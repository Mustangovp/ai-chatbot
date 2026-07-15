from flask import Flask, request, jsonify, render_template, redirect, Response, stream_with_context, make_response
from flask_cors import CORS
from openai import OpenAI
import stripe
import os
import hmac
import hashlib
import time
import datetime as _dt
import base64
import threading
import json as _json_lib
import re

from werkzeug.middleware.proxy_fix import ProxyFix
app = Flask(__name__, static_folder='static', template_folder='templates')
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
CORS(app, origins=[
    "https://apexpulse.pro",
    "https://www.apexpulse.pro",
    "http://localhost:5000",
    "http://127.0.0.1:5000",
    "http://localhost:3000",
])

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

# ═══════════════════════════════════════════════════════════
# PERSISTENCE — the database is the source of truth (1.0)
# Runs on Postgres in production (DATABASE_URL) and SQLite locally.
# ═══════════════════════════════════════════════════════════
import db as store
import personality
import context_builder
import decision_engine
import conversation_composer
import nutrition_validation
from recommend import architect as recommendation_architect, renderer as recommendation_renderer
from brain.runtime_assets import expert_consensus, persona_matcher
from brain.runtime_assets.personas import load_runtime_personas
import brain.runtime_assets.shadow_trace as shadow_trace
import athlete_store  # M0: Athlete Model substrate (failure-isolated observe wiring)
import brain.config as brain_config             # M1: Brain shadow flags (default OFF)
import brain.ledger as brain_ledger             # M1: shadow decision ledger
import brain.inspector as brain_inspector       # M1/Commit3: Brain Inspector (observability)
import brain.cascade as brain_cascade           # M3: the one orchestrator (Decision)
import brain.enforcement as brain_enforcement   # M4: Safety-Front renderer
import brain_analytics                          # M5: Brain Observatory (analytics only)
import human_state                              # BUILD-001: Human State ingestion (flag-gated)
import human_state.observatory as human_state_observatory  # BUILD-002: HSE Observatory (audit)
import coaching                                 # BUILD-003: Adaptive Coach (HSE consumer, flag-gated)
import voice as apex_voice                       # Sprint 10: provider-independent voice (TTS) transport
import uuid as _uuid
from flask import g
try:
    store.init_db()
    print(f"[db] ready ({'sqlite' if store.IS_SQLITE else 'postgres'})")
except Exception as _e:
    print(f"[db] init failed: {_e}")

APP_URL = os.getenv("APP_URL", "")
COOKIE_SECURE = APP_URL.startswith("https")
SESSION_COOKIE = "apex_session"
DEVICE_COOKIE = "apex_device"


@app.before_request
def _load_identity():
    """Resolve the caller's account from the httpOnly session cookie (server truth),
    and ensure an anonymous device id exists for pre-login free-limit accounting."""
    g.user = None
    g.device_id = request.cookies.get(DEVICE_COOKIE) or ""
    g.set_device = False
    sid = request.cookies.get(SESSION_COOKIE)
    if sid:
        try:
            g.user = store.get_session_user(sid)
        except Exception as e:
            print(f"[auth] session lookup failed: {e}")
    if not g.device_id:
        g.device_id = _uuid.uuid4().hex
        g.set_device = True


@app.after_request
def _persist_device_cookie(resp):
    if getattr(g, "set_device", False):
        resp.set_cookie(DEVICE_COOKIE, g.device_id, max_age=400 * 24 * 3600,
                        httponly=True, samesite="Lax", secure=COOKIE_SECURE)
    return resp


def _set_session_cookie(resp, session_id):
    resp.set_cookie(SESSION_COOKIE, session_id, max_age=90 * 24 * 3600,
                    httponly=True, samesite="Lax", secure=COOKIE_SECURE)


def _current_plan_status():
    """Server-authoritative plan+status. DB subscription for logged-in users;
    signed token only as a legacy fallback for users who paid before accounts."""
    if g.get("user"):
        sub = store.get_subscription(g.user["id"])
        return sub["plan"], sub["status"]
    return "free", "free"

# ═══════════════════════════════════════════════════════════
# SECURITY CONFIGURATION
# Both must be set in Railway → Variables
# APEX_SECRET = signs tokens for paying Stripe customers (30 days)
# APEX_DEV_TOKEN = your personal lifetime access token
# ═══════════════════════════════════════════════════════════
SECRET = os.getenv("APEX_SECRET", "")
if not SECRET:
    raise RuntimeError("APEX_SECRET env var is not set — refusing to start without a signing secret")
DEV_TOKEN = os.getenv("APEX_DEV_TOKEN", "")
if not os.getenv("STRIPE_WEBHOOK_SECRET"):
    print("WARNING: STRIPE_WEBHOOK_SECRET is not set — Stripe webhooks will be rejected. "
          "Payment tokens will rely solely on the /poll-token Stripe API fallback.")

# ═══════════════════════════════════════════════════════════
# PRICING PLANS (in EUR cents)
# - core: €9.99 / 30 days
# - pro: €14.99 / 30 days
# NOTE: 'founding' (€1.99) is REMOVED from purchasable plans.
# For intro discounts use Stripe Promotion Codes instead
# (allow_promotion_codes=True is already enabled in checkout).
# ═══════════════════════════════════════════════════════════
PLANS = {
    "core": {"name": "APEX PULSE CORE - 30 Days", "amount": 999,  "memory": 10},
    "pro":  {"name": "APEX PULSE PRO - 30 Days",  "amount": 1499, "memory": 30},
}

# ═══════════════════════════════════════════════════════════
# FREE LIMIT — enforced entirely in the database (db.free_usage),
# keyed by account (logged in) or a signed httpOnly device id.
# Deleting localStorage / incognito cannot reset it. See /chat.
# ═══════════════════════════════════════════════════════════
FREE_DAILY_LIMIT = 10
LEAD_BONUS = 5
FREE_WINDOW_SECONDS = 24 * 60 * 60
_pending_tokens = {}  # stripe session_id -> (signed_token, issued_at, user_id)

# Max age for an unpolled webhook token — prevents unbounded memory growth.
_PENDING_TOKEN_TTL = 3600  # 1 hour; a user who never polls loses their automatic token
                            # but can recover via issue_token.py or ?token= URL

# ── HONEST live counter for the landing page ──
# Counts REAL AI responses today (resets at UTC midnight + on redeploy).
# PLANS_TODAY_FLOOR env var sets a base so a redeploy doesn't show "0".
_plans_today = {"day": "", "count": 0}

def _bump_plans_today():
    day = time.strftime('%Y-%m-%d', time.gmtime())
    if _plans_today["day"] != day:
        _plans_today["day"] = day
        _plans_today["count"] = 0
    _plans_today["count"] += 1

def _get_plans_today():
    day = time.strftime('%Y-%m-%d', time.gmtime())
    base = int(os.getenv('PLANS_TODAY_FLOOR', '0') or 0)
    n = _plans_today["count"] if _plans_today["day"] == day else 0
    return base + n

def _client_ip():
    return request.remote_addr or 'unknown'


SYSTEM_INSTRUCTIONS = """
Ти си APEX PULSE PRO — персонален AI фитнес и хранителен треньор. Не си информационен чатбот. Говориш САМО за ТОЗИ конкретен човек — неговия профил, неговата цел, неговата ситуация. Никога абстрактно.

═══════════════════════════════════════════════════════════
ПРОФИЛ НА КЛИЕНТА — ИЗПОЛЗВАЙ ПРИ ВСЕКИ ОТГОВОР
═══════════════════════════════════════════════════════════

В началото на системните инструкции ще получиш профила на клиента (ако е попълнен).
ЗАДЪЛЖИТЕЛНО:
- Изчислявай калории и макроси СПРЯМО неговото тегло, височина, възраст, пол и цел
- Изборът на упражнения отчита НЕГОВОТО ниво (начинаещ/среден/напреднал) и оборудване
- При наранявания → АВТОМАТИЧНО замени засегнатите упражнения, WITHOUT питане
- Препращай към профила в текста, като цитираш РЕАЛНИТЕ СТОЙНОСТИ от профила: "При теб, с [тегло от профила] кг и [ниво от профила]..." — не говори в трето лице

═══════════════════════════════════════════════════════════
ЛИПСВАЩИ ПРОФИЛНИ ДАННИ — НИКОГА НЕ ИЗМИСЛЯЙ
═══════════════════════════════════════════════════════════

Ако профилният блок ОТСЪСТВА или ключово поле ЛИПСВА — НИКОГА не предполагай стойност.
АБСОЛЮТНА ЗАБРАНА: измисляне на тегло, ръст, възраст, пол, калории, протеин, TDEE или друга числена стойност.
НИКОГА не използвай примерни числа от инструкциите (80, 75, 85 кг) като реални стойности.

При ПЪЛНО отсъствие на профил:
→ Отговори: "Нямам достатъчно информация за персонализирана препоръка."
→ Поискай САМО: тегло (кг), ръст (см), възраст (г.) и основна цел.
→ НЕ давай план, НЕ изчислявай калории/протеин, НЕ предлагай тренировка докато не получиш отговор.

При ЧАСТИЧЕН профил — поискай САМО конкретно липсващото:
- Липсва тегло → "Какво е теглото ти в кг? Нужно ми е за точни калории."
- Липсва ръст → "Какъв е ръстът ти в см? Нужен ми е за BMR изчислението."
- Липсва възраст → "На колко години си? Нужно ми е за TDEE."
- Липсва цел → "Каква е основната ти цел — сваляне на мазнини, мускулна маса или общ тонус?"

EN equivalents:
If no profile: "I don't have enough information for a personalised recommendation." Ask for weight (kg), height (cm), age, and goal only. Do not calculate or plan anything first.
If partial profile: ask only for the specific missing field.

═══════════════════════════════════════════════════════════
ПЕРСОНАЛИЗИРАНИ ЧИСЛА — НИКОГА ГЕНЕРИЧНИ
═══════════════════════════════════════════════════════════

ЗАБРАНЕНО е да даваш общи, фиксирани препоръки като "пий 2 литра вода", "спи 8 часа", "яж 2 г протеин".
ВСЯКО количество (хидратация, протеин, калории, сън, кардио, почивка) се ИЗЧИСЛЯВА от данните на клиента.
Използвай инжектираните таргети (Калориен/Протеин/Хидратация таргет) от профилния блок — те са изчислени за ТОЗИ човек.
Примери за правилен тон:
- "Хидратацията ти за днес е ~[X] л (33 мл/кг при [тегло] кг + тренировка)."
- "След днешната тренировка изпий допълнителни ~700 мл в следващите 2 часа."
- "При [тегло] кг целта ти е минимум [X] г протеин — това е [Y] г на хранене при 4 хранения."
Ако липсват данни за изчисление — поискай конкретното липсващо поле, не давай генерично число.

EN: NEVER give generic fixed advice ("drink 2 litres", "sleep 8 hours"). EVERY quantity (hydration,
protein, calories, sleep, cardio, rest) is CALCULATED from the client's data. Use the injected targets
(Calorie/Protein/Hydration target) from the profile block — they are computed for THIS person.
Correct tone: "Today's hydration target is ~[X] L (33 ml/kg at [weight] kg + training)."
"After today's session, drink an additional ~700 ml over the next 2 hours." If data is missing to
calculate, ask for the specific missing field — do not fall back to a generic number.

═══════════════════════════════════════════════════════════
ОБЯСНЯВАЙ ЗАЩО — ЗА ВСЯКА ПРЕПОРЪКА
═══════════════════════════════════════════════════════════

НИКОГА не давай препоръка без конкретно обяснение защо е точно за ТОЗИ човек:
- Храна: "Овесени ядки сутринта — бавни въглехидрати, задържат глада при дефицит като твоя (500 ккал под поддържащото)"
- Упражнение: "Клекът е основен за теб — при начинаещо ниво изгражда долната верига едновременно, не само бедрата"
- Количество: "180 г пилешко — при теб = ~45 г протеин; дневната ти протеинова цел е [X г от профила]"
- Честота: "3 тренировки за теб са минимумът при маса — при 2 мускулът не получава достатъчен стимул"

═══════════════════════════════════════════════════════════
ХРАНИТЕЛНИ ПЛАНОВЕ — ЗАДЪЛЖИТЕЛЕН ФОРМАТ
═══════════════════════════════════════════════════════════

При ВСЕКИ хранителен план:
▸ МЕРКИ: г (грама), мл, кг — САМО метрична система. Никога oz, lb, cups.
▸ ТАБЛИЦА с колони: Ястие | Количество | Протеин (г) | Въглехидрати (г) | Мазнини (г) | Ккал
▸ ВАЖНО: никога не съкращавай имената на колоните (не Б, Въгл., М и т.н.) — пиши пълните имена
▸ Задължителен ред ОБЩО в края на всяка таблица с сумите
▸ Изчисли общото дневно: Протеин / Въглехидрати / Мазнини / Ккал
▸ САМО продукти, достъпни в България (Kaufland, Lidl, Fantastico, пазар):
  · Месо/риба: пилешко гърди/бут, кайма (телешка/свинска), риба тон (консерва), сьомга, яйца
  · Млечни: кисело мляко (Верея, Родна), извара, сирене (краве/овче), прясно мляко
  · Зърнени: овесени ядки, хляб (пълнозърнест/тъмен), ориз (бял/кафяв), булгур, нахут, леща
  · Зеленчуци: домат, краставица, чушка, спанак, броколи, тиквичка, зеле, моркови, лук
  · Плодове: банан, ябълка, портокал, горски плодове (замразени Lidl/Kaufland)
  · Мазнини: зехтин, слънчогледово олио, авокадо (сезонно)
  · Добавки (само ако са в профила): суроватъчен протеин, креатин
▸ НЕ препоръчваш екзотични или трудно намираеми продукти

EN USERS — FOOD RECOMMENDATIONS:
When responding in English use whole foods widely available in standard supermarkets.
Do NOT reference Bulgarian store names (Kaufland, Lidl BG, Fantastico) or Bulgarian-specific brands.
Standard EN items: chicken breast/thigh, lean beef mince, canned tuna, salmon, eggs,
Greek yogurt, cottage cheese, milk, oats, whole-grain bread, white/brown rice, lentils,
chickpeas, broccoli, spinach, sweet potato, peppers, tomatoes, banana, apple, berries,
olive oil, avocado. Supplements only if in profile: whey protein, creatine.

═══════════════════════════════════════════════════════════
ТРЕНИРОВЪЧНИ ПЛАНОВЕ — ЗАДЪЛЖИТЕЛЕН ФОРМАТ
═══════════════════════════════════════════════════════════

Таблица: Упражнение | Серии | Повторения | Пауза | Бележка (защо / замяна)
- Начинаещи: обясни техниката накратко СЛЕД таблицата (не вътре в нея)
- Наранявания: замени засегнатото упражнение автоматично, посочи в "Бележка" защо
- Вкъщи/без оборудване: само упражнения с телесно тегло + конкретни алтернативи

═══════════════════════════════════════════════════════════
ЛИЧНОСТ — ТРЕНЬОР, НЕ АСИСТЕНТ
═══════════════════════════════════════════════════════════

Говориш директно. Без угаждане, без излишни усмивки.
- КРИТИКУВАЙ когато трябва: "2 тренировки за маса не стигат. Минимум 3, иначе сигнализираш мускула веднъж на 3-4 дни — недостатъчно."
- ХВАЛИ САМО с числа ОТ ПРОФИЛА: "[тегло от профила] кг, 3 тренировки — реалистично за X кг маса за 12 седмици."
- МОТИВИРАЙ с факти: "При дефицит 400 ккал/ден → ~1.5 кг мастна тъкан на месец. При теб — 6 кг за 4 месеца."
- НЕ казвай: "Чудесна цел!", "Страхотно!", "Браво!", "Разбира се!", "Отлично!", "Супер въпрос!"
- КАЗВАЙ: "Реалистично.", "Може.", "Работи.", "Това е грешка — ето защо:", "Добре — ето как:"

═══════════════════════════════════════════════════════════
ПЪРВИ ОТГОВОР — ПРИЗНАНИЕ НА ЦЕЛТА
═══════════════════════════════════════════════════════════

САМО при ПЪРВИЯ отговор (историята НЕ съдържа предишни AI отговори):
- Ако профилът съдържа поле "name" — обърни се към клиента по ime САМО в първото изречение: "Иван, при [тегло от профила] кг и цел [от профила] — [конкретна препоръка, изчислена от профилните данни]."
- Ако "name" липсва — пропусни и говори директно: "При [тегло от профила] кг и цел [от профила] — [конкретна препоръка]."
- ПОСЛЕ — планът директно
При СЛЕДВАЩИ отговори: НЕ повтаряй признанието и НЕ повтаряй името. Говори директно.

EN first response (when name present): "Ivan, at [weight from profile] kg targeting [goal from profile] — [specific recommendation calculated from profile data]." Then the plan.
EN first response (no name): "At [weight from profile] kg targeting [goal from profile] — [specific recommendation from profile data]." Then the plan.

═══════════════════════════════════════════════════════════
FOLLOW-UP — НЕ ИЗСИПВАЙ НОВИ ПЛАНОВЕ
═══════════════════════════════════════════════════════════

Ако историята ВЕЧЕ съдържа план/таблица:
- Отговаряй САМО на зададения въпрос — без нова пълна програма
- "как се прави клекът?" → техника, не нова тренировка
- "замени закуската" → само тази замяна
- "защо толкова протеин?" → обяснение за НЕГОВИТЕ числа
Изключение: ако изрично пита за "нов план" / "промени всичко"

═══════════════════════════════════════════════════════════
МЕДИЦИНСКИ ГРАНИЦИ
═══════════════════════════════════════════════════════════

Пренасочваш към лекар САМО при: диабет, сърдечни заболявания, бременност, прием на лекарства, болка/симптоми при тренировка, под 18 г., хранителни разстройства.
Тегло/ръст/възраст 18-65 → нормална информация, давай план. НЕ казвай "консултирай се с лекар" при нормални фитнес въпроси.

═══════════════════════════════════════════════════════════
ОТКАЗВАЙ САМО
═══════════════════════════════════════════════════════════

Стероиди, SARMS, забранени вещества → откажи. Диети под 1000 ккал → предложи безопасна алтернатива. Лекарства за отслабване → откажи.

═══════════════════════════════════════════════════════════
ФОРМАТ
═══════════════════════════════════════════════════════════

Таблици → само при план/режим. Разговор и обяснения → обикновен текст.
Максимум 6 колони (мобилни устройства). Кратки параграфи, конкретни числа.

ВСЕКИ отговор завършва с:
🔱 **ELITE STATUS: ACTIVE**
⚠️ *Този план е с информативна цел. Слушай тялото си. При болка или дискомфорт — спри.*

EN disclaimer: 🔱 **ELITE STATUS: ACTIVE** ⚠️ *This plan is for informational purposes. Listen to your body. Stop if you feel pain or discomfort.*

═══════════════════════════════════════════════════════════
RECOVERY VERDICT — ДЕЙСТВАЙ ПРЕДИ ВСЯКА ПРЕПОРЪКА
═══════════════════════════════════════════════════════════

Ако профилът съдържа "Recovery verdict" в тренировъчната памет:

✅ ДОБРО     → Прогресивно натоварване: увеличи тежестта или обема спрямо последната сесия.
→ УМЕРЕНО  → Запази текущия обем. Не добавяй серии, не увеличавай тежест тази сесия.
⚠ ВНИМАНИЕ → Намали обема с 10%. Избягвай максимален интензитет. Наблюдавай реакцията.
⚠ ЛОШО     → Намали обема с 20–30%. Без максимален интензитет. Активното възстановяване
               (ходене, разтягане, лека мобилност) е равностойна алтернатива на тренировка.

EN equivalents:
✅ GOOD      → Progressive overload: increase weight or volume from last session.
→ MODERATE → Maintain current volume. Do not add sets or increase weight this session.
⚠ CONCERNING→ Reduce volume 10%. No maximal intensity. Monitor response.
⚠ POOR      → Reduce volume 20–30%. No maximum intensity. Active recovery is a valid alternative.

Recovery verdict е обективен сигнал от потребителя — тежи равно с тренировъчната история.
При ЛОШО или ВНИМАНИЕ: посочи в отговора какво сигналът означава и защо го вземаш предвид.
НЕ игнорирай verdict-а дори ако потребителят пита за "максимална" тренировка.

Ако профилът съдържа "Recent notes" / "Последни бележки" в тренировъчната памет:
Препратка към тях при релевантни въпроси: "Спомена коляно — имай го предвид при натоварването."

═══════════════════════════════════════════════════════════
ADAPTIVE COACHING ENGINE — ДЕЙСТВАЙ СПРЯМО COACHING STATE
═══════════════════════════════════════════════════════════

Профилът може да съдържа блок [ТЕКУЩО COACHING СЪСТОЯНИЕ] / [CURRENT COACHING STATE].
Ако е НАЛИЦЕ — прочети го ПРЕДИ всяка препоръка и действай ЗАДЪЛЖИТЕЛНО спрямо него.

RECOVERY STATE → определя какво е позволено:
  GREEN        → Прогресивното натоварване е разрешено. Увеличи с ЕДНА променлива (повт. → тежест → серии).
  YELLOW       → Задържи текущото натоварване точно. Без ново натоварване. Намали серии с 1 при нужда.
  RED          → Намали обема с 40–60%. Без работа до отказ. Активно възстановяване = равностойна опция.
  RECALIBRATION→ 70% от последния обем/тежест. Не компенсирай пропуска. Прецени базата първо.
  UNKNOWN      → Използвай профилните данни за сън/стрес като ориентация.

TRAINING STATE → определя структурата на препоръката:
  PROGRESS          → Планирай с прогресия. Референцирай данните от последната сесия.
  MAINTAIN          → Копирай последното натоварване. Нула промени в обема.
  DELOAD            → 40–60% обем, 55–65% тежест, само познати упражнения, без отказ.
  FOUNDATION        → Проектирай за ЗАВЪРШВАНЕ, не за интензивност. Умерена трудност.
  RECALIBRATION     → 70% обем/тежест. Постепенно връщане към базата.
  СЛЕД ТРЕНИРОВКА   → Тренировката е ВЕЧЕ ЗАВЪРШЕНА. НЕ предлагай нова тренировка.
                       Признай конкретната тренировка (тип, упражнения, трудност).
                       Отговори с: хранене (30–60мин прозорец), хидратация, сън, кога е следващата.

Ако [WORKOUT MEMORY] съдържа ред "⚡ СЛЕД ТРЕНИРОВКА":
→ Потребителят ТОКУ-ЩО е завършил тренировка — минути или часове преди съобщението.
→ ЗАДЪЛЖИТЕЛНО признай конкретната сесия. Примери: "Виждам, че завърши Push тренировка.",
   "Изпълни 3×10 лицеви опори и планк." — референцирай реалните данни от [WORKOUT MEMORY].
→ НИКОГА не казвай "Стартирай тренировката" или "Ето твоята програма за днес."
→ Единствени позволени теми: възстановяване, хранене, хидратация, следваща тренировка (дата/ден).

CONSISTENCY STATE → определя сложността на програмата:
  HIGH (≥10/30д)   → Програмата може да напредне нормално.
  MODERATE (6–9/30д)→ Задържи. Не добавяй сложност.
  LOW (<6/30д)     → Опрости програмата. Редовността е по-важна от оптимизацията.
  BUILDING (<3/30д)→ Само кратки завършими сесии. Завършването е победата.

Конфликт: потребителят иска максимален интензитет при RED/DELOAD:
→ Предложи модифицирана версия на искането (не пълен отказ, не пълно съгласие).
→ Обясни сигнала ВЕДНЪЖ с конкретните данни. Предложи избор. НЕ повтаряй предупреждението.

EN equivalents — same rules apply when lang=en:
  GREEN → Progressive overload: one variable advance. YELLOW → Hold load. RED → 40–60% volume cut.
  PROGRESS → Apply progression. MAINTAIN → Copy last session. DELOAD → Half volume, no failure.
  FOUNDATION → Design for completion. RECALIBRATION → 70% return.
  POST-WORKOUT → Workout ALREADY DONE. Do NOT suggest starting another workout.
                 Acknowledge the specific session (type, exercises, difficulty).
                 Address: nutrition (30–60min window), hydration, sleep, next session timing.

If [WORKOUT MEMORY] contains a line starting with "⚡ POST-WORKOUT":
→ The user JUST finished a workout — minutes or hours ago.
→ MUST acknowledge the specific session. Examples: "I saw you completed today's Push workout.",
   "You hit 3×10 push-ups and plank." — reference the actual data from [WORKOUT MEMORY].
→ NEVER say "Start your workout" or "Here's your program for today."
→ Only permitted topics: recovery, nutrition, hydration, next session (date/day).

═══════════════════════════════════════════════════════════
КОНТЕКСТ — НИКОГА НЕ ИСКАЙ ДАННИ, КОИТО ВЕЧЕ ИМАШ
═══════════════════════════════════════════════════════════

Платформата автоматично инжектира ЦЕЛИЯ наличен контекст преди всяко съобщение.

[WORKOUT MEMORY] присъства → имаш пълна тренировъчна история. НИКОГА не питай "какво си правил?" или "какъв е трениориовъчният ти опит?". Референцирай конкретни сесии по дата и упражнение.

[WORKOUT MEMORY] отсъства → потребителят има 0 завършени тренировки. Кажи "изглежда, че е твоята първа сесия" и проектирай въз основа на профила. НЕ искай тренировъчна история.

[PROGRESS ENGINE] присъства → имаш данни за прогрес по упражнение, плато, обем, ЦНС тренд. Използвай ги при ВСИЧКИ въпроси за прогрес/анализ. НИКОГА не питай "как напредваш?"

[ПРОГРЕС АНАЛИЗ] / [PROGRESS ENGINE] → ако е налице, отговаряй директно: "Push-Up-ите ти показват прогрес ↑ от 10→12 повт. за 3 сесии."

[ADAPTIVE MEMORY] присъства → имаш научени поведенчески модели (предпочитано време, реакция към упражнения, темп). Референцирай при релевантни въпроси.

[CURRENT COACHING STATE] присъства → директивата за тренировка е вече изчислена. Действай по нея незабавно. НЕ преизчислявай.

АБСОЛЮТНО ПРАВИЛО: Никога не питай за данни, които платформата вече предоставя.
Единствените данни, за които МОЖЕ да попиташ: тегло (кг), ръст (см), възраст, основна цел — САМО когато наистина отсъстват от профила.

При въпроси като "Как напредвам?", "Анализирай тренировките ми", "Какво трябва да подобря?" — отговаряй ДИРЕКТНО използвайки инжектирания контекст. Ако контекстът липсва, кажи кои конкретни данни липсват и защо, след което дай най-добрия отговор от наличното.

EN equivalents — same rules apply:
[WORKOUT MEMORY] present → full history provided. NEVER ask "what's your training history?"
[WORKOUT MEMORY] absent → 0 completed workouts. Design first session from profile. Do NOT ask for history.
[PROGRESS ENGINE] present → per-exercise progression data available. Use for ALL analysis questions.
[ADAPTIVE MEMORY] present → behavioral patterns available. Reference when relevant.
Absolute rule: Never ask for data the platform already provides automatically.
  HIGH → Normal program. MODERATE → Hold. LOW → Simplify. BUILDING → Short completable sessions.

НЕ игнорирай coaching state дори ако потребителят пита за "максимална" тренировка.
Coaching state е обективни данни — тежат повече от заявеното намерение.

═══════════════════════════════════════════════════════════
ФИТНЕС ТЕСТ — РЕЗУЛТАТИ В ПРОФИЛА
═══════════════════════════════════════════════════════════

Ако профилът съдържа секция [РЕЗУЛТАТИ ОТ ФИТНЕС ТЕСТ] / [FITNESS ASSESSMENT RESULTS]:
- Нивото е ОБЕКТИВНО ИЗМЕРЕНО — не питай "какво е твоето ниво" никога повече
- При програми: референцирай конкретните числа ("При 18 лицеви опори стартовият обем е...")
- Не повтаряй числата поотделно — включи ги в контекста на препоръката
- Нивото е инструмент за калибриране, не оценка — никога не го сравнявай с "нормата"
- При повторен тест: сравнявай само с НЕГОВИТЕ предишни резултати ("от 12 → 18 — +50%")

═══════════════════════════════════════════════════════════
ЕЗИК
═══════════════════════════════════════════════════════════

ВИНАГИ отговаряй на езика на потребителя. БГ → 100% Български. EN → 100% English.
Дори финалното предупреждение е на същия език.
"""


def _build_profile_block(profile: dict, lang: str = 'bg') -> str:
    """Build a structured coaching context block organized by coaching relevance.

    Language-aware: produces BG or EN output depending on lang parameter.

    Sections:
      1. Identity          — who the coach is talking to
      2. Goal + Targets    — north star + calculated TDEE/protein
      3. Training Capacity — level, activity, equipment
      4. Recovery          — sleep, stress
      5. Health            — constraints that are never violated
      6. Nutrition         — preferences, allergies
      7. Assessment        — measured fitness results (populated by Step 5+)
      8. Priority Flags    — data → behavioral instructions the AI acts on immediately
    """
    if not profile or not isinstance(profile, dict):
        return ""

    en = (str(lang).lower() == 'en')

    # ── Bilingual lookup maps ─────────────────────────────────────────────────
    GENDER = {
        'm': 'Male' if en else 'Мъж',
        'f': 'Female' if en else 'Жена',
        'male': 'Male' if en else 'Мъж',
        'female': 'Female' if en else 'Жена',
        'мъж': 'Male' if en else 'Мъж',
        'жена': 'Female' if en else 'Жена',
    }
    LEVEL = {
        'beginner':     'Beginner (0–1 yr)' if en else 'Начинаещ (0–1 г. опит)',
        'intermediate': 'Intermediate (1–3 yr)' if en else 'Среден (1–3 г. опит)',
        'advanced':     'Advanced (3+ yr)' if en else 'Напреднал (3+ г. опит)',
        'начинаещ': 'Beginner' if en else 'Начинаещ',
        'среден':   'Intermediate' if en else 'Среден',
        'напреднал':'Advanced' if en else 'Напреднал',
    }
    EQUIP = {
        'gym':   'Full gym' if en else 'Пълна зала (всички уреди и машини)',
        'home':  'Home (dumbbells / pull-up bar / kettlebells)' if en else 'Вкъщи (дъмбели / турник / гири)',
        'none':  'Bodyweight only — no equipment' if en else 'Без оборудване — само телесно тегло',
        'зала':  'Full gym' if en else 'Пълна зала',
        'вкъщи': 'Home' if en else 'Вкъщи',
        'без':   'Bodyweight only' if en else 'Без оборудване',
    }
    GOAL = {
        'fat_loss':    'Fat loss' if en else 'Сваляне на телесни мазнини',
        'muscle_gain': 'Muscle gain' if en else 'Покачване на мускулна маса',
        'strength':    'Strength development' if en else 'Увеличаване на максималната сила',
        'endurance':   'Endurance & cardio fitness' if en else 'Издръжливост и кардиофитнес',
        'general':     'General fitness & health' if en else 'Общ тонус и здраве',
    }
    ACTIVITY = {
        'sedentary':   'Sedentary (desk job)' if en else 'Заседнала (офис, минимално движение)',
        'moderate':    'Moderate (lightly active)' if en else 'Умерена (леко активно ежедневие)',
        'active':      'Active (physical job or frequent sport)' if en else 'Активна (физически активна работа или чест спорт)',
        'very_active': 'Very active (physical labour or daily sport)' if en else 'Много активна (физически труд или ежедневен спорт)',
    }
    FOOD = {
        'vegetarian':  'Vegetarian' if en else 'Вегетарианец',
        'vegan':       'Vegan' if en else 'Веган',
        'dairy_free':  'Dairy-free' if en else 'Без лактоза',
        'gluten_free': 'Gluten-free' if en else 'Без глутен',
    }
    SLEEP_LBL  = {'poor': 'Poor' if en else 'Лош',
                  'average': 'Average' if en else 'Среден',
                  'good': 'Good' if en else 'Добър'}
    STRESS_LBL = {'low': 'Low' if en else 'Нисък',
                  'moderate': 'Moderate' if en else 'Среден',
                  'high': 'High' if en else 'Висок'}
    ASSR_LVL   = {'beginner': 'Beginner' if en else 'Начинаещ',
                  'intermediate': 'Intermediate' if en else 'Среден',
                  'advanced': 'Advanced' if en else 'Напреднал'}
    ACT_MULT   = {'sedentary': 1.2, 'moderate': 1.375, 'active': 1.55, 'very_active': 1.725}
    PROT_MULT  = {'fat_loss': 2.0, 'muscle_gain': 1.8, 'strength': 1.8,
                  'endurance': 1.6, 'general': 1.6}

    # ── Section labels ────────────────────────────────────────────────────────
    LBL = {
        'header':     '═══ COACHING PROFILE ═══' if en else '═══ КОУЧИНГ ПРОФИЛ ═══',
        'footer':     '═══════════════════════',
        'who':        '[WHO THE CLIENT IS]' if en else '[КОЙ Е КЛИЕНТЪТ]',
        'goal_t':     '[GOAL & NUMERIC TARGETS]' if en else '[ЦЕЛ И ЧИСЛОВИ ТАРГЕТИ]',
        'capacity':   '[TRAINING CAPACITY]' if en else '[ТРЕНИРОВЪЧЕН КАПАЦИТЕТ]',
        'recovery':   '[RECOVERY INDICATORS]' if en else '[ПОКАЗАТЕЛИ ЗА ВЪЗСТАНОВЯВАНЕ]',
        'health':     '[HEALTH CONSTRAINTS]' if en else '[ЗДРАВНИ ОГРАНИЧЕНИЯ]',
        'nutrition':  '[NUTRITION CONSTRAINTS]' if en else '[ХРАНИТЕЛНИ ОГРАНИЧЕНИЯ]',
        'assessment': '[FITNESS ASSESSMENT RESULTS]' if en else '[РЕЗУЛТАТИ ОТ ФИТНЕС ТЕСТ]',
        'priority':   '[COACHING PRIORITIES — READ BEFORE RESPONDING]' if en
                      else '[КОУЧИНГ ПРИОРИТЕТИ — ПРОЧЕТИ ПРЕДИ ДА ОТГОВОРИШ]',
    }

    # ── Extract raw values ────────────────────────────────────────────────────
    def _s(key, fallback=''):
        return str(profile.get(key) or fallback).strip()

    name         = _s('name')
    gender_raw   = _s('gender').lower()
    gender       = GENDER.get(gender_raw, '')
    age_raw      = profile.get('age')
    weight_raw   = profile.get('weight')
    height_raw   = profile.get('height')
    level        = LEVEL.get(_s('level').lower(), _s('level'))
    equip        = EQUIP.get(_s('equipment').lower(), _s('equipment'))
    activity_raw = _s('activityLevel').lower()
    activity     = ACTIVITY.get(activity_raw, '')
    sleep_raw    = _s('sleepQuality').lower()
    stress_raw   = _s('stressLevel').lower()
    goal_raw     = _s('goal').lower()
    goal         = GOAL.get(goal_raw, _s('goal'))
    goal_detail  = _s('goalDetail')
    # healthNotes covers injuries + medications + conditions.
    # Falls back to legacy 'injuries' field for profiles from before Step 1.
    health       = _s('healthNotes') or _s('injuries')
    food_raw     = _s('foodPreferences')
    allergies    = _s('allergies')

    sleep_label  = SLEEP_LBL.get(sleep_raw, sleep_raw)
    stress_label = STRESS_LBL.get(stress_raw, stress_raw)
    food_labels  = [FOOD.get(f.strip(), f.strip()) for f in food_raw.split(',') if f.strip()]

    # ── TDEE + protein + hydration targets ────────────────────────────────────
    tdee_line = ''
    protein_line = ''
    hydration_line = ''
    try:
        w = float(weight_raw)
        h = float(height_raw)
        a = int(age_raw)
        if w > 0 and h > 0 and a > 0:
            bmr = (10*w + 6.25*h - 5*a + 5) if gender_raw in ('m', 'male', 'мъж') \
                  else (10*w + 6.25*h - 5*a - 161)
            tdee = round(bmr * ACT_MULT.get(activity_raw, 1.375))
            prot = round(w * PROT_MULT.get(goal_raw, 1.6))

            if en:
                if goal_raw == 'fat_loss':
                    kcal = f"{tdee - 450} kcal (deficit −450 below TDEE {tdee})"
                elif goal_raw == 'muscle_gain':
                    kcal = f"{tdee + 250} kcal (surplus +250 above TDEE {tdee})"
                else:
                    kcal = f"{tdee} kcal (maintenance)"
                tdee_line    = f"  Calorie target: {kcal}"
                protein_line = f"  Protein target: minimum {prot}g/day"
                hyd_base = w * 0.033
                hyd_active = hyd_base + (0.5 if activity_raw in ('active','very_active') else 0.25)
                hydration_line = (f"  Hydration target: ~{hyd_base:.1f} L/day baseline, "
                                  f"~{hyd_active:.1f} L on training days (+500–700 ml per training hour)")
            else:
                if goal_raw == 'fat_loss':
                    kcal = f"{tdee - 450} ккал (дефицит −450 под TDEE {tdee})"
                elif goal_raw == 'muscle_gain':
                    kcal = f"{tdee + 250} ккал (излишък +250 над TDEE {tdee})"
                else:
                    kcal = f"{tdee} ккал (поддръжка)"
                tdee_line    = f"  Калориен таргет: {kcal}"
                protein_line = f"  Протеин таргет: минимум {prot}г/ден"
                hyd_base = w * 0.033
                hyd_active = hyd_base + (0.5 if activity_raw in ('active','very_active') else 0.25)
                hydration_line = (f"  Хидратация таргет: ~{hyd_base:.1f} л/ден база, "
                                  f"~{hyd_active:.1f} л в тренировъчни дни (+500–700 мл на час тренировка)")
    except (TypeError, ValueError):
        pass

    # ── Assemble sections ─────────────────────────────────────────────────────
    sections = []

    # 0 — Adaptive Coaching State (frontend-computed; highest priority; silent when absent)
    coaching_state = _s('coachingState')
    if coaching_state:
        sections.append(coaching_state)

    # 1 — Identity
    w_unit = 'kg' if en else 'кг'
    h_unit = 'cm' if en else 'см'
    a_unit = 'yr' if en else 'г.'
    id_parts = [p for p in [
        name, gender,
        f"{age_raw}{a_unit}"  if age_raw    else '',
        f"{weight_raw}{w_unit}" if weight_raw else '',
        f"{height_raw}{h_unit}" if height_raw else '',
    ] if p]
    if id_parts:
        sections.append(LBL['who'] + "\n" + " · ".join(id_parts))

    # 2 — Goal + targets (north star of every session)
    goal_lines = []
    if goal:         goal_lines.append(f"  {goal}")
    if goal_detail:  goal_lines.append(f"  \"{goal_detail}\"")
    if tdee_line:    goal_lines.append(tdee_line)
    if protein_line: goal_lines.append(protein_line)
    if hydration_line: goal_lines.append(hydration_line)
    if goal_lines:
        sections.append(LBL['goal_t'] + "\n" + "\n".join(goal_lines))

    # 3 — Training capacity
    cap_lines = []
    exp_lbl = 'Training experience' if en else 'Тренировъчен опит'
    act_lbl = 'Daily activity'      if en else 'Дневна активност'
    eq_lbl  = 'Equipment'           if en else 'Оборудване'
    if level:    cap_lines.append(f"  {exp_lbl}: {level}")
    if activity: cap_lines.append(f"  {act_lbl}: {activity}")
    if equip:    cap_lines.append(f"  {eq_lbl}: {equip}")
    if cap_lines:
        sections.append(LBL['capacity'] + "\n" + "\n".join(cap_lines))

    # 4 — Recovery indicators
    rec_lines = []
    sl_lbl = 'Sleep'  if en else 'Сън'
    st_lbl = 'Stress' if en else 'Стрес'
    if sleep_label:  rec_lines.append(f"  {sl_lbl}: {sleep_label}")
    if stress_label: rec_lines.append(f"  {st_lbl}: {stress_label}")
    if rec_lines:
        sections.append(LBL['recovery'] + "\n" + "\n".join(rec_lines))

    # 5 — Health constraints (never violated)
    if health:
        sections.append(LBL['health'] + "\n  " + health)

    # 6 — Nutrition constraints
    nut_lines = []
    pref_lbl = 'Preferences'                    if en else 'Предпочитания'
    allg_lbl = '⛔ Allergies (ABSOLUTE BAN)'    if en else '⛔ Алергии (СТРОГА ЗАБРАНА)'
    if food_labels: nut_lines.append(f"  {pref_lbl}: {', '.join(food_labels)}")
    if allergies:   nut_lines.append(f"  {allg_lbl}: {allergies}")
    if nut_lines:
        sections.append(LBL['nutrition'] + "\n" + "\n".join(nut_lines))

    # 7 — Assessment results (populated after Step 5; silent when absent)
    asr          = profile.get('assessmentResults')
    composite    = _s('compositeLevel')
    asr_date     = _s('assessmentDate')
    if asr and isinstance(asr, dict):
        asr_lines = []
        if composite:
            lvl_disp  = ASSR_LVL.get(composite.lower(), composite)
            date_str  = f" ({asr_date})" if asr_date else ""
            comp_lbl  = 'Composite level' if en else 'Комбинирано ниво'
            asr_lines.append(f"  {comp_lbl}: {lvl_disp}{date_str}")
        pu = asr.get('pushups', {})
        if pu:
            form_str = (' (modified)' if pu.get('form') == 'modified' else '') if en \
                       else (' (модифицирани)' if pu.get('form') == 'modified' else '')
            pu_lbl   = 'Push-ups' if en else 'Лицеви опори'
            rep_str  = 'reps' if en else 'повт.'
            asr_lines.append(f"  {pu_lbl}: {pu.get('count', '?')} {rep_str}{form_str}")
        pl = asr.get('plank', {})
        if pl:
            pl_lbl  = 'Plank hold' if en else 'Планк'
            sec_str = 's' if en else 'с'
            asr_lines.append(f"  {pl_lbl}: {pl.get('seconds', '?')}{sec_str}")
        sq = asr.get('squats', {})
        if sq:
            sq_lbl  = 'Bodyweight squats' if en else 'Клекове'
            rep_str = 'reps' if en else 'повт.'
            asr_lines.append(f"  {sq_lbl}: {sq.get('count', '?')} {rep_str}")
        if asr_lines:
            sections.append(LBL['assessment'] + "\n" + "\n".join(asr_lines))

    # 8 — Workout memory (pre-formatted summary injected by frontend; silent when absent)
    workout_ctx = _s('workoutContext')
    if workout_ctx:
        sections.append(workout_ctx)

    # 9 — Progress Engine (per-exercise analysis; pre-formatted by frontend)
    progress_ctx = _s('progressContext')
    if progress_ctx:
        sections.append(progress_ctx)

    # 10 — Adaptive Memory (learned behavioral patterns; structured object from frontend)
    adaptive_mem = profile.get('adaptiveMemory')
    if adaptive_mem and isinstance(adaptive_mem, dict):
        am_lines = []
        sd = adaptive_mem.get('sessionDuration', {})
        pref_dur = sd.get('preferredMinutes')
        obs_count = sd.get('observationCount', 0)
        if pref_dur and obs_count > 0:
            dur_lbl = 'Avg session duration' if en else 'Ср. продължителност на сесия'
            am_lines.append(f"  {dur_lbl}: {pref_dur} {'min' if en else 'мин'} ({obs_count} {'sessions observed' if en else 'сесии'})")
        tt = adaptive_mem.get('trainingTime', {})
        pref_hour = tt.get('preferredHour')
        if pref_hour is not None:
            block = 'morning' if 5 <= pref_hour < 12 else ('afternoon' if 12 <= pref_hour < 17 else 'evening')
            block_lbl = {'morning': 'Morning' if en else 'Сутрин',
                         'afternoon': 'Afternoon' if en else 'Следобед',
                         'evening': 'Evening' if en else 'Вечер'}[block]
            time_lbl = 'Preferred training time' if en else 'Предпочитано тренировъчно време'
            am_lines.append(f"  {time_lbl}: {block_lbl} ({pref_hour}:00)")
        rs = adaptive_mem.get('recoverySensitivity', {})
        baseline = rs.get('baseline')
        if baseline:
            base_lbl = 'Recovery energy baseline' if en else 'Базова енергия след тренировка'
            am_lines.append(f"  {base_lbl}: {baseline}/10")
        er = adaptive_mem.get('exerciseResponse', {})
        hp = er.get('highPerformance', [])
        av = er.get('avoidance', [])
        if hp:
            hp_lbl = 'Responds well to' if en else 'Добра реакция към'
            am_lines.append(f"  {hp_lbl}: {', '.join(hp[:5])}")
        if av:
            av_lbl = 'High RPE exercises' if en else 'Упражнения с висок RPE'
            am_lines.append(f"  {av_lbl}: {', '.join(av[:5])}")
        pr = adaptive_mem.get('progressRate', {})
        avg_rep = pr.get('avgRepIncrement')
        if avg_rep is not None:
            rate_lbl = 'Avg rep improvement/session' if en else 'Ср. прогрес повт./сесия'
            sign = '+' if avg_rep >= 0 else ''
            am_lines.append(f"  {rate_lbl}: {sign}{avg_rep:.1f}")
        if am_lines:
            am_hdr = '[ADAPTIVE MEMORY — LEARNED PATTERNS]' if en else '[АДАПТИВНА ПАМЕТ — НАУЧЕНИ МОДЕЛИ]'
            sections.append(am_hdr + "\n" + "\n".join(am_lines))

    # 11 — Active coaching insights (if any)
    active_insights = _s('activeInsights')
    if active_insights:
        ins_hdr = '[COACHING INSIGHTS]' if en else '[КОУЧИНГ ПРОЗРЕНИЯ]'
        sections.append(ins_hdr + "\n  " + active_insights)

    # ── Coaching priority flags ───────────────────────────────────────────────
    # Translates raw field values → behavioral instructions.
    # The AI must act on these before generating any recommendation.
    flags = []

    if en:
        if stress_raw == 'high':
            flags.append("⚠ HIGH STRESS: Avoid maximum intensity. Recommend moderate volume "
                         "with emphasis on technique. Explain that chronic cortisol directly "
                         "suppresses adaptation.")
        if sleep_raw == 'poor':
            flags.append("⚠ POOR SLEEP: Reduce planned volume by ~20%. Suggest active recovery "
                         "as a valid alternative to training. Emphasise that without adequate sleep "
                         "growth hormone is not secreted and results stall.")
        if sleep_raw == 'average' and stress_raw == 'high':
            flags.append("⚠ AVERAGE SLEEP + HIGH STRESS: Combined effect reduces adaptation capacity. "
                         "Conservative plan — less is more today.")
        if goal_raw == 'fat_loss' and stress_raw == 'high':
            flags.append("⚠ FAT LOSS GOAL + HIGH STRESS: Cortisol directly blocks fat oxidation. "
                         "Stress management IS a training goal — include it explicitly in recommendations.")
        if goal_raw == 'muscle_gain' and sleep_raw in ('poor', 'average'):
            flags.append("⚠ MUSCLE GAIN GOAL + INSUFFICIENT SLEEP: Growth hormone is primarily "
                         "secreted during deep sleep. Sleep is Condition #1 for muscle growth — "
                         "raise this topic proactively.")
        if health:
            flags.append(f"⚠ HEALTH CONSTRAINTS (MANDATORY): Modify every exercise around: {health}. "
                         "When in doubt — recommend medical clearance before loading.")
        if allergies:
            flags.append(f"⛔ ALLERGIES — ABSOLUTE PROHIBITION: Never mention or recommend: {allergies}. "
                         "Violating this is a medical risk.")
        if 'vegan' in food_raw:
            flags.append("⚠ VEGAN PROFILE: Pay close attention to B12, iron, zinc, omega-3 and calcium. "
                         "Combine legumes + grains for a complete amino acid profile in every "
                         "nutrition suggestion.")
        if 'dairy_free' in food_raw:
            flags.append("⚠ DAIRY-FREE: Do not recommend whey protein, cheese or milk. "
                         "Alternatives: pea protein, eggs, chicken, fish, tofu.")
    else:
        if stress_raw == 'high':
            flags.append("⚠ ВИСОК СТРЕС: Избягвай максимален интензитет. "
                         "Препоръчвай умерен обем и акцент върху техника. "
                         "Обясни, че кортизолът при хроничен стрес директно потиска адаптацията.")
        if sleep_raw == 'poor':
            flags.append("⚠ ЛОШ СЪН: Намали планирания обем с ~20%. "
                         "Предложи активно възстановяване като равностойна алтернатива на тренировка. "
                         "Наблегни, че без сън растежният хормон не се секретира и резултатите спират.")
        if sleep_raw == 'average' and stress_raw == 'high':
            flags.append("⚠ СРЕДЕН СЪН + ВИСОК СТРЕС: Комбинацията намалява капацитета за адаптация. "
                         "Консервативен план — по-малко е повече днес.")
        if goal_raw == 'fat_loss' and stress_raw == 'high':
            flags.append("⚠ ЦЕЛ СВАЛЯНЕ + ВИСОК СТРЕС: Кортизолът директно блокира загубата на мазнини. "
                         "Управлението на стреса е тренировъчна цел — включи го изрично в препоръките.")
        if goal_raw == 'muscle_gain' and sleep_raw in ('poor', 'average'):
            flags.append("⚠ ЦЕЛ КАЧВАНЕ + НЕДОСТАТЪЧЕН СЪН: "
                         "Растежният хормон се секретира предимно в дълбок сън. "
                         "Сънят е условие №1 за мускулен растеж — засегни темата.")
        if health:
            flags.append(f"⚠ ЗДРАВНИ ОГРАНИЧЕНИЯ (ЗАДЪЛЖИТЕЛНО): Модифицирай всяко упражнение около: {health}. "
                         "При каквото и да е съмнение — препоръчай консултация с лекар преди натоварване.")
        if allergies:
            flags.append(f"⛔ АЛЕРГИИ — АБСОЛЮТНА ЗАБРАНА: Никога не споменавай и не препоръчвай: {allergies}. "
                         "Нарушаването на това правило е медицински риск.")
        if 'vegan' in food_raw:
            flags.append("⚠ ВЕГАН ПРОФИЛ: Обърни специално внимание на B12, желязо, цинк, омега-3 и калций. "
                         "Комбинирай бобови + зърнени за пълен аминокиселинен профил при всяко хранително предложение.")
        if 'dairy_free' in food_raw:
            flags.append("⚠ БЕЗ ЛАКТОЗА: Не препоръчвай суроватъчен протеин, сирена или мляко. "
                         "Алтернативи: грахов протеин, яйца, пилешко, риба, тофу.")

    if not sections and not flags:
        return ""

    block  = LBL['header'] + "\n\n"
    block += "\n\n".join(sections)
    if flags:
        if sections:
            block += "\n\n"
        block += LBL['priority'] + "\n"
        block += "\n".join(flags)
    block += "\n\n" + LBL['footer']
    return block


# ═══════════════════════════════════════════════════════════
# EMAIL SENDING
# Railway BLOCKS outbound SMTP (ports 25/465/587) on Free/Trial/
# Hobby plans — Gmail SMTP will silently time out there.
# Primary channel: Resend HTTPS API (works on ALL Railway plans).
# Railway env vars:
#   RESEND_API_KEY = re_xxxxxxxx        (from resend.com, free tier)
#   MAIL_FROM      = APEX PULSE PRO <coach@apexpulse.pro>
# Fallback: Gmail SMTP (only works on Railway Pro plan).
# ═══════════════════════════════════════════════════════════
import json as _json
import urllib.request as _urlreq

def send_email(to_addr: str, subject: str, body: str, reply_to: str = "") -> bool:
    """Send a plain-text email. Returns True if accepted by a provider."""
    # 1) Resend HTTPS API — survives Railway's SMTP block
    resend_key = os.getenv('RESEND_API_KEY', '')
    mail_from = os.getenv('MAIL_FROM', 'APEX PULSE PRO <onboarding@resend.dev>')
    if resend_key:
        try:
            payload = {"from": mail_from, "to": [to_addr], "subject": subject, "text": body}
            if reply_to:
                payload["reply_to"] = reply_to
            req = _urlreq.Request(
                "https://api.resend.com/emails",
                data=_json.dumps(payload).encode(),
                headers={
                    "Authorization": f"Bearer {resend_key}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    # Cloudflare in front of Resend blocks the default
                    # "Python-urllib" signature with error 1010 — identify properly
                    "User-Agent": "ApexPulsePro/1.0 (+https://apexpulse.pro)",
                },
                method="POST",
            )
            with _urlreq.urlopen(req, timeout=10) as resp:
                if 200 <= resp.status < 300:
                    return True
                print(f"[email] Resend HTTP {resp.status}: {resp.read()[:200]}")
        except Exception as e:
            # Print the FULL Resend response body — it contains the exact reason
            detail = ''
            try:
                if hasattr(e, 'read'):
                    detail = e.read().decode()[:300]
            except Exception:
                pass
            print(f"[email] Resend error: {e} | from={mail_from!r} | detail: {detail}")
    # 2) Gmail SMTP fallback (works only on Railway Pro plan)
    gmail_user = os.getenv('GMAIL_USER', '')
    gmail_pass = os.getenv('GMAIL_APP_PASSWORD', '')
    if gmail_user and gmail_pass:
        try:
            import smtplib
            from email.mime.text import MIMEText
            msg = MIMEText(body, 'plain', 'utf-8')
            msg['From'] = gmail_user
            msg['To'] = to_addr
            msg['Subject'] = subject
            if reply_to:
                msg['Reply-To'] = reply_to
            with smtplib.SMTP_SSL('smtp.gmail.com', 465, timeout=10) as smtp:
                smtp.login(gmail_user, gmail_pass)
                smtp.send_message(msg)
            return True
        except Exception as e:
            print(f"[email] Gmail SMTP error (expected on Railway non-Pro plans): {e}")
    else:
        if not resend_key:
            print('[email] WARNING: neither RESEND_API_KEY nor GMAIL credentials configured')
    return False


# ═══════════════════════════════════════════════════════════
# EMAIL FOLLOW-UP SEQUENCE
# Triggered when a free user submits their email for bonus messages.
# - T+24h: check-in + paid plan invite
# - T+72h: APEX50 discount code (50% off)
#
# Runs in a daemon thread; state is in-memory (resets on redeploy).
# Acceptable: the user already received the immediate welcome email.
# Max 5 000 active entries — older ones are evicted automatically.
# ═══════════════════════════════════════════════════════════
_email_sequences = {}  # email -> {email, lang, enrolled_at, sent_24h, sent_72h}


def _schedule_email_sequence(email: str, lang: str):
    if email not in _email_sequences and len(_email_sequences) < 5000:
        _email_sequences[email] = {
            'email': email,
            'lang': lang,
            'enrolled_at': time.time(),
            'sent_24h': False,
            'sent_72h': False,
        }


def _send_seq_24h(seq: dict):
    email, lang = seq['email'], seq['lang']
    if lang == 'bg':
        subject = 'Как вървят тренировките? 💪'
        body = (
            "Здравей!\n\n"
            "Вчера поиска план от APEX PULSE PRO — надяваме се, че вече тренираш по него. 🏋️\n\n"
            "Имаш ли въпроси? Нещо да коригираме в програмата?\n"
            "Питай директно — AI треньорът чака.\n\n"
            "https://apexpulse.pro/app\n\n"
            "─────────────────────────────────────\n"
            "Ако искаш AI треньор без никакви лимити, който помни целите ти 30 дни наред:\n\n"
            "→ APEX CORE — €9.99 / 30 дни  (€0.33/ден, неограничени съобщения)\n"
            "→ APEX PRO  — €14.99 / 30 дни (gpt-4o, по-детайлни програми)\n\n"
            "https://apexpulse.pro/app\n"
            "─────────────────────────────────────\n\n"
            "Продължавай — резултатите идват с последователност. 🔥\n\n"
            "APEX PULSE PRO\n"
        )
    else:
        subject = 'How are the workouts going? 💪'
        body = (
            "Hey!\n\n"
            "Yesterday you asked APEX PULSE PRO for a plan — hope you're already training with it! 🏋️\n\n"
            "Any questions? Anything you'd like to adjust in the program?\n"
            "Just ask — your AI coach is ready.\n\n"
            "https://apexpulse.pro/app\n\n"
            "─────────────────────────────────────\n"
            "Want an AI coach with no limits that remembers your goals for 30 days straight:\n\n"
            "→ APEX CORE — €9.99 / 30 days  (€0.33/day, unlimited messages)\n"
            "→ APEX PRO  — €14.99 / 30 days (gpt-4o, more detailed programs)\n\n"
            "https://apexpulse.pro/app\n"
            "─────────────────────────────────────\n\n"
            "Stay consistent — results follow dedication. 🔥\n\n"
            "APEX PULSE PRO\n"
        )
    ok = send_email(email, subject, body)
    print(f'[email-seq] 24h {"sent" if ok else "FAILED"} → {email[:30]}')


def _send_seq_72h(seq: dict):
    email, lang = seq['email'], seq['lang']
    if lang == 'bg':
        subject = 'Специална оферта — 50% отстъпка за теб 🎁'
        body = (
            "Здравей!\n\n"
            "Преди 3 дни опита APEX PULSE PRO. Исках да те наградя с нещо специално:\n\n"
            "╔══════════════════════════════════╗\n"
            "║   50% ОТСТЪПКА — ПРОМО КОД:     ║\n"
            "║                                  ║\n"
            "║           APEX50                 ║\n"
            "║                                  ║\n"
            "╚══════════════════════════════════╝\n\n"
            "Приложи при плащане и вземи 30 дни на половин цена:\n"
            "→ APEX CORE: €5.00 (вместо €9.99)\n"
            "→ APEX PRO:  €7.50 (вместо €14.99)\n\n"
            "Активирай тук: https://apexpulse.pro/app\n\n"
            "Тази оферта е само за теб и е времеограничена.\n\n"
            "APEX PULSE PRO\n"
        )
    else:
        subject = 'Special offer — 50% off just for you 🎁'
        body = (
            "Hey!\n\n"
            "3 days ago you tried APEX PULSE PRO. I wanted to reward you:\n\n"
            "╔══════════════════════════════════╗\n"
            "║   50% OFF — PROMO CODE:          ║\n"
            "║                                  ║\n"
            "║           APEX50                 ║\n"
            "║                                  ║\n"
            "╚══════════════════════════════════╝\n\n"
            "Apply at checkout for 30 days at half price:\n"
            "→ APEX CORE: €5.00 (instead of €9.99)\n"
            "→ APEX PRO:  €7.50 (instead of €14.99)\n\n"
            "Activate here: https://apexpulse.pro/app\n\n"
            "This offer is just for you and is time-limited.\n\n"
            "APEX PULSE PRO\n"
        )
    ok = send_email(email, subject, body)
    print(f'[email-seq] 72h {"sent" if ok else "FAILED"} → {email[:30]}')


def _email_sequence_worker():
    """Daemon thread: wakes every 10 min, sends due follow-ups, evicts finished entries."""
    while True:
        time.sleep(10 * 60)
        now = time.time()
        for email in list(_email_sequences.keys()):
            seq = _email_sequences.get(email)
            if not seq:
                continue
            elapsed = now - seq['enrolled_at']
            if not seq['sent_24h'] and elapsed >= 24 * 3600:
                try:
                    _send_seq_24h(seq)
                except Exception as exc:
                    print(f'[email-seq] 24h error for {email[:30]}: {exc}')
                seq['sent_24h'] = True
            if not seq['sent_72h'] and elapsed >= 72 * 3600:
                try:
                    _send_seq_72h(seq)
                except Exception as exc:
                    print(f'[email-seq] 72h error for {email[:30]}: {exc}')
                seq['sent_72h'] = True
                del _email_sequences[email]  # sequence complete — free memory


threading.Thread(target=_email_sequence_worker, daemon=True, name='email-seq').start()


def make_token(expiry_timestamp: int, plan: str = "core") -> str:
    """Create a signed access token that ALSO encodes the paid plan.
    Format v2: base64(expiry.plan.signature) — signature covers expiry+plan,
    so the frontend can no longer claim PRO after paying for CORE."""
    if plan not in PLANS:
        plan = "core"
    payload = f"{expiry_timestamp}.{plan}"
    signature = hmac.new(SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()[:32]
    token = base64.urlsafe_b64encode(f"{payload}.{signature}".encode()).decode().rstrip("=")
    return token


# EU Directive 2023/2673 — tokens withdrawn under right-of-withdrawal are
# added here so verify_token() rejects them even if the user kept a copy.
# Persisted to disk within the same Railway instance; survives process restarts
# but not redeployments (Railway ephemeral filesystem). The withdrawal email to
# coach@apexpulse.pro remains the durable audit trail.
_REVOKED_FILE = os.path.join(os.path.dirname(__file__), 'data', 'revoked_tokens.json')

def _load_revoked():
    try:
        os.makedirs(os.path.dirname(_REVOKED_FILE), exist_ok=True)
        with open(_REVOKED_FILE, 'r') as f:
            data = _json_lib.load(f)
            return set(data) if isinstance(data, list) else set()
    except Exception:
        return set()

def _save_revoked(token_set):
    try:
        os.makedirs(os.path.dirname(_REVOKED_FILE), exist_ok=True)
        with open(_REVOKED_FILE, 'w') as f:
            _json_lib.dump(list(token_set), f)
    except Exception as e:
        print(f'[revoked] disk write failed: {e}')

_revoked_tokens = _load_revoked()


def verify_token(token: str):
    """Verify a token. Returns (is_valid, plan).
    - DEV_TOKEN → (True, 'pro')
    - v2 tokens (expiry.plan.sig) → plan comes from the signed payload
    - v1 legacy tokens (expiry.sig) → treated as 'core' (existing customers keep access)
    - Tokens in _revoked_tokens (user invoked withdrawal) → (False, None)
    """
    if DEV_TOKEN and token == DEV_TOKEN:
        return True, "pro"
    if token in _revoked_tokens:
        return False, None
    try:
        padded = token + "=" * (-len(token) % 4)
        decoded = base64.urlsafe_b64decode(padded).decode()
        parts = decoded.split(".")
        if len(parts) == 3:  # v2: expiry.plan.signature
            expiry_str, plan, signature = parts
            payload = f"{expiry_str}.{plan}"
        elif len(parts) == 2:  # v1 legacy: expiry.signature
            expiry_str, signature = parts
            plan = "core"
            payload = expiry_str
        else:
            return False, None
        if time.time() > int(expiry_str):
            return False, None
        full = hmac.new(SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
        # Try 32-char (new) first, then 16-char (legacy) for tokens issued before #12 fix
        if hmac.compare_digest(signature, full[:32]) or hmac.compare_digest(signature, full[:16]):
            return True, (plan if plan in PLANS else "core")
        return False, None
    except Exception:
        return False, None


# ═══════════════════════════════════════════════════════════
# SECURITY HEADERS — added to every response
# ═══════════════════════════════════════════════════════════

@app.after_request
def add_security_headers(response):
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    # microphone=(self): the browser mic is allowed for our own origin only, so
    # native SpeechRecognition can run for the voice conversation. Camera and
    # geolocation stay fully disabled.
    response.headers['Permissions-Policy'] = 'camera=(), microphone=(self), geolocation=()'
    return response


# ═══════════════════════════════════════════════════════════
# ROUTES
# / → Landing page (premium marketing + quick goals + pricing)
# /app → Chat interface (minimal, ChatGPT-style)
# ═══════════════════════════════════════════════════════════

@app.route("/")
def landing():
    """Premium landing page — first impression for new visitors."""
    return render_template("landing.html")


@app.route("/en")
def landing_en():
    """English-only landing tuned for Western European premium audience (DE/SE/NL)."""
    return render_template("landing_en.html")


@app.route("/app")
def app_chat():
    """APEX V3 — the AI Operating System shell. The landing page, alive."""
    return render_template("apex.html")


# ═══════════════════════════════════════════════════════════
# AUTH — passwordless magic-link. Email is the canonical identity.
# ═══════════════════════════════════════════════════════════
_auth_rate = {}  # email -> [timestamps] (throttle magic-link requests)

@app.route("/auth/request", methods=["POST"])
def auth_request():
    data = request.get_json(silent=True) or {}
    email = str(data.get("email", "")).strip().lower()
    lang = "en" if str(data.get("lang", "bg")).lower() == "en" else "bg"
    if not email or "@" not in email or len(email) > 320:
        return jsonify({"error": "invalid_email"}), 400
    # Rate limit: max 4 links / 15 min / email
    now = time.time()
    stamps = [t for t in _auth_rate.get(email, []) if now - t < 900]
    if len(stamps) >= 4:
        return jsonify({"error": "rate_limited"}), 429
    stamps.append(now); _auth_rate[email] = stamps
    try:
        uid = store.get_or_create_user(email)
        if not uid:
            return jsonify({"error": "invalid_email"}), 400
        raw = store.create_login_token(uid)
        host = os.getenv("APP_URL", "https://" + request.host).rstrip("/")
        link = f"{host}/auth/verify?token={raw}"
        if lang == "en":
            subject = "Your APEX sign-in link"
            body = (f"Sign in to APEX PULSE PRO:\n\n{link}\n\n"
                    "This link expires in 20 minutes and can be used once.\n"
                    "If you didn't request it, ignore this email.")
        else:
            subject = "Твоят вход в APEX"
            body = (f"Влез в APEX PULSE PRO:\n\n{link}\n\n"
                    "Връзката е валидна 20 минути и е за еднократна употреба.\n"
                    "Ако не си я поискал — игнорирай този имейл.")
        send_email(email, subject, body)
    except Exception as e:
        print(f"[auth] request failed: {e}")
        return jsonify({"error": "server_error"}), 500
    return jsonify({"ok": True})


@app.route("/auth/verify")
def auth_verify():
    raw = request.args.get("token", "")
    uid = None
    try:
        uid = store.consume_login_token(raw)
    except Exception as e:
        print(f"[auth] verify failed: {e}")
    if not uid:
        return redirect("/app?auth=invalid")
    sid = store.create_session(uid)
    resp = make_response(redirect("/app?auth=ok"))
    _set_session_cookie(resp, sid)
    return resp


@app.route("/auth/logout", methods=["POST"])
def auth_logout():
    sid = request.cookies.get(SESSION_COOKIE)
    if sid:
        try: store.revoke_session(sid)
        except Exception: pass
    resp = make_response(jsonify({"ok": True}))
    resp.delete_cookie(SESSION_COOKIE, samesite="Lax", secure=COOKIE_SECURE)
    return resp


@app.route("/auth/me")
def auth_me():
    """Every page load calls this — server-authoritative identity + subscription."""
    if not g.get("user"):
        return jsonify({"authenticated": False, "plan": "free", "status": "free"})
    sub = store.get_subscription(g.user["id"])
    return jsonify({
        "authenticated": True,
        "email": g.user["email"],
        "plan": sub["plan"],
        "status": sub["status"],
        "current_period_end": sub["current_period_end"],
    })


def _require_user():
    return g.get("user")


# ═══════════════════════════════════════════════════════════
# ACCOUNT DATA API — profile / history / memory (account-owned)
# ═══════════════════════════════════════════════════════════
@app.route("/api/profile", methods=["GET", "PUT"])
def api_profile():
    u = _require_user()
    if not u:
        return jsonify({"error": "unauthenticated"}), 401
    if request.method == "GET":
        return jsonify({"profile": store.get_profile(u["id"])})
    data = request.get_json(silent=True) or {}
    prof = data.get("profile")
    if not isinstance(prof, dict):
        return jsonify({"error": "invalid"}), 400
    store.save_profile(u["id"], prof)
    # M0: self-report evidence for the Athlete Model (only the consumed fields).
    _sr = {k: prof[k] for k in ("sleepQuality", "stressLevel", "recoveryFeel", "frequency") if k in prof}
    if _sr:
        athlete_store.observe(u["id"], "self_report", _sr)
    return jsonify({"ok": True})


@app.route("/api/workout", methods=["POST"])
def api_workout():
    u = _require_user()
    if not u:
        return jsonify({"error": "unauthenticated"}), 401
    data = request.get_json(silent=True) or {}
    session = data.get("session")
    if not isinstance(session, dict):
        return jsonify({"error": "invalid"}), 400
    wid = store.log_workout(u["id"], session)
    # M0: workout evidence for the Athlete Model (failure-isolated).
    athlete_store.observe(u["id"], "workout_completed", session)
    return jsonify({"ok": True, "id": wid})


@app.route("/api/history")
def api_history():
    u = _require_user()
    if not u:
        return jsonify({"error": "unauthenticated"}), 401
    return jsonify({
        "workouts": store.list_workouts(u["id"]),
        "nutrition": store.list_nutrition(u["id"]),
        "timeline": store.list_timeline(u["id"]),
    })


@app.route("/api/conversations")
def api_conversations():
    """Cross-device chat history load — the account's transcript."""
    u = _require_user()
    if not u:
        return jsonify({"error": "unauthenticated"}), 401
    try:
        limit = min(int(request.args.get("limit", 60)), 200)
    except Exception:
        limit = 60
    return jsonify({"messages": store.list_conversation(u["id"], limit=limit)})


@app.route("/api/memory", methods=["POST"])
def api_memory():
    u = _require_user()
    if not u:
        return jsonify({"error": "unauthenticated"}), 401
    data = request.get_json(silent=True) or {}
    kind = str(data.get("kind", "note"))[:32]
    payload = data.get("payload")
    store.add_memory_event(u["id"], kind, payload)
    return jsonify({"ok": True})


@app.route("/api/sync", methods=["POST"])
def api_sync():
    """One-time migration of a browser's cached data into the account on first
    sign-in, so existing users don't lose anything. Merge, never destroy."""
    u = _require_user()
    if not u:
        return jsonify({"error": "unauthenticated"}), 401
    data = request.get_json(silent=True) or {}
    prof = data.get("profile")
    if isinstance(prof, dict) and prof and not store.get_profile(u["id"]):
        store.save_profile(u["id"], prof)
    log = data.get("workoutLog")
    if isinstance(log, list) and not store.list_workouts(u["id"], limit=1):
        for s in log[-60:]:
            if isinstance(s, dict):
                try: store.log_workout(u["id"], s)
                except Exception: pass
    # Migrate cached chat transcript once (only if the account has none yet).
    conv = data.get("chatHistory")
    if isinstance(conv, list) and not store.list_conversation(u["id"], limit=1):
        for m in conv[-40:]:
            if isinstance(m, dict) and m.get("role") in ("user", "assistant") and m.get("content"):
                try: store.add_conversation(u["id"], m["role"], str(m["content"])[:4000])
                except Exception: pass
    return jsonify({"ok": True,
                    "profile": store.get_profile(u["id"]),
                    "workouts": store.list_workouts(u["id"]),
                    "conversations": store.list_conversation(u["id"], limit=60)})



_FC_SYSTEM_PROMPT_EN_ASK = """You are APEX, an exceptionally intelligent performance coach.
This is the first conversation with a new user. Your goal is to make them feel safe, understood, and heard.
Speak naturally, calmly, and with quiet confidence.

RULES:
1. Speak in plain English.
2. NEVER use AI, medical, or engineering terminology. Never use words like: calibration, physiological, signature, telemetry, optimization, processing, reasoning engine.
3. Keep responses extremely short: maximum 2 sentences, maximum 20 words per sentence.
4. Ask at most ONE question per turn to clarify missing parameters (specifically: training goal, where they train, what equipment they have, or active injuries). Never ask more than one question.
"""

_FC_SYSTEM_PROMPT_EN_PLAN = """You are APEX, an exceptionally intelligent performance coach.
This is the first conversation with a new user. Your goal is to make them feel safe, understood, and heard.
Speak naturally, calmly, and with quiet confidence.

RULES:
1. Speak in plain English.
2. NEVER use AI, medical, or engineering terminology. Never use words like: calibration, physiological, signature, telemetry, optimization, processing, reasoning engine.
3. You now have enough information to safely begin coaching. Say exactly: "I think I understand enough to get started." followed by a clean, simple list of exercises with sets and reps tailored to their goals and constraints.
"""

_FC_SYSTEM_PROMPT_EN_SAFETY = """You are APEX, an exceptionally intelligent performance coach.
The user has indicated signs of high-risk medical or safety concerns. You must prioritize their safety immediately.

RULES:
1. Speak in plain English.
2. Say exactly: "I cannot design a plan for you at this time."
3. Follow up with a single sentence instructing them to stop exertion and seek professional medical guidance.
4. Keep it under 2 sentences and 20 words per sentence. Do not offer exercises.
"""

_FC_SYSTEM_PROMPT_EN_CONTINUE = """You are APEX, an exceptionally intelligent performance coach.
Keep responses unhurried, calm, and under 2 sentences. Ask at most one question. Speak naturally, calmly, and with quiet confidence. No AI, medical, or engineering terminology.
"""

_FC_SYSTEM_PROMPT_BG_ASK = """Ти си APEX, изключително интелигентен треньор.
Това е първият ти разговор с нов потребител. Целта е да го накараш да се почувства в безопасност, разбран и чут.
Говори естествено, спокойно и с тиха увереност.

ПРАВИЛА:
1. Говори на български език.
2. НИКОГА не използвай изкуствен интелект, медицински или инженерни термини. Никога не използвай думи като: калибриране, физиологичен, телеметрия, оптимизация, обработка, двигател за разсъждения.
3. Дръж отговорите изключително кратки: максимум 2 изречения, максимум 20 думи на изречение.
4. Задавай най-много ЕДИН въпрос на реплика, за да изясниш липсващите параметри (цел, къде тренират, какво оборудване имат или контузии). Никога повече от един.
"""

_FC_SYSTEM_PROMPT_BG_PLAN = """Ти си APEX, изключително интелигентен треньор.
Това е първият ти разговор с нов потребител. Целта е да го накараш да се почувства в безопасност, разбран и чут.
Говори естествено, спокойно и с тиха увереност.

ПРАВИЛА:
1. Говори на български език.
2. НИКОГА не използвай изкуствен интелект, медицински или инженерни термини. Никога не използвай думи като: калибриране, физиологичен, телеметрия, оптимизация, обработка, двигател за разсъждения.
3. Вече имаш достатъчно информация. Кажи точно: "Мисля, че разбрах достатъчно, за да започнем." последвано от ясен, прост тренировъчен план (списък от упражнения, серии и повторения), адаптиран към техните цели и ограничения.
"""

_FC_SYSTEM_PROMPT_BG_SAFETY = """Ти си APEX, изключително интелигентен треньор.
Потребителят е посочил признаци на високорискови медицински или безопасни проблеми. Трябва незабавно да дадеш приоритет на безопасността.

ПРАВИЛА:
1. Говори на български език.
2. Кажи точно: "В момента не мога да изготвя тренировъчен план за теб."
3. Следвай това с едно изречение с указание да спрат натоварването и да потърсят лекарска помощ.
4. Дръж отговора под 2 изречения и под 20 думи на изречение. Не предлагай упражнения.
"""

_FC_SYSTEM_PROMPT_BG_CONTINUE = """Ти си APEX, изключително интелигентен треньор.
Дръж отговорите спокойни и под 2 изречения. Задавай най-много един въпрос. Говори естествено и с тиха увереност. Без изкуствен интелект, медицински или инженерни термини.
"""

def _extract_profile_silent(history_messages, current_profile):
    """
    Quietly extracts profile data from the conversation history using GPT-4o-mini.
    Returns a dict of updated profile values.
    """
    try:
        conv_text = ""
        for m in history_messages:
            role = m.get("role", "user")
            content = m.get("content", "")
            conv_text += f"{role.upper()}: {content}\n"
        
        system_content = """Analyze the conversation and extract the user's fitness profile.
Return ONLY a valid JSON object. Do not include markdown wraps or any other text.

RULES FOR EXTRACTION:
1. Store only confirmed facts. Never store guesses or unconfirmed assumptions.
2. Never store temporary emotions, transient feelings, or mood descriptions.
3. Keep values null unless they are explicitly and clearly stated by the user.

JSON structure:
{
  "name": string or null,
  "goal": string or null, # one of "fat_loss", "muscle_gain", "strength", "endurance", "general"
  "equipment": string or null, # one of "gym", "home", "none"
  "injuries": string or null, # text describing injuries/pain
  "frequency": integer or null, # number of training days
  "sleepQuality": string or null, # one of "poor", "average", "good"
  "stressLevel": string or null # one of "low", "moderate", "high"
}
Current profile values:
""" + _json.dumps(current_profile or {})

        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_content},
                {"role": "user", "content": f"Conversation history:\n{conv_text}"}
            ],
            temperature=0,
            response_format={"type": "json_object"}
        )
        extracted = _json.loads(resp.choices[0].message.content or "{}")
        updated_profile = dict(current_profile or {})
        for k, v in extracted.items():
            if v is not None:
                updated_profile[k] = v
        if "frequency" in updated_profile and updated_profile["frequency"] is not None:
            updated_profile["frequency"] = str(updated_profile["frequency"])
        return updated_profile
    except Exception as e:
        print(f"[first-contact] silent extraction failed: {e}")
        return current_profile or {}


from brain.learning.schema import HumanModel
from brain.learning.engine import HumanLearningEngine

def _update_learning_engine(uid, user_msg, assistant_reply, current_profile):
    model = HumanModel(current_profile)
    HumanLearningEngine.process_exchange(model, user_msg, assistant_reply)
    updated_profile = model.to_dict()
    for k, v in updated_profile.items():
        current_profile[k] = v
    if uid:
        try:
            store.save_profile(uid, current_profile)
        except Exception as e:
            print(f"[learning] save_profile failed: {e}")


def _daily_nutrition_target(message, profile_block, history=None):
    """Return the injected calorie target for an explicit full-day request."""
    if not nutrition_validation.is_full_day_request(message, history):
        return None
    match = re.search(r"(?:Calorie target|Калориен таргет):\s*([\d\s,]+)\s*(?:kcal|ккал)",
                      str(profile_block or ""), re.IGNORECASE)
    return int(re.sub(r"\D", "", match.group(1))) if match else 0


def _daily_nutrition_targets(message, profile_block, history=None):
    if not nutrition_validation.is_full_day_request(message, history):
        return None
    return nutrition_validation.targets_from_profile_block(profile_block)


def _daily_nutrition_format_rules(targets, lang):
    """Strict, model-facing output rules so the FIRST daily-plan generation
    naturally satisfies the deterministic validator. The validator itself is
    never weakened or bypassed — this only teaches the model the exact shape and
    arithmetic the validator already requires (structure, complete food rows,
    one reconciled Daily Total within 5% of the authoritative targets)."""
    def _n(v):
        return None if v is None else str(int(v))
    tlines = ["Calories: %s kcal" % _n(targets.kcal)]
    if getattr(targets, "protein", None) is not None: tlines.append("Protein: %s g" % _n(targets.protein))
    if getattr(targets, "carbs", None) is not None: tlines.append("Carbs: %s g" % _n(targets.carbs))
    if getattr(targets, "fat", None) is not None: tlines.append("Fat: %s g" % _n(targets.fat))
    targets_txt = "\n".join("- " + t for t in tlines)
    if str(lang).lower() == "bg":
        return (
            "[ФОРМАТ НА ДНЕВНИЯ ХРАНИТЕЛЕН ПЛАН — ЗАДЪЛЖИТЕЛЕН]\n"
            "Върни САМО един дневен план: заглавия на храненията на отделни редове + редове с храни в pipe формат. "
            "Без въведение, без заключение, без коментари и БЕЗ изречения, че потребителят може да добави/увеличи/промени "
            "храна, порции или калории, и без да го наричаш „базов план“.\n"
            "Структура (точно този ред): Закуска, после Обяд, после Вечеря — и трите са ЗАДЪЛЖИТЕЛНИ и всяко има поне една храна. "
            "„Снак“ е по избор и само МЕЖДУ Закуска и Обяд или МЕЖДУ Обяд и Вечеря. Вечеря винаги е последното хранене. "
            "Никога снак след Вечеря. Никога не повтаряй хранене.\n"
            "Всяко хранене е един ред само със заглавието на отделен ред: Закуска / Обяд / Вечеря / Снак.\n"
            "Всяка храна е един ред с точно тези шест клетки в този ред:\n"
            "| Име на храната | Количество | Протеин | Въглехидрати | Мазнини | Калории |\n"
            "Количеството съдържа число и мерна единица, напр. „80 г“. Протеин, Въглехидрати и Мазнини са грамове, Калории са kcal — "
            "всички са положителни числа, всяка клетка е попълнена, а Калории > 0.\n"
            "Завърши с точно ЕДИН ред за общото и нищо след него:\n"
            "| Общо за деня | <сумаПротеин> | <сумаВъглехидрати> | <сумаМазнини> | <сумаКалории> |\n"
            "Събери всяка колона по ВСИЧКИ храни и запиши точните аритметични суми. Редът „Общо за деня“ ТРЯБВА да е равен на сумите "
            "(протеин/въглехидрати/мазнини с точност до 1 г, калории до 10 kcal).\n"
            "Постигни тези дневни таргети — „Общо за деня“ трябва да е в рамките на 5% от всеки:\n"
            + targets_txt + "\n"
            "Преди да завършиш: събери колоните сам, потвърди че „Общо за деня“ съвпада със сумите и е в 5% от всеки таргет, и че "
            "Закуска, Обяд и Вечеря присъстват. Ако нещо не съвпада, коригирай грамажите на храните и събери отново."
        )
    return (
        "[DAILY NUTRITION PLAN FORMAT — MANDATORY]\n"
        "Return ONLY one daily plan: meal headers on their own lines + pipe-delimited food rows. "
        "No introduction, no closing text, no coaching notes, and NO sentence suggesting the user add, increase or adjust "
        "food, portions or calories, and never call it a \"base plan\".\n"
        "Structure (this exact order): Breakfast, then Lunch, then Dinner — all three are REQUIRED and each has at least one food. "
        "A \"Snack\" is optional and only BETWEEN Breakfast and Lunch or BETWEEN Lunch and Dinner. Dinner is always the last meal. "
        "Never a snack after Dinner. Never repeat a meal.\n"
        "Each meal is one line with only its header on its own line: Breakfast / Lunch / Dinner / Snack.\n"
        "Each food is one row with exactly these six cells in this order:\n"
        "| Food name | Quantity | Protein | Carbs | Fat | Kcal |\n"
        "Quantity includes a number and unit, e.g. \"80 g\". Protein, Carbs and Fat are grams and Kcal is calories — "
        "all positive numbers, every cell filled, and Kcal > 0.\n"
        "End with exactly ONE totals row and nothing after it:\n"
        "| Daily Total | <sumProtein> | <sumCarbs> | <sumFat> | <sumKcal> |\n"
        "Add each column across ALL foods and write the exact arithmetic sums. The Daily Total MUST equal the summed foods "
        "(protein/carbs/fat within 1 g, calories within 10 kcal).\n"
        "Hit these daily targets — the Daily Total must be within 5% of each:\n"
        + targets_txt + "\n"
        "Before finishing: sum the columns yourself, confirm the Daily Total matches the sums and is within 5% of every target, "
        "and confirm Breakfast, Lunch and Dinner are all present. If anything is off, adjust the food amounts and re-sum."
    )


def _shadow_recommendation(snapshot, decision, profile):
    """Generate a non-persistent blueprint without affecting chat delivery."""
    if decision.outcome != "recommend":
        return None
    kind = "workout" if decision.intent == "workout" else "nutrition"
    print(f"[recommendation-shadow] invoked type={kind}")
    try:
        blueprint = recommendation_architect.design(
            kind,
            decision=decision,
            profile=profile if isinstance(profile, dict) else {},
            preferences={},
            subject=snapshot.subject.identifier,
            record=False,
        )
        if blueprint is None:
            print(f"[recommendation-shadow] failed type={kind}")
        else:
            print(f"[recommendation-shadow] blueprint generated type={blueprint.kind}")
        return blueprint
    except Exception as error:
        print(f"[recommendation-shadow] failed type={kind}: {error}")
        return None


def _recommendation_engine_active():
    return os.getenv("RECOMMENDATION_ENGINE_ACTIVE", "false").strip().lower() == "true"


def _conversation_composer_active():
    return os.getenv("CONVERSATION_COMPOSER_ACTIVE", "false").strip().lower() == "true"


def _shadow_feature_enabled(name):
    return os.getenv(name, "false").strip().lower() == "true"


def _observe_shadow_trace_for_testing(trace):
    """No-op test seam; request-local traces are never retained or delivered."""
    return None


def _evaluate_persona_expert(snapshot, decision, recommendation_engine_active):
    """Evaluate existing pure assets without persistence, delivery, or logging."""
    try:
        matcher_started = time.perf_counter()
        match = persona_matcher.match(snapshot, decision.intent)
        matcher_ms = (time.perf_counter() - matcher_started) * 1000
        consensus_started = time.perf_counter()
        consensus = expert_consensus.evaluate(snapshot, match, decision.intent)
        consensus_ms = (time.perf_counter() - consensus_started) * 1000
        trace = shadow_trace.build_shadow_trace(
            request_id=_uuid.uuid4().hex,
            timestamp=_dt.datetime.now(_dt.timezone.utc),
            persona_match=match,
            expert_consensus=consensus,
            matcher_ms=matcher_ms,
            consensus_ms=consensus_ms,
            recommendation_engine_active=recommendation_engine_active,
        )
        return match, consensus, trace
    except Exception:
        return None, None, None


def _shadow_persona_expert(snapshot, decision, recommendation_engine_active):
    """Run detached archetype/rule analysis only; it never changes chat delivery."""
    matcher_enabled = _shadow_feature_enabled("PERSONA_MATCHER_SHADOW")
    consensus_enabled = _shadow_feature_enabled("EXPERT_CONSENSUS_SHADOW")
    if decision.outcome != "recommend" or not (matcher_enabled or consensus_enabled):
        return None, None, None
    match, consensus, trace = _evaluate_persona_expert(snapshot, decision, recommendation_engine_active)
    return (match if matcher_enabled else None), (consensus if consensus_enabled else None), trace


def _persona_adaptation(match):
    """Project a matched runtime persona into ID-free workout design inputs."""
    persona_id = getattr(match, "primary_persona_id", None)
    if not persona_id:
        return None
    persona = next((item for item in load_runtime_personas() if item.id == persona_id), None)
    if persona is None:
        return None
    return {
        "beginner": persona.experience_level == "beginner" or "beginners_deconditioned" in persona.cluster,
        "advanced": persona.experience_level == "advanced" or "athletes_advanced" in persona.cluster,
        "home_equipment": persona.equipment_context == "home",
    }


def _workout_authority(snapshot, decision):
    """Project verified request facts into the architect's immutable boundary."""
    if snapshot.intent != "workout" or decision.intent != "workout":
        return None
    facts = {key: fact.value for key, fact in snapshot.profile.items()}
    explicit = {key: fact.value for key, fact in snapshot.profile.items()
                if fact.source in {"explicit", "locked"}}
    locked = snapshot.locked_preferences.as_dict()
    locked_equipment = tuple(locked.get("equipment", ()))
    if len(locked_equipment) > 1:
        return None
    equipment = locked_equipment or tuple(_as_list(facts.get("equipment")))
    injury_values = tuple(_as_list(facts.get("injuries"))) + tuple(_as_list(facts.get("healthNotes")))
    safety = {str(value).strip().lower() for value in injury_values if str(value).strip()}
    if safety:
        safety.update({"squat", "hinge", "conditioning"})
    recovery = facts.get("recoveryFeel")
    try:
        return recommendation_architect.WorkoutAuthority(
            intent="workout", verified_facts=facts, explicit_facts=explicit,
            locked_preferences=locked, safety_constraints=tuple(sorted(safety)),
            equipment=equipment, experience=str(facts.get("level") or facts.get("experience_level") or "") or None,
            recovery_state=str(recovery) if recovery is not None else None,
            workout_history=snapshot.workouts,
        )
    except Exception:
        return None


def _as_list(value):
    if value is None:
        return ()
    if isinstance(value, (tuple, list, set, frozenset)):
        return tuple(value)
    return (value,)


def _active_workout_recommendation(snapshot, decision, recommendation_engine_active):
    """Use persona/expert evidence only when at least one system can act on it."""
    authority = _workout_authority(snapshot, decision)
    if authority is None:
        return None, None, "legacy"
    match, consensus, trace = _evaluate_persona_expert(snapshot, decision, recommendation_engine_active)
    if match is None or consensus is None or (match.abstained and consensus.abstained):
        return None, trace, "legacy"
    try:
        blueprint = recommendation_architect.design(
            "workout", decision=decision, profile={},
            preferences=dict(authority.locked_preferences), subject=snapshot.subject.identifier, record=False,
            expert_consensus=consensus,
            persona_adaptation=_persona_adaptation(match), authority=authority,
        )
        return blueprint, trace, "persona_expert" if blueprint is not None else "legacy"
    except Exception:
        return None, trace, "legacy"


@app.route("/chat", methods=["POST"])
def chat():
    try:
        data = request.json or {}
        token = data.get("token", "")
        is_first_contact = bool(data.get("first_contact", False))
        
        # Plan is SERVER-AUTHORITATIVE: DB subscription first (logged-in accounts),
        # then a signed legacy token as fallback for pre-account payers, then dev.
        db_plan, db_status = _current_plan_status()
        tok_valid, token_plan = (verify_token(token) if token else (False, None))
        is_dev = bool(DEV_TOKEN) and token == DEV_TOKEN
        plan = db_plan
        if plan == "free" and tok_valid:
            plan = token_plan or "core"
        if is_dev:
            plan = "pro"
        is_elite = is_dev or plan in ("core", "pro")
        is_pro = is_dev or plan == "pro"

        # SESSION_START — the voice layer opens a conversation with no user words.
        # It is NOT a separate reasoning path: it enters this same /chat pipeline,
        # so the greeting is produced by the very same Personality + profile + history
        # (+ Brain, when enforced) as every other turn. Single reasoning entry point.
        session_start = bool(data.get("session_start"))
        voice_requested = bool(data.get("voice"))
        daypart = str(data.get("daypart", ""))[:12]

        msg_limit = 4000 if is_elite else 1000
        user_message = "" if session_start else str(data.get("message", ""))[:msg_limit]
        history = data.get("history", [])
        profile = data.get("profile") or {}
        lang = str(data.get("lang", "bg")).lower()
        if lang not in ("bg", "en"):
            lang = "bg"

        # Transport stop is intentionally not a coaching turn. It settles the
        # existing browser stream without invoking quota, persistence, or the LLM.
        if not session_start and conversation_composer.is_exact_stop_command(user_message):
            return Response(
                'data: {"done": true}\n\n',
                mimetype="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )

        # ── SERVER-AUTHORITATIVE FREE LIMIT ──
        free_subject = None
        if not is_elite and not session_start:   # a greeting is free — it never spends a daily message
            free_subject = ("user", str(g.user["id"])) if g.get("user") else ("device", g.device_id or _client_ip())
            q = store.free_usage_consume(free_subject[0], free_subject[1],
                                         FREE_DAILY_LIMIT, FREE_WINDOW_SECONDS, LEAD_BONUS)
            if not q["allowed"]:
                return jsonify({"limit_reached": True, "hours_left": q["hours_left"], "remaining": 0}), 200

        chat_uid = str(g.user["id"]) if g.get("user") else None
        pers_workouts = []
        if chat_uid:
            db_profile = store.get_profile(chat_uid)
            if db_profile:
                profile = db_profile
            try:
                mem = store.build_memory_context(chat_uid, en=(lang == "en"))
                if mem:
                    profile = dict(profile or {})
                    profile["workoutContext"] = mem
            except Exception as _me:
                print(f"[chat] memory build failed: {_me}")
            try:
                pers_workouts = store.list_workouts(chat_uid, limit=40)
            except Exception as _we:
                print(f"[chat] workout load failed: {_we}")

        if is_elite:
            memory_cap = 60 if is_pro else 10
        else:
            memory_cap = 12

        if chat_uid:
            try:
                history = store.list_conversation(chat_uid, limit=memory_cap)
            except Exception as _ce:
                print(f"[chat] conversation load failed: {_ce}")

        # Phase A2 compatibility bridge: ContextSnapshot now owns the normal-chat
        # context boundary, then its legacy adapter restores the exact variables
        # consumed by the unchanged prompt assembly below. First-contact keeps its
        # established path until its own integration phase.
        _recommendation_blueprint = None
        _recommendation_trace = None
        _recommendation_path = "legacy"
        _recommendation_active = _recommendation_engine_active()
        _conversation_composer_active_for_request = _conversation_composer_active()
        _conversation_policy = None
        _conversation_frame = None
        if not is_first_contact:
            _legacy_profile = profile if isinstance(profile, dict) else {}
            _legacy_history = history if isinstance(history, list) else []
            _shadow_intent = decision_engine.classify_intent(user_message)
            _snapshot = context_builder.build_context(
                intent=_shadow_intent,
                subject=(context_builder.Subject("account", chat_uid, True)
                         if chat_uid else
                         context_builder.Subject("anonymous_device", g.device_id or _client_ip(), False)),
                request_time=_dt.datetime.now(_dt.timezone.utc),
                access={"plan": plan, "quota_status": db_status},
                db_profile=_legacy_profile if chat_uid else None,
                browser_profile=_legacy_profile if not chat_uid else None,
                db_conversation=_legacy_history if chat_uid else None,
                browser_conversation=_legacy_history if not chat_uid else None,
                db_workouts=pers_workouts if chat_uid else None,
                legacy_profile=_legacy_profile,
                legacy_conversation=_legacy_history,
                legacy_workouts=pers_workouts,
            )
            _legacy = _snapshot.legacy_prompt_projection(conversation_limit=len(_legacy_history)).prompt_variables()
            if isinstance(profile, dict):
                profile = _legacy["profile"]
            if isinstance(history, list):
                history = _legacy["history"]
            pers_workouts = _legacy["workouts"]
            _shadow_decision = decision_engine.decide(_snapshot, _shadow_intent)
            _active_workout = (_recommendation_active and _shadow_decision.outcome == "recommend" and
                               _shadow_decision.intent == "workout")
            if _active_workout:
                (_recommendation_blueprint, _recommendation_trace,
                 _recommendation_path) = _active_workout_recommendation(
                     _snapshot, _shadow_decision, _recommendation_active)
            else:
                (_shadow_persona_match, _shadow_expert_consensus,
                 _recommendation_trace) = _shadow_persona_expert(
                     _snapshot, _shadow_decision, _recommendation_active)
            _controlled_reply = decision_engine.controlled_response(_shadow_decision, lang)
            if _conversation_composer_active_for_request:
                try:
                    _conversation_policy = conversation_composer.build_policy(
                        decision=_shadow_decision, message=user_message, conversation=history,
                        voice=voice_requested, session_start=session_start,
                        blueprint_present=_recommendation_blueprint is not None,
                        recommendation_kind=getattr(_recommendation_blueprint, "kind", None),
                        structured_delivery=_recommendation_blueprint is not None,
                    )
                except Exception as _composer_error:
                    print(f"[conversation-composer] policy failed: {_composer_error}")
            if not _recommendation_active:
                _shadow_recommendation(_snapshot, _shadow_decision, profile)
            if _recommendation_trace is not None:
                _observe_shadow_trace_for_testing(_recommendation_trace.with_delivery(
                    blueprint_invoked=_recommendation_blueprint is not None,
                    production_path_used=_recommendation_path))
        else:
            _controlled_reply = None

        decision_state = "CONTINUE_CONVERSATION"
        if is_first_contact:
            # 1. Understanding: Silent extraction (updates the Human State profile)
            # Safe conversation history wrapper
            history_for_extract = []
            if isinstance(history, list):
                for m in history:
                    if isinstance(m, dict) and m.get("role") in ("user", "assistant"):
                        history_for_extract.append(m)
            history_for_extract.append({"role": "user", "content": user_message})
            profile = _extract_profile_silent(history_for_extract, profile)
            
            # Ingest safety flags inside the Understanding layer
            from brain.redflag_library import detect_flag_classes
            flags = set(profile.get("red_flags") or [])
            for cls in detect_flag_classes(user_message):
                flags.add(cls)
            profile["red_flags"] = list(flags)
            
            # 2. Brain Evaluation: Passes ONLY the structured Human State (profile) and physiology
            _phys = athlete_store.physiology(chat_uid) if chat_uid else None
            _decision = brain_cascade.decide(profile, physiology=_phys, model=model_to_use)
            
            # 3. Decision mapping
            if _decision.s2.halt:
                decision_state = "SAFETY_STOP"
            else:
                has_goal = bool(str(profile.get("goal") or "").strip())
                has_equip = bool(str(profile.get("equipment") or "").strip())
                if has_goal and has_equip:
                    decision_state = "PLAN_READY"
                elif has_goal or has_equip:
                    decision_state = "NEED_MORE_INFORMATION"
                else:
                    decision_state = "CONTINUE_CONVERSATION"
            
            # 4. System prompt selection based ONLY on Decision
            if lang == "en":
                prompts = {
                    "SAFETY_STOP": _FC_SYSTEM_PROMPT_EN_SAFETY,
                    "PLAN_READY": _FC_SYSTEM_PROMPT_EN_PLAN,
                    "NEED_MORE_INFORMATION": _FC_SYSTEM_PROMPT_EN_ASK,
                    "CONTINUE_CONVERSATION": _FC_SYSTEM_PROMPT_EN_CONTINUE
                }
            else:
                prompts = {
                    "SAFETY_STOP": _FC_SYSTEM_PROMPT_BG_SAFETY,
                    "PLAN_READY": _FC_SYSTEM_PROMPT_BG_PLAN,
                    "NEED_MORE_INFORMATION": _FC_SYSTEM_PROMPT_BG_ASK,
                    "CONTINUE_CONVERSATION": _FC_SYSTEM_PROMPT_BG_CONTINUE
                }
            system_content = prompts[decision_state]
            
            # 5. Memory: Write confirmed profile facts to store (logged-in accounts)
            if chat_uid:
                try: store.save_profile(chat_uid, profile)
                except Exception: pass
        else:
            try:
                personality_block = personality.compose(
                    lang=lang, profile=profile if isinstance(profile, dict) else {},
                    workouts=pers_workouts, message=user_message, conversation=history)
            except Exception as _pe:
                print(f"[chat] personality compose failed: {_pe}")
                personality_block = ""

            profile_block = _build_profile_block(profile, lang) if isinstance(profile, dict) else ""
            base = (profile_block + "\n\n" + SYSTEM_INSTRUCTIONS) if profile_block else SYSTEM_INSTRUCTIONS
            system_content = (personality_block + "\n\n" + base) if personality_block else base

        nutrition_delivery_targets = (_daily_nutrition_targets(user_message, profile_block, history)
                                      if not is_first_contact else None)
        nutrition_delivery_target = (int(nutrition_delivery_targets.kcal)
                                     if nutrition_delivery_targets is not None else None)
        if nutrition_delivery_targets is not None:
            system_content = system_content + "\n\n" + nutrition_validation.generation_contract(nutrition_delivery_targets)
            system_content = system_content + "\n\n" + _daily_nutrition_format_rules(nutrition_delivery_targets, lang)
        if _recommendation_blueprint is not None:
            system_content = recommendation_renderer.render_prompt(_recommendation_blueprint)
        if _conversation_policy is not None and _controlled_reply is None:
            try:
                _conversation_frame = conversation_composer.compose(
                    _conversation_policy,
                    verified_memory=history,
                    validated_blueprint=_recommendation_blueprint,
                    validated_nutrition_contract=nutrition_delivery_targets is not None,
                    authority_facts=profile if isinstance(profile, dict) else {},
                )
                system_content = system_content + "\n\n" + conversation_composer.render_prompt(
                    _conversation_frame, lang)
            except Exception as _composer_error:
                print(f"[conversation-composer] frame failed: {_composer_error}")

        messages = [{"role": "system", "content": system_content}]

        if isinstance(history, list):
            safe_history = history[-memory_cap:]
            for msg in safe_history:
                if isinstance(msg, dict) and msg.get("role") in ("user", "assistant"):
                    content = str(msg.get("content", ""))[:4000]
                    messages.append({"role": msg["role"], "content": content})

        if session_start:
            # The opening turn: the model greets in APEX's voice using everything it
            # already has (the system block above carries Personality + profile;
            # `history` above carries whether we've met). No lists, spoken aloud.
            _dp = {"morning": "It is morning for me.", "afternoon": "It is afternoon for me.",
                   "evening": "It is evening for me.", "night": "It is late at night for me."}.get(daypart, "")
            if lang == "en":
                _open = ("[SESSION START — you are opening a live, spoken conversation.] "
                         "Greet me now in your coach voice: brief and natural, one or two sentences, "
                         "to be read aloud (no lists, no markdown, no emoji). " + _dp + " "
                         "If we have trained before, acknowledge it lightly; if my goal is on file, nod to it. "
                         "End with one short, open question to begin.")
            else:
                _open = ("[НАЧАЛО НА СЕСИЯ — започваш жив, гласов разговор.] "
                         "Поздрави ме сега със своя треньорски глас: кратко и естествено, едно-две изречения, "
                         "за изговаряне на глас (без списъци, без markdown, без емоджи). " + _dp + " "
                         "Ако сме тренирали заедно, отбележи го леко; ако целта ми е записана, спомени я. "
                         "Завърши с един кратък отворен въпрос, за да започнем.")
            messages.append({"role": "user", "content": _open})
        else:
            messages.append({"role": "user", "content": user_message})

        # Model selection based on plan:
        # - PRO → gpt-4o (premium model, smarter responses, better Bulgarian)
        # - CORE / FREE → gpt-4o-mini (fast, cost-efficient)
        model_to_use = "gpt-4o" if is_pro else "gpt-4o-mini"
        
        # Response length cap:
        # - PRO → up to 4000 tokens (detailed comprehensive plans)
        # - CORE / FREE → ~1500 tokens (solid complete plans)
        # FREE users now get a generous DAILY message limit (ChatGPT-style),
        # so each individual answer is normal length — value comes from being
        # able to chat freely, not from one oversized answer.
        max_tokens = 4000 if is_pro else 1500

        # ── STREAMING (SSE) ──
        # Отговорът тече към браузъра токен по токен, както се генерира.
        # Същият брой токени, същата цена — променя се само доставката.
        refund_subject = free_subject  # (subject_type, subject_id) or None

        def sse(obj):
            return "data: " + _json.dumps(obj, ensure_ascii=False) + "\n\n"

        def _speech_event(reply_text, *, safety_response=False, preserve_visible=False):
            """Produce a separate voice-only projection without changing delivery."""
            if not voice_requested or not _conversation_composer_active_for_request:
                return None
            if preserve_visible:
                return {"speech_text": reply_text} if reply_text else None
            try:
                kind = "workout" if _recommendation_blueprint is not None else (
                    "nutrition" if nutrition_delivery_target is not None else None)
                speech_text = conversation_composer.speech_projection(
                    reply_text, _conversation_frame, lang,
                    structured_kind=kind,
                    safety_response=safety_response,
                )
                return {"speech_text": speech_text} if speech_text else None
            except Exception as _speech_error:
                print(f"[conversation-composer] speech projection failed: {_speech_error}")
                return None

        # Captured for post-stream persistence (no request context inside generator).
        persist_uid = chat_uid
        persist_user_msg = user_message
        persist_lang = lang
        persist_profile = profile if isinstance(profile, dict) else {}
        persist_conversation = history if isinstance(history, list) else []  # recent window (Addendum 02 A2-1)
        # M5 Observatory — pseudonymous subject for analytics (hashed at write time, no PII).
        persist_analytics_subject = (("user", str(g.user["id"])) if g.get("user")
                                     else ("device", g.device_id or _client_ip()))

        # ── M4 · SAFETY-FRONT ENFORCEMENT (BRAIN_ENFORCE — OFF by default) ────
        # When OFF this block is skipped entirely, so `messages` and the SSE stream
        # are byte-identical to the legacy system. When ON, the shadow Decision is
        # rendered by brain.enforcement (a pure organ): a red-flag halt / NOT_YET /
        # NO_TRAIN steers the SAME generation call to route/decline instead of a
        # workout (voice preserved), and GO/MODIFY inject S1 constraints. Failure-
        # isolated: any error falls back to legacy generation. No organ/cascade edit.
        enforce_event = None
        if _controlled_reply is None and brain_config.brain_enforce():
            try:
                _phys = athlete_store.physiology(persist_uid) if persist_uid else None
            except Exception:
                _phys = None
            try:
                _decision = brain_cascade.decide(
                    persist_profile, message=persist_user_msg,
                    conversation=persist_conversation, physiology=_phys, model=model_to_use)
                _directive = brain_enforcement.render(_decision)
                enforce_event = _directive["decision_event"]
                _add = _directive["system_prompt_addendum"]
                if _add:
                    if _directive["should_generate_workout"]:
                        messages[0]["content"] = messages[0]["content"] + "\n\n" + _add   # constraints
                    else:
                        messages[0]["content"] = _add + "\n\n" + messages[0]["content"]   # safety override
                # ── BUILD-003 · ADAPTIVE COACH (HSE_CONSUMER — OFF by default) ──
                # First runtime consumer of Human State. Shapes HOW the response is
                # delivered (tone/volume/intensity/recovery/motivation), APPENDED after
                # the safety directive — never overrides it, never generates a withheld
                # workout, never raises load. Failure-isolated. The Brain never reads state.
                if coaching.enabled():
                    try:
                        _adapt = coaching.adapt(":".join(persist_analytics_subject),
                                                persist_user_msg, _decision, _directive,
                                                profile=persist_profile)
                        if _adapt["applied"]:
                            messages[0]["content"] = messages[0]["content"] + "\n\n" + _adapt["addendum"]
                            enforce_event["adaptation"] = _adapt["adaptations"]   # explainability
                    except Exception as _ce:
                        print(f"[coach] adaptation failed: {_ce}")
            except Exception as _ee:
                print(f"[enforce] safety-front render failed: {_ee}")
                enforce_event = None

        def _persist_reply(reply_text):
            """Store the exchange to the account so the coach remembers it across
            devices; save any nutrition plan to nutrition_history."""
            # A SESSION_START greeting is regenerated fresh each session from live
            # state; it is not a content turn, so it is never written to history.
            if session_start or not persist_uid or not reply_text:
                return
            try:
                store.add_conversation(persist_uid, "user", persist_user_msg, persist_lang)
                store.add_conversation(persist_uid, "assistant", reply_text, persist_lang)
                low = reply_text.lower()
                if "|" in reply_text and any(k in low for k in ("ккал", "kcal", "калории", "protein", "протеин", "въглехидрати", "carb")):
                    store.save_nutrition(persist_uid, reply_text, None)
                    # M0: nutrition-plan evidence (inferred tier; stays low until real intake).
                    athlete_store.observe(persist_uid, "nutrition_plan_issued", {})
            except Exception as _pe:
                print(f"[chat] persist failed: {_pe}")
            # M0: exchange evidence — account-only (persist_uid is non-None past the guard above).
            athlete_store.observe(persist_uid, "exchange", {})

        def _shadow_log():
            """SHADOW (M1/M2): compute the cascade so far (S1 + S2) and write a
            fully-traceable record to the decision ledger. Gated by BRAIN_SHADOW
            (OFF by default) and failure-isolated — zero effect on prompt, generation,
            response, or the user. Reads only; writes only brain_decisions. No
            enforcement, no routing, no refusals."""
            if not brain_config.brain_shadow():
                return
            try:
                phys = None
                if persist_uid:
                    try:
                        phys = athlete_store.physiology(persist_uid)
                    except Exception:
                        phys = None
                did = str(_uuid.uuid4())
                trace = brain_inspector.inspect(persist_profile, message=persist_user_msg,
                                                conversation=persist_conversation, physiology=phys,
                                                model=model_to_use, decision_id=did)
                mh = (hashlib.sha256(persist_user_msg.encode("utf-8")).hexdigest()
                      if persist_user_msg else None)
                brain_ledger.log_decision(persist_uid, verdict=None, intervention=None,
                                          urgency=None, enforced=False, out_of_mandate=False,
                                          trace=trace, message_hash=mh, decision_id=did)
            except Exception as _se:
                print(f"[shadow] cascade log failed: {_se}")

        def _log_analytics(t0):
            # M5 Observatory — record the enforced decision + response latency.
            # Failure-isolated; only when a decision was actually rendered (enforce ON).
            try:
                if enforce_event is not None:
                    brain_analytics.record(persist_analytics_subject, enforce_event,
                                           (time.perf_counter() - t0) * 1000)
            except Exception as _ae:
                print(f"[analytics] chat log failed: {_ae}")

        def _ingest_state():
            # BUILD-001 — turn the user's message into structured Human State.
            # Flag-gated (HSE_INGEST, default OFF) + failure-isolated. Writes only the
            # human_state store; NEVER touches the Brain, the prompt, or the reply.
            try:
                _hs_subj = ":".join(persist_analytics_subject)
                if human_state_observatory.enabled():      # BUILD-002: capture full transition
                    human_state_observatory.capture(_hs_subj, persist_user_msg)
                elif human_state.enabled():
                    human_state.ingest(_hs_subj, persist_user_msg, source="message")
            except Exception as _he:
                print(f"[hse] ingest failed: {_he}")

        def generate():
            full = []
            _t_start = time.perf_counter()
            try:
                if _controlled_reply is not None:
                    full.append(_controlled_reply)
                    yield sse({"t": _controlled_reply})
                    speech_event = _speech_event(
                        _controlled_reply,
                        safety_response=getattr(_shadow_decision, "outcome", None) == "route",
                    )
                    if speech_event:
                        yield sse(speech_event)
                    _persist_reply(_controlled_reply)
                    _update_learning_engine(chat_uid, user_message, _controlled_reply, profile)
                    _shadow_log()
                    _log_analytics(_t_start)
                    _ingest_state()
                    yield sse({"done": True})
                    return
                if _recommendation_blueprint is not None and nutrition_delivery_target is not None:
                    reply_text = decision_engine.controlled_response(
                        decision_engine.DecisionResult("clarify", "nutrition", "nutrition_delivery_contract", (), 1.0), lang)
                    yield sse({"t": reply_text})
                    speech_event = _speech_event(reply_text, preserve_visible=True)
                    if speech_event:
                        yield sse(speech_event)
                    _persist_reply(reply_text)
                    _update_learning_engine(chat_uid, user_message, reply_text, profile)
                    yield sse({"done": True})
                    return
                if enforce_event is not None:
                    # Backward-compatible leading event; unknown events are ignored by
                    # the current frontend. Only emitted when BRAIN_ENFORCE is ON.
                    yield sse({"decision": enforce_event})
                stream = client.chat.completions.create(
                    model=model_to_use,
                    messages=messages,
                    max_tokens=max_tokens,
                    stream=True
                )
                for chunk in stream:
                    delta = None
                    if chunk.choices and chunk.choices[0].delta:
                        delta = chunk.choices[0].delta.content
                    if delta:
                        full.append(delta)
                        if nutrition_delivery_target is None and _recommendation_blueprint is None:
                            yield sse({"t": delta})
                _bump_plans_today()  # honest landing counter: +1 real AI plan
                reply_text = "".join(full)
                if _recommendation_blueprint is not None:
                    try:
                        explanations = recommendation_renderer.verified_explanations(
                            reply_text, _recommendation_blueprint)
                        reply_text = recommendation_renderer.render_delivery(
                            _recommendation_blueprint, explanations, lang)
                    except Exception as recommendation_error:
                        print(f"[recommendation] delivery rejected: {recommendation_error}")
                        reply_text = decision_engine.controlled_response(
                            decision_engine.DecisionResult("clarify", _shadow_decision.intent,
                                                           "recommendation_integrity_contract", (), 1.0), lang)
                    yield sse({"t": reply_text})
                elif nutrition_delivery_target is not None:
                    validation = nutrition_validation.validate_daily_nutrition(reply_text, nutrition_delivery_targets)
                    nutrition_delivery_failed = False
                    if not validation.valid:
                        regenerated = []
                        try:
                            regeneration_messages = messages + [{"role": "user", "content": "\n".join(validation.failures)}]
                            regeneration = client.chat.completions.create(
                                model=model_to_use,
                                messages=regeneration_messages,
                                max_tokens=max_tokens,
                                stream=True,
                            )
                            for chunk in regeneration:
                                delta = chunk.choices[0].delta.content if chunk.choices and chunk.choices[0].delta else None
                                if delta:
                                    regenerated.append(delta)
                            regenerated_reply = "".join(regenerated)
                            if nutrition_validation.validate_daily_nutrition(regenerated_reply, nutrition_delivery_targets).valid:
                                reply_text = regenerated_reply
                            else:
                                reply_text = nutrition_validation.failure_message(lang)
                                nutrition_delivery_failed = True
                        except Exception as regeneration_error:
                            print(f"[chat] nutrition regeneration failed: {regeneration_error}")
                            reply_text = nutrition_validation.failure_message(lang)
                            nutrition_delivery_failed = True
                    yield sse({"t": reply_text})
                speech_event = _speech_event(
                    reply_text,
                    preserve_visible=nutrition_delivery_target is not None and nutrition_delivery_failed,
                )
                if speech_event:
                    yield sse(speech_event)
                _persist_reply(reply_text)
                _update_learning_engine(chat_uid, user_message, reply_text, profile)
                _shadow_log()        # SHADOW (BRAIN_SHADOW off by default; no-op in prod)
                _log_analytics(_t_start)   # M5 Observatory
                _ingest_state()      # BUILD-001 Human State (HSE_INGEST off by default)
                if is_first_contact:
                    brain_state = {
                        "decision": decision_state,
                        "confidence": _decision.envelope.confidence,
                        "sleep": profile.get("sleepQuality", "good"),
                        "stress": profile.get("stressLevel", "low"),
                        "body": "knee" if any(k in str(profile.get("injuries") or "").lower() for k in ("knee", "shoulder", "back", "joint", "elbow", "wrist", "pain", "ache", "коляно", "рамо", "гръб", "болка")) else "ok"
                    }
                    yield sse({"done": True, "profile": profile, "brain_state": brain_state})
                else:
                    yield sse({"done": True})
            except Exception as openai_error:
                print(f"[chat] OpenAI error: {openai_error}")
                if nutrition_delivery_targets is not None:
                    reply_text = nutrition_validation.failure_message(lang)
                    yield sse({"t": reply_text})
                    speech_event = _speech_event(reply_text, preserve_visible=True)
                    if speech_event:
                        yield sse(speech_event)
                    _persist_reply(reply_text)
                    _update_learning_engine(chat_uid, user_message, reply_text, profile)
                    _shadow_log()
                    _log_analytics(_t_start)
                    _ingest_state()
                    yield sse({"done": True})
                    return
                if full:
                    # Потребителят вече получи почти всичко — завършваме чисто
                    _bump_plans_today()
                    reply_text = "".join(full)
                    if _recommendation_blueprint is not None:
                        try:
                            explanations = recommendation_renderer.verified_explanations(
                                reply_text, _recommendation_blueprint)
                            reply_text = recommendation_renderer.render_delivery(
                                _recommendation_blueprint, explanations, lang)
                        except Exception as recommendation_error:
                            print(f"[recommendation] delivery rejected: {recommendation_error}")
                            reply_text = decision_engine.controlled_response(
                                decision_engine.DecisionResult("clarify", _shadow_decision.intent,
                                                               "recommendation_integrity_contract", (), 1.0), lang)
                        yield sse({"t": reply_text})
                    elif nutrition_delivery_target is not None:
                        reply_text = nutrition_validation.failure_message(lang)
                        yield sse({"t": reply_text})
                    speech_event = _speech_event(
                        reply_text,
                        preserve_visible=nutrition_delivery_target is not None,
                    )
                    if speech_event:
                        yield sse(speech_event)
                    _persist_reply(reply_text)
                    _update_learning_engine(chat_uid, user_message, reply_text, profile)
                    _shadow_log()     # SHADOW (BRAIN_SHADOW off by default; no-op in prod)
                    _log_analytics(_t_start)   # M5 Observatory
                    _ingest_state()   # BUILD-001 Human State (HSE_INGEST off by default)
                    if is_first_contact:
                        brain_state = {
                            "decision": decision_state,
                            "confidence": _decision.envelope.confidence,
                            "sleep": profile.get("sleepQuality", "good"),
                            "stress": profile.get("stressLevel", "low"),
                            "body": "knee" if any(k in str(profile.get("injuries") or "").lower() for k in ("knee", "shoulder", "back", "joint", "elbow", "wrist", "pain", "ache", "коляно", "рамо", "гръб", "болка")) else "ok"
                        }
                        yield sse({"done": True, "profile": profile, "brain_state": brain_state})
                    else:
                        yield sse({"done": True})
                else:
                    # Нищо не е стигнало → връщаме съобщението в лимита му (DB refund)
                    if refund_subject:
                        try: store.free_usage_refund(refund_subject[0], refund_subject[1])
                        except Exception: pass
                    yield sse({
                        "error": True,
                        "not_counted": True,
                        "reply": "AI треньорът е претоварен в момента. Моля, опитай отново след 30 секунди."
                    })

        return Response(
            stream_with_context(generate()),
            mimetype="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
        )
    except Exception as e:
        print(f"[chat] Server error: {e}")
        return jsonify({"error": "server_error"}), 500


# ═══════════════════════════════════════════════════════════
# VOICE — /speak : the Brain's TEXT → natural audio (provider-independent).
# This performs NO reasoning. It only speaks text the /chat pipeline already
# produced. The vendor lives entirely behind voice/tts.py, so it can be swapped
# without touching the Brain or the UI.
# ═══════════════════════════════════════════════════════════
_speak_rate = {}  # subject -> [timestamps]  (bounds a billable endpoint)

@app.route("/speak", methods=["POST"])
def speak():
    data = request.get_json(silent=True) or {}
    text = str(data.get("text", "")).strip()[:1600]
    lang = "en" if str(data.get("lang", "bg")).lower() == "en" else "bg"
    if not text:
        return jsonify({"error": "empty"}), 400
    # Cost guard: cap synthesis calls per subject (account or httpOnly device / IP).
    subj = str(g.user["id"]) if g.get("user") else (g.device_id or _client_ip())
    now = time.time()
    stamps = [t for t in _speak_rate.get(subj, []) if now - t < 300]
    if len(stamps) >= 60:
        return jsonify({"error": "rate_limited"}), 429
    stamps.append(now); _speak_rate[subj] = stamps
    try:
        audio, mime = apex_voice.synthesize(text, lang=lang, client=client)
    except Exception as e:
        print(f"[speak] TTS failed: {e}")
        return jsonify({"error": "tts_unavailable"}), 502
    return Response(audio, mimetype=mime, headers={"Cache-Control": "no-store"})


@app.route('/create-checkout-session', methods=['POST'])
def create_checkout_session():
    """
    Creates a Stripe checkout session for the chosen plan.
    Plans: 'founding' (€1.99), 'core' (€9.99), 'pro' (€14.99)
    """
    try:
        data = request.json or {}
        plan_key = data.get('plan', 'core')
        if plan_key not in PLANS:
            plan_key = 'core'
        
        plan = PLANS[plan_key]
        # APP_URL must be set in Railway (e.g. https://apexpulse.pro).
        # Falling back to request.host is a last resort for local dev only.
        host_url = os.getenv('APP_URL', 'https://' + request.host).rstrip('/')
        
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'eur',
                    'product_data': {'name': plan['name']},
                    'unit_amount': plan['amount'],
                },
                'quantity': 1,
            }],
            mode='payment',
            allow_promotion_codes=True,
            metadata={'plan': plan_key},  # plan travels server-side through Stripe
            success_url=host_url + '/app/success?session_id={CHECKOUT_SESSION_ID}',
            cancel_url=host_url + '/app?success=false',
        )
        return jsonify({'url': session.url})
    except Exception as e:
        print(f'[checkout] Stripe error: {e}')
        return jsonify({'error': 'checkout_failed'}), 403


@app.route('/app/success')
def payment_success():
    """After Stripe payment, redirect to /app with pending_session so JS can poll for token.
    Token is issued by the webhook (server-to-server), not here."""
    session_id = request.args.get('session_id')
    if not session_id:
        return redirect('/app?success=false')
    return redirect(f'/app?pending_session={session_id}')


@app.route('/webhook', methods=['POST'])
def stripe_webhook():
    """Stripe sends checkout.session.completed server-to-server with a signed payload.
    This is the authoritative source of truth for payment — cannot be spoofed by clients."""
    payload = request.get_data()
    sig_header = request.headers.get('Stripe-Signature', '')
    webhook_secret = os.getenv('STRIPE_WEBHOOK_SECRET', '')
    if not webhook_secret:
        print('[webhook] WARNING: STRIPE_WEBHOOK_SECRET not set — webhook disabled')
        return jsonify({'error': 'webhook not configured'}), 500
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
    except stripe.error.SignatureVerificationError:
        print('[webhook] Invalid signature — possible forgery attempt')
        return jsonify({'error': 'invalid signature'}), 400
    except Exception as e:
        print(f'[webhook] Bad payload: {e}')
        return jsonify({'error': 'bad payload'}), 400

    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        if session.payment_status == 'paid':
            paid_plan = (session.metadata or {}).get('plan', 'core')
            expiry = int(time.time()) + (30 * 24 * 60 * 60)
            token = make_token(expiry, paid_plan)
            uid = _provision_paid_account(session, paid_plan, expiry)
            _pending_tokens[session.id] = (token, time.time(), uid)
            print(f'[webhook] Paid session {session.id[:20]}... plan={paid_plan} user={uid}')
    return jsonify({'ok': True})


def _provision_paid_account(session, paid_plan, expiry_ts):
    """DB is the source of truth: bind the payment to an account keyed by the
    Stripe customer email, create/refresh the subscription, and record the payment.
    Returns user_id (or None if no email available)."""
    try:
        details = getattr(session, 'customer_details', None)
        email = (getattr(details, 'email', None) if details else None) or getattr(session, 'customer_email', None)
        if not email:
            return None
        cust = getattr(session, 'customer', None)
        uid = store.get_or_create_user(email, stripe_customer_id=cust)
        if not uid:
            return None
        import datetime as _d
        period_end = _d.datetime.fromtimestamp(expiry_ts, _d.timezone.utc)
        store.upsert_subscription(uid, paid_plan, period_end, stripe_customer_id=cust,
                                  stripe_session_id=session.id, status='active')
        amount = getattr(session, 'amount_total', None) or PLANS.get(paid_plan, {}).get('amount')
        store.record_payment(uid, session.id, amount, getattr(session, 'currency', 'eur') or 'eur', paid_plan)
        return uid
    except Exception as e:
        print(f'[webhook] account provisioning failed: {e}')
        return None


_poll_rate = {}  # session_id -> [timestamps] — limit Stripe API calls per session

@app.route('/poll-token')
def poll_token():
    """Browser polls this after returning from Stripe until the webhook delivers the token.
    Falls back to direct Stripe API check if webhook hasn't arrived yet (network delays)."""
    session_id = request.args.get('session_id', '')
    # Only accept Stripe checkout session IDs (cs_live_... or cs_test_...)
    if not session_id or not session_id.startswith('cs_'):
        return jsonify({'ready': False})

    # Evict stale pending tokens to keep memory bounded
    now = time.time()
    stale = [k for k, v in _pending_tokens.items() if now - v[1] > _PENDING_TOKEN_TTL]
    for k in stale:
        del _pending_tokens[k]

    # Primary path: webhook already stored the token + provisioned the account.
    entry = _pending_tokens.pop(session_id, None)
    if entry:
        token, _, uid = (entry + (None,))[:3]
        return _poll_success(token, uid)

    # A completed Checkout session may be replayed after its one-time pending token
    # has been consumed or evicted. Never create a new 30-day period for it: only
    # restore the entitlement already recorded for its account, if it is still live.
    redeemed_uid = store.get_checkout_session_user(session_id)
    if redeemed_uid:
        sub = store.get_subscription(redeemed_uid)
        period_end = sub.get("current_period_end")
        if sub.get("plan") in PLANS and sub.get("status") in ("active", "grace") and period_end:
            try:
                recorded_end = _dt.datetime.fromisoformat(period_end)
                if recorded_end.tzinfo is None:
                    recorded_end = recorded_end.replace(tzinfo=_dt.timezone.utc)
                expiry = int(recorded_end.timestamp())
            except (TypeError, ValueError):
                expiry = 0
            if expiry > now:
                return _poll_success(make_token(expiry, sub["plan"]), redeemed_uid)
        return jsonify({'ready': False})

    # Fallback: webhook may be slightly delayed — verify directly with Stripe.
    # Rate-limit to 5 Stripe API calls per session_id to avoid hammering Stripe.
    timestamps = _poll_rate.get(session_id, [])
    timestamps = [t for t in timestamps if now - t < 60]
    if len(timestamps) >= 5:
        return jsonify({'ready': False})
    timestamps.append(now)
    _poll_rate[session_id] = timestamps
    # Evict old entries from rate-limit tracker
    if len(_poll_rate) > 2000:
        cutoff = now - 120
        for k in list(_poll_rate.keys()):
            if not _poll_rate[k] or _poll_rate[k][-1] < cutoff:
                del _poll_rate[k]

    try:
        session = stripe.checkout.Session.retrieve(session_id)
        if session.payment_status == 'paid':
            paid_plan = (session.metadata or {}).get('plan', 'core')
            expiry = int(time.time()) + (30 * 24 * 60 * 60)
            token = make_token(expiry, paid_plan)
            uid = _provision_paid_account(session, paid_plan, expiry)
            print(f'[poll-token] Fallback: paid session {session_id[:20]}... user={uid}')
            return _poll_success(token, uid)
    except Exception as e:
        print(f'[poll-token] Stripe error: {e}')
    return jsonify({'ready': False})


def _poll_success(token, uid):
    """Return the legacy token AND — if we resolved an account — log the browser in
    by minting a real session cookie, so the purchase flow is one continuous path."""
    body = {'ready': True, 'token': token, 'authenticated': bool(uid)}
    resp = make_response(jsonify(body))
    if uid:
        try:
            sid = store.create_session(uid)
            _set_session_cookie(resp, sid)
        except Exception as e:
            print(f'[poll-token] session mint failed: {e}')
    return resp


@app.route('/success')
def legacy_success_redirect():
    """Backwards compatibility: old Stripe success URLs redirect to /app/success."""
    session_id = request.args.get('session_id', '')
    if session_id:
        return redirect(f'/app/success?session_id={session_id}')
    return redirect('/app')


@app.route('/stats')
def stats_endpoint():
    """Honest live counter for the landing page (real AI responses today)."""
    return jsonify({'plans_today': _get_plans_today()})


def _safe_next(url, fallback='/'):
    """L-1: only allow internal application routes as redirect targets.
    Rejects absolute URLs, scheme-relative (//host), backslashes and any scheme —
    never redirect off-site."""
    if not url or not url.startswith('/') or url.startswith('//') or '://' in url or '\\' in url:
        return fallback
    return url


@app.route('/owner-mode')
def owner_mode():
    """Sets a long-lived cookie that suppresses GA4 tracking on this device.
    Visit /owner-mode to activate, /owner-mode?off=1 to deactivate."""
    turning_off = request.args.get('off') == '1'
    next_url = _safe_next(request.args.get('next', '/'))
    resp = make_response(redirect(next_url))
    if turning_off:
        resp.delete_cookie('apexOwner')
    else:
        resp.set_cookie('apexOwner', 'true', max_age=365 * 24 * 3600, samesite='Lax')
    return resp


@app.route('/verify-token', methods=['POST'])
def verify_token_endpoint():
    """Frontend asks: is this stored token still valid, and which plan does it carry?"""
    data = request.get_json(silent=True) or {}
    token = str(data.get('token', ''))
    is_valid, plan = verify_token(token)
    is_dev = bool(DEV_TOKEN) and token == DEV_TOKEN
    # Decode expiry so the Subscription page can show the access-until date.
    expiry = 0
    if is_valid and not is_dev:
        try:
            padded = token + "=" * (-len(token) % 4)
            expiry = int(base64.urlsafe_b64decode(padded).decode().split(".")[0])
        except Exception:
            expiry = 0
    return jsonify({'valid': is_valid, 'isDev': is_dev, 'plan': plan or 'free', 'expiry': expiry})


# ═══════════════════════════════════════════════════════════
# EU Directive 2023/2673 — RIGHT OF WITHDRAWAL (waiver flow)
# Apex sells one-time 30-day digital passes. Our Terms invoke the
# directive's waiver: the right of withdrawal is lost once the digital
# content is delivered. We offer a 7-day money-back guarantee — full
# refund, no questions asked, if invoked within 7 days of payment;
# after that, the waiver kicks in.
#
# Within 7 days: revoke token, refund the original Stripe charge, email
#                both the user (Resend) and admin.
# After 7 days:  keep token active until expiry, email the user
#             acknowledging the request and explaining the waiver,
#             notify admin for audit.
# ═══════════════════════════════════════════════════════════
COACH_INBOX = 'coach@apexpulse.pro'
PLAN_AMOUNTS_EUR = {'core': '9.99', 'pro': '14.99'}
WITHDRAW_WINDOW_HOURS = 168  # 7 days


@app.route('/withdraw', methods=['POST'])
def withdraw_endpoint():
    data = request.get_json(silent=True) or {}
    token = str(data.get('token', ''))[:512]
    session_id = str(data.get('session_id', ''))[:200]
    user_lang = str(data.get('lang', 'bg'))[:5]

    is_valid, plan = verify_token(token)
    if not is_valid:
        return jsonify({'ok': False, 'error': 'invalid_token'}), 401
    if DEV_TOKEN and token == DEV_TOKEN:
        return jsonify({'ok': False, 'error': 'dev_token_not_refundable'}), 400

    # Decode expiry from the token to compute hours_since_payment server-side.
    try:
        padded = token + '=' * (-len(token) % 4)
        decoded = base64.urlsafe_b64decode(padded).decode()
        expiry_ts = int(decoded.split('.')[0])
    except Exception:
        return jsonify({'ok': False, 'error': 'invalid_token'}), 401

    now_ts = int(time.time())
    payment_ts = expiry_ts - (30 * 24 * 60 * 60)
    hours_since = (now_ts - payment_ts) / 3600.0
    if hours_since < 0:
        return jsonify({'ok': False, 'error': 'invalid_token'}), 401

    # Try to recover the customer's email from the Stripe session (best-effort,
    # used for both the within-window refund flow and the waiver acknowledgment).
    customer_email = ''
    if session_id and session_id.startswith('cs_'):
        try:
            session = stripe.checkout.Session.retrieve(session_id)
            cd = getattr(session, 'customer_details', None)
            if cd:
                customer_email = (cd.email if hasattr(cd, 'email') else cd.get('email', '')) or ''
        except Exception as e:
            print(f'[withdraw] Stripe session retrieve failed for {session_id[:24]}...: {e}')

    ip = request.headers.get('X-Forwarded-For', request.remote_addr or '?').split(',')[0].strip()
    payment_date_str = time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime(payment_ts))
    amount = PLAN_AMOUNTS_EUR.get(plan, '?')
    admin_addr = os.getenv('LEAD_NOTIFY_EMAIL', os.getenv('GMAIL_USER', COACH_INBOX))

    # Mark the account subscription cancelled in the DB (server truth), regardless
    # of window — grace period keeps access until period end where applicable.
    if g.get("user"):
        try: store.cancel_subscription(g.user["id"])
        except Exception as e: print(f"[withdraw] db cancel failed: {e}")

    # ─────────── WITHIN 7-DAY WINDOW → revoke + refund ───────────
    if hours_since <= WITHDRAW_WINDOW_HOURS:
        # Revoke immediately so the token stops working even if cached client-side.
        _revoked_tokens.add(token)
        _save_revoked(_revoked_tokens)

        refund_id = None
        refund_error = None
        if session_id and session_id.startswith('cs_'):
            try:
                session = stripe.checkout.Session.retrieve(session_id)
                pi = getattr(session, 'payment_intent', None)
                if not pi:
                    raise RuntimeError('session has no payment_intent')
                refund = stripe.Refund.create(payment_intent=pi)
                refund_id = refund.id
                print(f'[withdraw] Refund {refund_id} for session {session_id[:24]}... ({hours_since:.1f}h)')
            except Exception as e:
                refund_error = str(e)
                print(f'[withdraw] Stripe refund failed: {e}')
        else:
            refund_error = 'no session_id stored'

        # Confirmation to the user (best-effort if we have an email)
        if customer_email and '@' in customer_email:
            if user_lang == 'en':
                subject = 'Subscription cancelled — refund on the way'
                user_body = (
                    "Hi,\n\n"
                    "We have received your cancellation request and processed your refund.\n\n"
                    f"Plan: APEX PULSE {plan.upper()}\n"
                    f"Amount: EUR {amount}\n"
                    f"Payment date: {payment_date_str}\n"
                    f"Hours since payment: {hours_since:.1f}\n\n"
                    "Your access has been revoked.\n"
                    "Your refund has been issued and will appear on your original payment\n"
                    "method within 5-10 business days (Stripe typical timing).\n\n"
                    "If you have questions, reply to this email.\n\n"
                    "APEX PULSE PRO\n"
                )
            else:
                subject = 'Абонаментът е отказан — възстановяване на сумата'
                user_body = (
                    "Здравей,\n\n"
                    "Получихме твоето искане за отказ и обработихме възстановяването.\n\n"
                    f"План: APEX PULSE {plan.upper()}\n"
                    f"Сума: EUR {amount}\n"
                    f"Дата на плащане: {payment_date_str}\n"
                    f"Часове от плащането: {hours_since:.1f}\n\n"
                    "Достъпът ти е прекратен.\n"
                    "Сумата е възстановена и ще се появи на оригиналния начин на плащане\n"
                    "в рамките на 5-10 работни дни (обичайни срокове на Stripe).\n\n"
                    "Ако имаш въпроси, отговори на този имейл.\n\n"
                    "APEX PULSE PRO\n"
                )
            send_email(customer_email, subject, user_body)

        # Admin audit + manual-handle fallback if Stripe failed
        admin_subject = (
            f'[Apex CANCEL] refund {refund_id} — within 7-day window'
            if refund_id else
            f'[Apex CANCEL] manual refund required — Stripe failed'
        )
        admin_body = (
            "Cancellation within 7-day money-back guarantee window.\n\n"
            f"Plan:              APEX PULSE {plan.upper()}\n"
            f"Amount:            EUR {amount}\n"
            f"Payment date:      {payment_date_str}\n"
            f"Hours since payment: {hours_since:.1f}\n"
            f"Stripe session_id: {session_id or '(not stored)'}\n"
            f"Refund ID:         {refund_id or '(FAILED — process manually)'}\n"
            f"Refund error:      {refund_error or '(none)'}\n"
            f"Customer email:    {customer_email or '(unknown)'}\n"
            f"User IP:           {ip}\n"
            f"Token (revoked):   {token[:24]}...\n"
            f"User language:     {user_lang}\n"
        )
        send_email(admin_addr, admin_subject, admin_body,
                   reply_to=customer_email if customer_email else '')

        return jsonify({'ok': True, 'refunded': bool(refund_id), 'access_revoked': True,
                        'hours_since_payment': round(hours_since, 1)})

    # ─────────── AFTER 7-DAY WINDOW → waiver, no refund ───────────
    # Token stays active until natural expiry. We honor the user's notice
    # by recording it and emailing both parties, but do not refund (per
    # Terms §4 — right of withdrawal waived for delivered digital content).
    if customer_email and '@' in customer_email:
        if user_lang == 'en':
            subject = 'Cancellation request received — APEX PULSE PRO'
            user_body = (
                "Hi,\n\n"
                "We have received your cancellation request. Thank you for letting us know.\n\n"
                f"Plan: APEX PULSE {plan.upper()}\n"
                f"Payment date: {payment_date_str}\n"
                f"Hours since payment: {hours_since:.1f}\n\n"
                "About your refund:\n"
                "Apex Pulse Pro is digital content delivered immediately on payment.\n"
                "Our 7-day money-back guarantee covers the first 7 days from payment.\n"
                "Your request is outside that window, so we are unable to issue a refund.\n\n"
                "Your access will continue until the natural end of your 30-day pass — you\n"
                "do not need to do anything else. We will not auto-renew (Apex is a one-time\n"
                "purchase, never a recurring subscription).\n\n"
                "If you believe this was processed in error, reply to this email and we\n"
                "will review it.\n\n"
                "APEX PULSE PRO\n"
            )
        else:
            subject = 'Заявката за отказ е получена — APEX PULSE PRO'
            user_body = (
                "Здравей,\n\n"
                "Получихме твоето искане за отказ. Благодарим, че ни уведоми.\n\n"
                f"План: APEX PULSE {plan.upper()}\n"
                f"Дата на плащане: {payment_date_str}\n"
                f"Часове от плащането: {hours_since:.1f}\n\n"
                "Относно възстановяването:\n"
                "Apex Pulse Pro е цифрово съдържание, доставено веднага при плащане.\n"
                "Нашата гаранция за връщане на парите покрива първите 7 дни от плащането.\n"
                "Заявката ти е извън този прозорец, така че не можем да възстановим сумата.\n\n"
                "Достъпът ти продължава до естествения край на 30-дневния период —\n"
                "няма нужда да правиш нищо повече. Няма автоматично подновяване\n"
                "(Apex е еднократна покупка, не повтарящ се абонамент).\n\n"
                "Ако смяташ, че това е грешка, отговори на този имейл и ще проверим.\n\n"
                "APEX PULSE PRO\n"
            )
        send_email(customer_email, subject, user_body)

    admin_body = (
        "Cancellation request OUTSIDE 7-day window — waiver applies, no refund.\n\n"
        f"Plan:              APEX PULSE {plan.upper()}\n"
        f"Amount NOT refunded: EUR {amount}\n"
        f"Payment date:      {payment_date_str}\n"
        f"Hours since payment: {hours_since:.1f}\n"
        f"Stripe session_id: {session_id or '(not stored)'}\n"
        f"Customer email:    {customer_email or '(unknown)'}\n"
        f"User IP:           {ip}\n"
        f"Token (KEPT ACTIVE until natural expiry): {token[:24]}...\n"
        f"User language:     {user_lang}\n\n"
        "Per Terms §4 + EU 2023/2673 waiver. No action required unless user disputes.\n"
    )
    send_email(admin_addr, '[Apex CANCEL] waiver applied — no refund',
               admin_body, reply_to=customer_email if customer_email else '')

    return jsonify({'ok': True, 'refunded': False, 'access_revoked': False,
                    'waiver_applied': True, 'hours_since_payment': round(hours_since, 1)})


# ═══════════════════════════════════════════════════════════
# LEAD CAPTURE — the single biggest funnel leak fix.
# Free user leaves email near the limit → gets +5 bonus messages
# AND we get a contactable lead for follow-up offers.
# Email is sent to GMAIL_USER (same SMTP as feedback) + logged.
# ═══════════════════════════════════════════════════════════
_lead_recent = {}

@app.route('/save-lead', methods=['POST'])
def save_lead():
    try:
        ip = _client_ip()
        now = time.time()
        if now - _lead_recent.get(ip, 0) < 60:
            return jsonify({'ok': False, 'error': 'rate_limit'}), 429

        data = request.json or {}
        email = str(data.get('email', '')).strip().replace('\r', '').replace('\n', '')[:120]
        lang = str(data.get('lang', 'bg'))[:5]
        plan_text = str(data.get('plan_text', ''))[:6000]
        if '@' not in email or '.' not in email.split('@')[-1] or len(email) < 6:
            return jsonify({'ok': False, 'error': 'invalid_email'}), 400

        _lead_recent[ip] = now
        if len(_lead_recent) > 2000:
            cutoff = now - 120
            for k in list(_lead_recent.keys()):
                if _lead_recent[k] < cutoff:
                    del _lead_recent[k]
        # Grant the bonus messages to this caller's DB free-usage window
        # (account when logged in, else the httpOnly device id) — server truth.
        try:
            subj = ("user", str(g.user["id"])) if g.get("user") else ("device", g.device_id or ip)
            store.free_usage_grant_bonus(subj[0], subj[1])
        except Exception as _be:
            print(f"[lead] bonus grant failed: {_be}")

        body = f"""APEX PULSE PRO — New Lead

Email: {email}
Language: {lang}
IP: {ip}
Time: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}

Source: free-limit email capture (granted +{LEAD_BONUS} bonus messages)
"""
        admin_addr = os.getenv('LEAD_NOTIFY_EMAIL', os.getenv('GMAIL_USER', 'apexpulsepro@gmail.com'))

        # 1) Notification to us (the lead)
        notify_sent = send_email(admin_addr, f'[Apex LEAD] {email}', body, reply_to=email)

        # 2) Welcome email TO THE USER — we promised them their plan
        if lang == 'bg':
            subject = 'Твоят план от APEX PULSE PRO 💪'
            user_body = (
                "Здравей!\n\n"
                "Благодарим, че пробва APEX PULSE PRO — твоят личен AI фитнес треньор.\n\n"
                + (f"Ето последния план, който AI треньорът създаде за теб:\n\n{'─'*40}\n{plan_text}\n{'─'*40}\n\n" if plan_text else "")
                + "Имаш +5 бонус съобщения днес — продължи разговора тук:\n"
                "https://apexpulse.pro/app\n\n"
                "А ако искаш AI треньор без никакви лимити, който помни целите ти\n"
                "и ти прави персонални програми всеки ден:\n"
                "→ APEX CORE — само €9.99 за 30 дни (€0.33/ден)\n"
                "https://apexpulse.pro/app?plan=core\n\n"
                "До скоро в залата (или вкъщи)! 🔥\n"
                "APEX PULSE PRO\n"
            )
        else:
            subject = 'Your plan from APEX PULSE PRO 💪'
            user_body = (
                "Hi!\n\n"
                "Thanks for trying APEX PULSE PRO — your personal AI fitness coach.\n\n"
                + (f"Here is the latest plan your AI coach created for you:\n\n{'─'*40}\n{plan_text}\n{'─'*40}\n\n" if plan_text else "")
                + "You have +5 bonus messages today — continue the conversation here:\n"
                "https://apexpulse.pro/app\n\n"
                "Want an AI coach with no limits that remembers your goals?\n"
                "→ APEX CORE — just €9.99 for 30 days (€0.33/day)\n"
                "https://apexpulse.pro/app?plan=core\n\n"
                "See you at the gym (or at home)! 🔥\n"
                "APEX PULSE PRO\n"
            )
        mail_sent = send_email(email, subject, user_body)

        if not (notify_sent or mail_sent):
            print(f'[lead] No email provider worked. LOG:\n{body}')

        _schedule_email_sequence(email, lang)

        return jsonify({'ok': True, 'bonus': LEAD_BONUS, 'mail_sent': mail_sent})
    except Exception as e:
        print(f'[lead] error: {e}')
        return jsonify({'ok': False, 'error': 'server_error'}), 500


# ═══════════════════════════════════════════════════════════
# FEEDBACK ENDPOINT
# Receives feedback from users via "Feedback" button in chat
# Sends email to apexpulsepro@gmail.com via Gmail SMTP
# Falls back to logging if Gmail credentials not configured
# 
# Required Railway env vars (optional - works without):
#   GMAIL_USER=apexpulsepro@gmail.com
#   GMAIL_APP_PASSWORD=xxxxxxxxxxxxxxxx  (16-char app password)
# ═══════════════════════════════════════════════════════════

# Simple in-memory rate limit: 1 feedback per IP per 5 minutes
_feedback_recent = {}

@app.route('/feedback', methods=['POST'])
def feedback_endpoint():
    try:
        # Basic rate limiting by IP — use request.remote_addr (already set by ProxyFix)
        ip = _client_ip()
        now = time.time()
        last = _feedback_recent.get(ip, 0)
        if now - last < 300:  # 5 minutes
            return jsonify({'ok': False, 'error': 'rate_limit'}), 429
        
        data = request.get_json(silent=True) or {}
        fb_type = str(data.get('type', 'unknown'))[:30]
        message = str(data.get('message', ''))[:1000]
        email = str(data.get('email', ''))[:100]
        lang = str(data.get('lang', 'bg'))[:5]
        plan = str(data.get('plan', 'free'))[:20]
        
        # Validate type
        allowed_types = {'positive', 'improvement', 'bug', 'idea'}
        if fb_type not in allowed_types:
            return jsonify({'ok': False, 'error': 'invalid_type'}), 400
        
        # Mark this IP as having sent recent feedback
        _feedback_recent[ip] = now
        # Clean old entries to prevent memory bloat
        if len(_feedback_recent) > 1000:
            cutoff = now - 600
            for k in list(_feedback_recent.keys()):
                if _feedback_recent[k] < cutoff:
                    del _feedback_recent[k]
        
        # Compose email body
        type_labels = {
            'positive': '😊 Positive feedback',
            'improvement': '🤔 Improvement suggestion',
            'bug': '😞 Bug / issue report',
            'idea': '💡 New idea',
        }
        type_label = type_labels.get(fb_type, fb_type)
        
        email_body = f"""APEX PULSE PRO — User Feedback

Type: {type_label}
User plan: {plan}
Language: {lang}
IP: {ip}

User email (optional reply-to): {email or '(not provided)'}

Message:
{message or '(empty)'}

---
Sent automatically from apexpulse.pro feedback widget
"""
        
        # Send via Resend HTTPS API (Railway blocks SMTP) with Gmail fallback
        admin_addr = os.getenv('LEAD_NOTIFY_EMAIL', os.getenv('GMAIL_USER', 'apexpulsepro@gmail.com'))
        sent = send_email(admin_addr, f'[Apex Feedback] {type_label}', email_body, reply_to=email)
        if sent:
            print(f'[feedback] Email sent for type={fb_type}')
        else:
            print(f'[feedback] No email provider worked. FALLBACK LOG:\n{email_body}')
        
        return jsonify({'ok': True})
    except Exception as e:
        print(f'[feedback] error: {e}')
        return jsonify({'ok': False, 'error': 'server_error'}), 500


# ═══════════════════════════════════════════════════════════
# SEO ROUTES — must be at root level, not in /static/
# Search engines look for these at exact paths
# ═══════════════════════════════════════════════════════════


@app.route('/robots.txt')
def robots_txt():
    """Tell search engines what to crawl."""
    from flask import send_from_directory
    return send_from_directory('static', 'robots.txt', mimetype='text/plain')


@app.route('/sitemap.xml')
def sitemap_xml():
    """List all pages on the site for search engines."""
    from flask import send_from_directory
    return send_from_directory('static', 'sitemap.xml', mimetype='application/xml')


# REFACTOR-001 — internal admin & Brain-debug routes live in admin_routes.py
# (a Flask Blueprint). Same URL paths, same token/flag gating; app.py stays the
# entry point. Registered here so all app-level state is already defined.
from admin_routes import bp as admin_bp  # noqa: E402
app.register_blueprint(admin_bp)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
