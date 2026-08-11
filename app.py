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
import nutrition_conversation
import nutrition_plan
import nutrition_validation
from knowledge import KnowledgeResolver, load_default_registry
from recommend import architect as recommendation_architect, engine as recommendation_planning, renderer as recommendation_renderer
from training_engine import (
    MovementPattern,
    TrainingRuntimeError,
    apply_followup,
    advance_training_lifecycle,
    build_training_plan,
    followup_message,
    load_exercise_library,
    parse_workout_followup,
    recovery_from_payload,
    state_for,
    validate_workout_completion_payload,
    workout_result_from_payload,
)
from training_engine import renderer as training_renderer
from training_engine.advisory import persona_expert_training_signals
from training_engine.health_restrictions import (
    FitnessLimitationState,
    UnsupportedHealthRestrictionError,
    clinician_clearance_patterns,
    explicit_restrictions_from_message,
    fitness_limitation_from_history,
    fitness_limitation_from_profile,
    is_recovering_light_session_request,
    limitation_excluded_patterns,
    migrate_temporary_fitness_restrictions,
    project_explicit_health_restrictions,
    remove_cleared_clinician_restrictions,
    transition_fitness_limitation,
)
from brain.runtime_assets import expert_consensus, persona_matcher
from brain.runtime_assets.expert_rules import load_expert_rule_packs
from brain.runtime_assets.personas import load_runtime_personas
import brain.runtime_assets.shadow_trace as shadow_trace
import brain.runtime_assets.shadow_observability as shadow_observability
import brain.runtime_assets.persona_expert_projection as persona_expert_projection
import athlete_store  # M0: Athlete Model substrate (failure-isolated observe wiring)
import brain.config as brain_config             # M1: Brain shadow flags (default OFF)
import brain.inspector as brain_inspector       # M1/Commit3: Brain Inspector (observability)
import brain.cascade as brain_cascade           # M3: the one orchestrator (Decision)
import brain.enforcement as brain_enforcement   # M4: Safety-Front renderer
from brain.health_scope import (HealthSafetyScope, assess_health_scope,
                                declared_context_prompt, medical_boundary_message)
import brain.shoulder_validator as shoulder_validator
from brain.shoulder_exercise_index import EXERCISE_SHOULDER_LOAD
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
_WORKOUT_CONVERSATION_ID = re.compile(r"^[A-Za-z0-9_-]{16,128}$")
_workout_conversation_lock = threading.Lock()
_workout_conversation_state = {}
_workout_conversation_health_restrictions = {}
_workout_conversation_fitness_limitations = {}
_workout_conversation_medical_holds = {}
_workout_conversation_stale = set()


def _workout_conversation_scope(payload, user_id, device_id):
    """Return a tab-scoped, subject-bound key for an immutable last workout."""
    conversation_id = str((payload or {}).get("conversation_id") or "")
    if not _WORKOUT_CONVERSATION_ID.fullmatch(conversation_id):
        return None
    subject = f"account:{user_id}" if user_id else f"device:{device_id or ''}"
    return subject, conversation_id


def _last_workout_for(scope):
    if scope is None:
        return None
    with _workout_conversation_lock:
        return _workout_conversation_state.get(scope)


def _remember_workout(scope, plan):
    if scope is None or plan is None:
        return
    with _workout_conversation_lock:
        _workout_conversation_state[scope] = state_for(plan)
        _workout_conversation_stale.discard(scope)


def _conversation_health_restrictions(scope):
    if scope is None:
        return ()
    with _workout_conversation_lock:
        return _workout_conversation_health_restrictions.get(scope, ())


def _record_conversation_health_restrictions(scope, restrictions):
    """Keep explicit restrictions tab-scoped for anonymous follow-up safety."""
    if scope is None:
        return
    normalized = tuple(str(item).strip() for item in restrictions if str(item).strip())
    if not normalized:
        return
    with _workout_conversation_lock:
        previous = _workout_conversation_health_restrictions.get(scope, ())
        _workout_conversation_health_restrictions[scope] = tuple(dict.fromkeys((*previous, *normalized)))
        _workout_conversation_stale.add(scope)


def _replace_conversation_health_restrictions(scope, restrictions):
    if scope is None:
        return
    normalized = tuple(str(item).strip() for item in restrictions if str(item).strip())
    with _workout_conversation_lock:
        if normalized:
            _workout_conversation_health_restrictions[scope] = normalized
        else:
            _workout_conversation_health_restrictions.pop(scope, None)
        _workout_conversation_stale.add(scope)


def _conversation_fitness_limitation(scope):
    if scope is None:
        return None
    with _workout_conversation_lock:
        return _workout_conversation_fitness_limitations.get(scope)


def _record_conversation_fitness_limitation(scope, limitation):
    if scope is None or limitation is None:
        return
    with _workout_conversation_lock:
        _workout_conversation_fitness_limitations[scope] = limitation
        _workout_conversation_stale.add(scope)


def _apply_clinician_clearance(profile, cleared_patterns):
    """Remove only clinician-origin restrictions covered by explicit clearance."""
    updated = dict(profile or {})
    changed = False
    for field in ("clinicianRestrictions", "medicalRestrictions",
                  "healthRestrictions", "trainingRestrictions"):
        if field not in updated:
            continue
        remaining = remove_cleared_clinician_restrictions(
            updated.get(field), cleared_patterns,
            clinician_field=field in ("clinicianRestrictions", "medicalRestrictions"),
        )
        current = updated.get(field)
        current_values = ((current,) if isinstance(current, str) else
                          tuple(current) if isinstance(current, (list, tuple, set, frozenset)) else ())
        if remaining != current_values:
            changed = True
            if remaining:
                updated[field] = list(remaining)
            else:
                updated.pop(field, None)
    return updated, changed


def _conversation_medical_hold(scope):
    """Return the generic medical boundary retained for this conversation."""
    if scope is None:
        return None
    with _workout_conversation_lock:
        return _workout_conversation_medical_holds.get(scope)


def _record_conversation_medical_hold(scope, hold):
    """Retain an anonymous medical hold independently of workout state."""
    if scope is None or not isinstance(hold, dict):
        return
    with _workout_conversation_lock:
        _workout_conversation_medical_holds[scope] = dict(hold)
        _workout_conversation_stale.add(scope)


def _workout_is_stale(scope):
    if scope is None:
        return False
    with _workout_conversation_lock:
        return scope in _workout_conversation_stale


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


def _paid_access_enabled():
    """Keep Stripe checkout explicitly opt-in while paid sales are paused."""
    return os.getenv("PAID_ACCESS_ENABLED", "false").strip().lower() == "true"

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
    workout_completion = data.get("workout_completion")
    if workout_completion is not None:
        try:
            validate_workout_completion_payload(workout_completion)
        except ValueError:
            return jsonify({"error": "invalid_workout_completion"}), 400
        session = dict(session)
        session["workout_completion"] = workout_completion
    wid = store.log_workout(u["id"], session)
    # M0: workout evidence for the Athlete Model (failure-isolated).
    athlete_store.observe(u["id"], "workout_completed", session)
    return jsonify({"ok": True, "id": wid})


@app.route("/api/history", methods=["GET", "POST"])
def api_history():
    u = _require_user()
    if not u:
        return jsonify({"error": "unauthenticated"}), 401
    if request.method == "POST":
        return api_workout()
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


def _nutrition_restrictions(profile):
    """Project explicit profile constraints into a generated plan record."""
    if not isinstance(profile, dict):
        return ()
    values = []
    for key in ("allergies", "foodPreferences", "diet", "dietaryRestrictions"):
        value = profile.get(key)
        if isinstance(value, (list, tuple)):
            values.extend(str(item).strip() for item in value)
        elif value:
            values.extend(part.strip() for part in str(value).split(","))
    return tuple(value for value in values if value)


def _requests_workout_and_nutrition(message):
    """Identify a two-deliverable request before the single-turn renderer runs."""
    normalized = str(message or "").casefold()
    workout = any(token in normalized for token in ("workout", "training", "\u0442\u0440\u0435\u043d\u0438\u0440"))
    nutrition = any(token in normalized for token in (
        "nutrition", "meal", "diet", "food", "\u0445\u0440\u0430\u043d", "\u0440\u0435\u0436\u0438\u043c", "\u043c\u0435\u043d\u044e",
    ))
    return workout and nutrition


def _combined_request_follow_up(lang):
    if str(lang).lower() == "en":
        return ("\n\nYour workout is ready. A daily nutrition plan is delivered as a separate "
                "validated request; send: Give me a nutrition plan.")
    return ("\n\nТренировката е готова. Дневният хранителен режим се доставя като отделна "
            "валидирана заявка; изпрати: Направи ми хранителен режим.")


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


def _training_engine_active():
    # The deterministic training path is the production workout path. A
    # deployment without an explicit variable must not silently fall back to
    # the legacy prompt-generated workout flow.
    return os.getenv("TRAINING_ENGINE_ACTIVE", "true").strip().lower() == "true"


_RECOMMENDATION_PLANNER = recommendation_planning.RecommendationEngine(
    KnowledgeResolver(load_default_registry()))


_WORKOUT_REQUEST_TERMS = (
    "workout", "exercise routine", "training plan", "warm-up", "warmup",
    "тренировка", "тренировъчен план", "загрявка", "раздвижване",
)
_WORKOUT_REQUEST_PREFIXES = (
    "give me", "build", "make me", "create", "i want", "i need", "plan ",
    "дай ми", "направи ми", "създай", "искам", "нуждая се", "планирай",
)


def _explicit_workout_request(message):
    """Return true only for an actual workout prescription request, not coaching chat."""
    text = re.sub(r"\s+", " ", str(message or "").casefold()).strip()
    return (any(term in text for term in _WORKOUT_REQUEST_TERMS)
            and (any(text.startswith(prefix) for prefix in _WORKOUT_REQUEST_PREFIXES)
                 or any(f" {prefix}" in text for prefix in _WORKOUT_REQUEST_PREFIXES)))


def _planning_intent(message, history, classified_intent, *, require_explicit_workout=False):
    """Keep nutrition parsing BG-safe and make enforce-mode workout routing explicit."""
    if classified_intent == "medical":
        return None
    if nutrition_conversation.is_plan_request(message, history):
        return "nutrition"
    if classified_intent == "workout":
        return "workout" if not require_explicit_workout or _explicit_workout_request(message) else None
    return None


def _plan_coaching_request(snapshot, intent, history, lang):
    """Resolve a coaching turn before any communication prompt is assembled."""
    if intent not in ("workout", "nutrition"):
        return None, None
    profile = recommendation_planning.ImmutableUserProfile.from_verified_facts(
        snapshot.profile,
        locked_preferences=snapshot.locked_preferences.as_dict(),
        clarification_history=recommendation_planning.clarification_history(history, lang),
    )
    blueprint = _RECOMMENDATION_PLANNER.plan(intent, profile)
    if blueprint.outcome is recommendation_planning.RecommendationOutcome.CLARIFY:
        return blueprint, recommendation_planning.clarification_message(blueprint.clarification_field, lang)
    if blueprint.outcome is recommendation_planning.RecommendationOutcome.AWAITING_PROFILE:
        return blueprint, recommendation_planning.awaiting_profile_message(lang)
    return blueprint, None


def _active_training_plan(snapshot, planning_blueprint, *, followup=None, previous_workout=None,
                          advisory_signals=None, brain_excluded_movement_patterns=frozenset(),
                          fitness_excluded_movement_patterns=frozenset(), recovering=False):
    """Build the deterministic workout artifact from verified request facts only."""
    if (snapshot.intent != "workout" or planning_blueprint is None
            or planning_blueprint.outcome is not recommendation_planning.RecommendationOutcome.RECOMMEND):
        return None
    facts = {key: fact.value for key, fact in snapshot.profile.items()}
    if recovering:
        facts["recoveryFeel"] = "limited"
    all_excluded_patterns = (
        frozenset(brain_excluded_movement_patterns)
        | frozenset(fitness_excluded_movement_patterns)
    )
    if followup is not None:
        if previous_workout is None:
            raise TrainingRuntimeError("previous workout is required for this change")
        return apply_followup(
            followup=followup,
            previous=previous_workout,
            recommendation_blueprint_id=planning_blueprint.blueprint_id,
            facts=facts,
            locked_preferences=snapshot.locked_preferences.as_dict(),
            advisory_preferred_exercise_ids=getattr(advisory_signals, "preferred_exercise_ids", ()),
            external_excluded_movement_patterns=all_excluded_patterns,
        )
    return build_training_plan(
        recommendation_blueprint_id=planning_blueprint.blueprint_id,
        facts=facts,
        locked_preferences=snapshot.locked_preferences.as_dict(),
        requested_split=planning_blueprint.training_split,
        excluded_movement_patterns=all_excluded_patterns,
        advisory_preferred_exercise_ids=getattr(advisory_signals, "preferred_exercise_ids", ()),
    )


# Brain constraints use a wider movement vocabulary than the deterministic
# registry.  This is the only approved projection into selection: it can remove
# typed movement families, never add exercises or alter prescriptions.
_BRAIN_CONSTRAINT_PATTERNS = {
    "heavy_hinge": frozenset({MovementPattern.HINGE}),
    "deep_loaded_knee_flexion": frozenset({MovementPattern.SQUAT, MovementPattern.LUNGE}),
    "high_impact": frozenset({MovementPattern.SQUAT, MovementPattern.LUNGE}),
    "unsupported_balance": frozenset({MovementPattern.LUNGE}),
    "high_fall_risk": frozenset({MovementPattern.LUNGE}),
    "contact_collision": frozenset({MovementPattern.LUNGE}),
    "contact_fall_risk": frozenset({MovementPattern.LUNGE}),
    "heavy_isometric": frozenset({MovementPattern.CORE_ANTI_EXTENSION}),
    "push": frozenset({MovementPattern.HORIZONTAL_PUSH, MovementPattern.VERTICAL_PUSH}),
    "press": frozenset({MovementPattern.HORIZONTAL_PUSH, MovementPattern.VERTICAL_PUSH}),
    "overhead": frozenset({MovementPattern.VERTICAL_PUSH}),
    "pull": frozenset({MovementPattern.HORIZONTAL_PULL, MovementPattern.VERTICAL_PULL}),
    "row": frozenset({MovementPattern.HORIZONTAL_PULL}),
    "pull_up": frozenset({MovementPattern.VERTICAL_PULL}),
    "push_up": frozenset({MovementPattern.HORIZONTAL_PUSH}),
    "plank": frozenset({MovementPattern.CORE_ANTI_EXTENSION}),
}


def _brain_training_exclusions(decision):
    """Project only explicitly mapped Brain constraints into engine exclusions."""
    excluded = set()
    for constraint in getattr(getattr(decision, "constraints", None), "items", ()):
        mapped = _BRAIN_CONSTRAINT_PATTERNS.get(getattr(constraint, "movement", ""))
        if mapped is None:
            raise TrainingRuntimeError("brain safety constraint is not representable by the training engine")
        excluded.update(mapped)
    return frozenset(excluded)


def _brain_enforcement_failure_reply(lang):
    if str(lang).lower() == "en":
        return "I can't safely provide a workout right now because I couldn't verify the required safety checks."
    return "Не мога безопасно да предоставя тренировка сега, защото не успях да потвърдя необходимите проверки за безопасност."


def _brain_enforcement_withheld_reply(directive, lang):
    """Deterministic terminal delivery for a Brain decision that withholds training."""
    if directive.get("mode") == "route":
        return decision_engine.controlled_response(
            decision_engine.DecisionResult("route", "workout", "brain_safety_route", (), 1.0), lang)
    if str(lang).lower() == "en":
        return "I can't safely provide a workout right now. Let's focus on the safer next step first."
    return "Не мога безопасно да предоставя тренировка в момента. Нека първо се фокусираме върху по-безопасната следваща стъпка."


def _resolve_brain_training_enforcement(profile, message, conversation, *, physiology=None, model=None):
    """Return one authoritative Brain decision and its typed selection exclusions."""
    decision = brain_cascade.decide(
        profile if isinstance(profile, dict) else {}, message=message,
        conversation=conversation if isinstance(conversation, list) else [],
        physiology=physiology, model=model,
    )
    directive = brain_enforcement.render(decision)
    exclusions = (_brain_training_exclusions(decision)
                  if directive["should_generate_workout"] else frozenset())
    return decision, directive, exclusions


def _brain_enforcement_physiology(user_id):
    try:
        return athlete_store.physiology(user_id) if user_id else None
    except Exception:
        return None


def _shoulder_validator_id(exercise_id):
    """Map a namespaced registry ID to the shoulder index's explicit movement ID.

    The training registry owns stable IDs such as ``bodyweight.squat``. The
    shoulder index owns its canonical movement IDs such as ``bodyweight_squat``
    or ``squat``. An unknown registry ID is deliberately left unknown so the
    existing validator fails closed.
    """
    value = str(exercise_id or "")
    for candidate in (value, value.replace(".", "_"), value.rsplit(".", 1)[-1]):
        if candidate in EXERCISE_SHOULDER_LOAD:
            return candidate
    return value


def _validate_training_plan_shoulder_safety(plan, profile, *, constraints=None):
    """Validate the final immutable plan before renderer and Composer delivery."""
    try:
        if constraints is None:
            constraints = brain_cascade.decide(
                profile if isinstance(profile, dict) else {}
            ).constraints
        exercises = [
            {"canonical_id": _shoulder_validator_id(prescription.exercise_id)}
            for session in plan.sessions
            for prescription in session.prescriptions
        ]
        return shoulder_validator.validate_blueprint(exercises, constraints)
    except Exception as error:
        print(f"[training-engine] shoulder validation unavailable: {type(error).__name__}")
        return None


def _shoulder_constraint_state(profile):
    """Return ``active``, ``none``, or ``unavailable`` for delivery decisions."""
    try:
        constraints = brain_cascade.decide(
            profile if isinstance(profile, dict) else {}
        ).constraints
        if shoulder_validator.is_shoulder_constraint_active(constraints):
            return "active"
        return "none"
    except Exception as error:
        print(f"[training-engine] shoulder constraint lookup failed: {type(error).__name__}")
        return "unavailable"


def _shoulder_safety_failure_reply(lang):
    if str(lang).lower() == "en":
        return "I can't safely deliver this workout with the current shoulder restriction."
    return "Не мога безопасно да изпратя тази тренировка при текущото ограничение за рамото."


def _safety_constraints_unavailable_reply(lang):
    if str(lang).lower() == "en":
        return "I can't safely deliver this workout because I couldn't verify the current safety constraints."
    return "Не мога безопасно да изпратя тази тренировка, защото не успях да потвърдя текущите ограничения за безопасност."


def _explicit_health_restriction_reply(lang):
    """Terminal non-medical reply for an explicit restriction outside the taxonomy."""
    if str(lang).lower() == "en":
        return ("I can see the restriction you've provided, but I can't safely translate "
                "it into a training plan without risking going beyond it. Please follow "
                "the restriction exactly and confirm the permitted activity with your "
                "healthcare professional before I build the workout.")
    return ("Виждам ограничението, което си посочил, но не мога безопасно да го "
            "преведа в тренировъчен план, без риск да изляза извън него. Спазвай "
            "ограничението точно и потвърди разрешената активност с медицинския си "
            "специалист, преди да изградя тренировката.")


def _explicit_health_restriction_acknowledgement(lang):
    """Terminal acknowledgement for a supported restriction-only turn."""
    if str(lang).lower() == "en":
        return "Got it. I'll keep that movement restriction out of future workouts."
    return "Разбрах. Ще изключвам това ограничено движение от следващите ти тренировки."


def _fitness_limitation_reply(state, lang):
    english = str(lang).lower() == "en"
    if state is FitnessLimitationState.ACTIVE:
        return ("Got it. I'll keep overhead pressing out while this temporary fitness limitation is active."
                if english else
                "\u0420\u0430\u0437\u0431\u0440\u0430\u0445. \u0429\u0435 \u0438\u0437\u043a\u043b\u044e\u0447\u0430 \u043f\u0440\u0435\u0441\u0438\u0442\u0435 \u043d\u0430\u0434 \u0433\u043b\u0430\u0432\u0430, \u0434\u043e\u043a\u0430\u0442\u043e \u0442\u043e\u0432\u0430 \u0432\u0440\u0435\u043c\u0435\u043d\u043d\u043e \u0444\u0438\u0442\u043d\u0435\u0441 \u043e\u0433\u0440\u0430\u043d\u0438\u0447\u0435\u043d\u0438\u0435 \u0435 \u0430\u043a\u0442\u0438\u0432\u043d\u043e.")
    if state is FitnessLimitationState.RECOVERING:
        return ("Understood. I'll keep the overhead restriction while you ease back into training."
                if english else
                "\u0420\u0430\u0437\u0431\u0440\u0430\u0445. \u0429\u0435 \u0437\u0430\u043f\u0430\u0437\u044f \u043e\u0433\u0440\u0430\u043d\u0438\u0447\u0435\u043d\u0438\u0435\u0442\u043e \u0437\u0430 \u043f\u0440\u0435\u0441\u0438 \u043d\u0430\u0434 \u0433\u043b\u0430\u0432\u0430, \u0434\u043e\u043a\u0430\u0442\u043e \u0441\u0435 \u0432\u0440\u044a\u0449\u0430\u0448 \u043f\u043e\u0441\u0442\u0435\u043f\u0435\u043d\u043d\u043e \u043a\u044a\u043c \u0442\u0440\u0435\u043d\u0438\u0440\u043e\u0432\u043a\u0438\u0442\u0435.")
    return ("Got it. I've cleared the temporary shoulder limitation. Other saved restrictions still apply."
            if english else
            "\u0420\u0430\u0437\u0431\u0440\u0430\u0445. \u041f\u0440\u0435\u043c\u0430\u0445\u043d\u0430\u0445 \u0432\u0440\u0435\u043c\u0435\u043d\u043d\u043e\u0442\u043e \u043e\u0433\u0440\u0430\u043d\u0438\u0447\u0435\u043d\u0438\u0435 \u0437\u0430 \u0440\u0430\u043c\u043e\u0442\u043e. \u0414\u0440\u0443\u0433\u0438\u0442\u0435 \u0437\u0430\u043f\u0430\u0437\u0435\u043d\u0438 \u043e\u0433\u0440\u0430\u043d\u0438\u0447\u0435\u043d\u0438\u044f \u043e\u0441\u0442\u0430\u0432\u0430\u0442.")


def _clinician_clearance_reply(lang):
    if str(lang).lower() == "en":
        return "Got it. I've updated the clinician restriction from the explicit clearance you reported."
    return ("\u0420\u0430\u0437\u0431\u0440\u0430\u0445. \u0410\u043a\u0442\u0443\u0430\u043b\u0438\u0437\u0438\u0440\u0430\u0445 \u043e\u0433\u0440\u0430\u043d\u0438\u0447\u0435\u043d\u0438\u0435\u0442\u043e \u0441\u043f\u043e\u0440\u0435\u0434 \u0438\u0437\u0440\u0438\u0447\u043d\u043e\u0442\u043e \u0440\u0430\u0437\u0440\u0435\u0448\u0435\u043d\u0438\u0435 \u043e\u0442 "
            "\u043c\u0435\u0434\u0438\u0446\u0438\u043d\u0441\u043a\u0438\u044f \u0441\u043f\u0435\u0446\u0438\u0430\u043b\u0438\u0441\u0442, \u043a\u043e\u0435\u0442\u043e \u0441\u044a\u043e\u0431\u0449\u0438.")


def _restriction_turn_requests_workout(message):
    text = str(message or "").casefold()
    return any(token in text for token in (
        "workout", "training", "exercise", "work out", "warm-up", "warmup",
        "трениров", "упражнен", "загряв", "раздвиж",
    ))


def _cold_start_workout_reply(lang):
    """Deliver the Brain-approved starter session through the workout-card contract."""
    if str(lang).lower() == "en":
        return (
            "**Starter Workout · 15 minutes**\n"
            "| Exercise | Sets | Reps | Rest | Note |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| Easy march in place | 1 | 3 minutes | 30s | Comfortable pace |\n"
            "| Chair squat | 2 | 6–8 | 60s | Controlled range |\n"
            "| Wall push-up | 2 | 6–8 | 60s | Keep the body aligned |\n"
            "| Glute bridge | 2 | 8 | 60s | Pause briefly at the top |\n"
            "| Bird-dog | 2 | 6 per side | 60s | Keep the torso stable |\n\n"
            "Move slowly, rest as needed, and stop if you feel chest pain, dizziness, or unusual shortness of breath. "
            "Share your goal and any health conditions so the next session can be tailored."
        )
    return (
        "**Начална тренировка · 15 минути**\n"
        "| Упражнение | Серии | Повторения | Почивка | Бележка |\n"
        "| --- | --- | --- | --- | --- |\n"
        "| Леко ходене на място | 1 | 3 минути | 30 сек | Спокойно темпо |\n"
        "| Клек до стол | 2 | 6–8 | 60 сек | Контролиран обхват |\n"
        "| Лицеви опори на стена | 2 | 6–8 | 60 сек | Дръж тялото подравнено |\n"
        "| Глутеус мост | 2 | 8 | 60 сек | Кратка пауза горе |\n"
        "| Bird-dog | 2 | 6 на страна | 60 сек | Дръж торса стабилен |\n\n"
        "Движи се бавно, почивай при нужда и спри при болка в гърдите, замайване или необичаен задух. "
        "Сподели целта си и здравословни ограничения, за да персонализирам следващата сесия."
    )


def _advance_active_training_plan(plan, payload):
    """Apply traceable completed-workout evidence to one active training plan.

    Legacy browser workout logs intentionally do not enter here: they lack the
    immutable exercise and plan identities required for a safe revision.
    """
    if not isinstance(payload, dict):
        return plan
    raw_workouts = payload.get("completed_workouts")
    if raw_workouts is None and payload.get("completed_workout") is not None:
        raw_workouts = [payload["completed_workout"]]
    if raw_workouts is None:
        return plan
    if plan is None:
        raise TrainingRuntimeError("training lifecycle requires an active training plan")
    if not isinstance(raw_workouts, list) or not raw_workouts:
        raise TrainingRuntimeError("training lifecycle requires completed workout evidence")
    raw_recovery = payload.get("recovery")
    if not isinstance(raw_recovery, dict):
        raise TrainingRuntimeError("training lifecycle requires verified recovery evidence")
    try:
        workouts = tuple(workout_result_from_payload(item, plan=plan) for item in raw_workouts)
        result = advance_training_lifecycle(
            plan=plan,
            workouts=workouts,
            recovery=recovery_from_payload(raw_recovery),
        )
    except (TypeError, ValueError) as error:
        raise TrainingRuntimeError("training lifecycle evidence was rejected") from error
    return result.revision.revised_plan


def _persona_expert_communication_active():
    return os.getenv("PERSONA_EXPERT_COMMUNICATION_ACTIVE", "false").strip().lower() == "true"


def _persona_expert_training_active():
    """Allow bounded Persona/Expert advice to influence training only by opt-in."""
    return os.getenv("PERSONA_EXPERT_TRAINING_ACTIVE", "false").strip().lower() == "true"


def _conversation_composer_active():
    return os.getenv("CONVERSATION_COMPOSER_ACTIVE", "false").strip().lower() == "true"


def _nutrition_engine_v2_shadow_active():
    # Read-only Nutrition Engine V2 shadow. Fail-closed: default/invalid/missing → off.
    return os.getenv("NUTRITION_ENGINE_V2_SHADOW", "false").strip().lower() == "true"


def _nutrition_engine_v2_active():
    """Canonical V2 delivery is opt-in and independent from shadow evaluation."""
    return os.getenv("NUTRITION_ENGINE_V2_ACTIVE", "false").strip().lower() == "true"


def _shadow_feature_enabled(name):
    return os.getenv(name, "false").strip().lower() == "true"


_MEDICAL_HOLD_KEY = "_medical_hold"


def _medical_hold_from_message(message, *, conversation=None, profile=None):
    """Persist only a generic safety boundary; internal matches never surface."""
    decision = assess_health_scope(
        message=message,
        conversation=conversation if isinstance(conversation, list) else (),
        profile=profile if isinstance(profile, dict) else None,
    )
    if decision.scope is HealthSafetyScope.MEDICAL_BOUNDARY:
        return {"status": "ACTIVE_MEDICAL_HOLD", "reason_category": "MEDICAL_BOUNDARY",
                "workout_blocked": True, "session_blocked": True}
    return None


def _medical_hold_reply(lang, correction=False):
    return medical_boundary_message(lang)


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


def _evaluate_training_persona_expert(snapshot, decision):
    """Return bounded advice only when its explicit production flag is enabled."""
    if (decision.outcome != "recommend" or decision.intent != "workout"
            or not _persona_expert_training_active()):
        return None, None
    match, consensus, _trace = _evaluate_persona_expert(snapshot, decision, False)
    if match is None or consensus is None:
        return None, (match, consensus)
    signals = persona_expert_training_signals(
        persona_match=match, expert_consensus=consensus)
    return (signals if signals.preferred_exercise_ids else None), (match, consensus)


def _training_persona_expert_signals(snapshot, decision):
    """Compatibility seam for tests and non-delivery callers."""
    signals, _evaluation = _evaluate_training_persona_expert(snapshot, decision)
    return signals


def _shadow_expert_domains(result):
    """Return only broad domains; rule IDs never enter diagnostic logs."""
    if result is None:
        return ()
    ready = {
        rule.rule_id: rule.domain
        for pack in load_expert_rule_packs()
        for rule in pack.rules if rule.runtime_ready
    }
    return tuple(sorted({ready[rule_id] for rule_id in result.applicable_rule_ids if rule_id in ready}))


def _persona_expert_shadow_observation(snapshot, decision, *, locale, authoritative_path,
                                       recommendation_engine_active, pre_evaluated=None):
    """Pure worker body: it returns safe categories and cannot affect delivery."""
    matcher_enabled = _shadow_feature_enabled("PERSONA_MATCHER_SHADOW")
    consensus_enabled = _shadow_feature_enabled("EXPERT_CONSENSUS_SHADOW")
    statuses = {"persona": "SKIPPED", "expert": "SKIPPED"}
    fallback = None
    match = consensus = None
    started = time.perf_counter()
    if matcher_enabled or consensus_enabled:
        try:
            shadow_observability.emit_metric("persona_started", component="persona", status="started",
                                              locale=locale, intent_category=decision.intent)
            if pre_evaluated is not None:
                match, consensus = pre_evaluated
            else:
                match = persona_matcher.match(snapshot, decision.intent)
            statuses["persona"] = "ABSTAIN" if match.abstained else "SUCCESS"
        except Exception:
            statuses["persona"] = "ERROR"
            fallback = "PERSONA_EXCEPTION"
    if consensus_enabled:
        if match is None:
            statuses["expert"] = "SKIPPED"
        else:
            try:
                shadow_observability.emit_metric("expert_started", component="expert", status="started",
                                                  locale=locale, intent_category=decision.intent)
                if pre_evaluated is None:
                    consensus = expert_consensus.evaluate(snapshot, match, decision.intent)
                statuses["expert"] = "ABSTAIN" if consensus.abstained else "SUCCESS"
            except Exception:
                statuses["expert"] = "ERROR"
                fallback = "EXPERT_EXCEPTION"
    return shadow_observability.ShadowObservation(
        locale=locale, authoritative_path=authoritative_path, authoritative_intent=decision.intent,
        brain_status="SKIPPED", persona_status=statuses["persona"], expert_status=statuses["expert"],
        persona_match_class=("ABSTAIN" if getattr(match, "abstained", False) else
                             "MATCHED" if match is not None else None),
        expert_domain_classes=_shadow_expert_domains(consensus),
        decision_parity="NOT_COMPARABLE", safety_parity="NOT_COMPARABLE",
        constraint_parity="NOT_COMPARABLE", duration_ms=(time.perf_counter() - started) * 1000,
        fallback_category=fallback,
    )


def _brain_shadow_observation(profile, message, conversation, model, *, locale, authoritative_path,
                              authoritative_intent):
    """Run the existing Brain cascade without retaining its raw trace or evidence."""
    started = time.perf_counter()
    try:
        shadow_observability.emit_metric("brain_started", component="brain", status="started",
                                          locale=locale, intent_category=authoritative_intent)
        brain_inspector.inspect(profile, message=message, conversation=conversation, model=model,
                                decision_id=str(_uuid.uuid4()))
        status, fallback = "SUCCESS", None
    except Exception:
        status, fallback = "ERROR", "BRAIN_EXCEPTION"
    return shadow_observability.ShadowObservation(
        locale=locale, authoritative_path=authoritative_path, authoritative_intent=authoritative_intent,
        brain_status=status, persona_status="SKIPPED", expert_status="SKIPPED",
        persona_match_class=None, expert_domain_classes=(), decision_parity="NOT_COMPARABLE",
        safety_parity="NOT_COMPARABLE", constraint_parity="NOT_COMPARABLE",
        duration_ms=(time.perf_counter() - started) * 1000, fallback_category=fallback,
    )


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


def _active_workout_recommendation(snapshot, decision, recommendation_engine_active,
                                   communication_active=False, planning_blueprint=None):
    """Use persona/expert evidence only when at least one system can act on it."""
    if (planning_blueprint is not None
            and planning_blueprint.outcome is not recommendation_planning.RecommendationOutcome.RECOMMEND):
        return None, None, "legacy", None, None
    authority = _workout_authority(snapshot, decision)
    if authority is None:
        return None, None, "legacy", None, None
    match, consensus, trace = _evaluate_persona_expert(snapshot, decision, recommendation_engine_active)
    if match is None or consensus is None or (match.abstained and consensus.abstained):
        return None, trace, "legacy", None, None
    try:
        blueprint = recommendation_architect.design(
            "workout", decision=decision, profile={},
            preferences=dict(authority.locked_preferences), subject=snapshot.subject.identifier, record=False,
            expert_consensus=consensus,
            persona_adaptation=_persona_adaptation(match), authority=authority,
            planning_blueprint=planning_blueprint,
        )
        persona_projection = expert_constraints = None
        if blueprint is not None and communication_active:
            try:
                persona_projection, expert_constraints = persona_expert_projection.build_projections(
                    persona_adaptation=_persona_adaptation(match), authority=authority,
                    blueprint=blueprint, expert_consensus=consensus)
                if persona_projection.is_none and expert_constraints.is_none:
                    persona_projection = expert_constraints = None
            except Exception:
                persona_projection = expert_constraints = None
        return (blueprint, trace, "persona_expert" if blueprint is not None else "legacy",
                persona_projection, expert_constraints)
    except Exception:
        return None, trace, "legacy", None, None


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
        requested_session_start = bool(data.get("session_start"))
        voice_requested = bool(data.get("voice"))
        daypart = str(data.get("daypart", ""))[:12]

        msg_limit = 4000 if is_elite else 1000
        user_message = str(data.get("message", ""))[:msg_limit]
        # A greeting exists only for a genuinely empty opening action. A message
        # supplied with session_start is a real user turn and must win.
        session_start = requested_session_start and not user_message.strip()
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
        _workout_scope = _workout_conversation_scope(data, chat_uid, g.device_id)
        _workout_followup = parse_workout_followup(user_message)
        _previous_workout = _last_workout_for(_workout_scope)
        _followup_reply = None
        _followup_failure_reply = None
        if _workout_followup is not None:
            if _workout_followup.requires_previous and _previous_workout is None:
                _followup_reply = followup_message("previous workout is required", lang)
            elif (_workout_followup.operation.value == "repeat_previous" and
                  _workout_is_stale(_workout_scope)):
                _followup_reply = (
                    "A new restriction has been recorded, so I can't repeat the earlier workout. Ask me to build a new one."
                    if lang == "en" else
                    "Има ново ограничение, затова не мога да повторя предишната тренировка. Поискай нова."
                )
            elif _workout_followup.operation.value == "unknown_exercise":
                _followup_reply = followup_message("unknown requested exercise", lang)
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

        # Anonymous tabs have no server profile to reload on the next turn. Keep
        # only explicit, typed restriction declarations in the same tab scope so
        # a subsequent workout revision cannot silently lose them.
        _scoped_health_restrictions = _conversation_health_restrictions(_workout_scope)
        if _scoped_health_restrictions and isinstance(profile, dict):
            profile = dict(profile)
            existing_restrictions = profile.get("healthRestrictions")
            if isinstance(existing_restrictions, (tuple, list, set, frozenset)):
                profile["healthRestrictions"] = list(dict.fromkeys(
                    (*existing_restrictions, *_scoped_health_restrictions)))
            elif existing_restrictions:
                profile["healthRestrictions"] = list(dict.fromkeys(
                    (existing_restrictions, *_scoped_health_restrictions)))
            else:
                profile["healthRestrictions"] = list(_scoped_health_restrictions)

        if is_elite:
            memory_cap = 60 if is_pro else 10
        else:
            memory_cap = 12

        if chat_uid:
            try:
                history = store.list_conversation(chat_uid, limit=memory_cap)
            except Exception as _ce:
                print(f"[chat] conversation load failed: {_ce}")

        # Temporary self-reported limitations have their own lifecycle. They are
        # never promoted into permanent clinician/medical restrictions.
        _legacy_fitness_limitation = None
        if isinstance(profile, dict):
            profile = dict(profile)
            for _field in ("healthRestrictions", "trainingRestrictions"):
                if _field not in profile:
                    continue
                _remaining, _migrated = migrate_temporary_fitness_restrictions(
                    profile.get(_field))
                if _migrated is not None:
                    _legacy_fitness_limitation = _migrated
                    if _remaining:
                        profile[_field] = list(_remaining)
                    else:
                        profile.pop(_field, None)
        _scoped_remaining, _scoped_migrated = migrate_temporary_fitness_restrictions(
            _scoped_health_restrictions)
        if _scoped_migrated is not None:
            _legacy_fitness_limitation = _scoped_migrated
            _replace_conversation_health_restrictions(
                _workout_scope, _scoped_remaining)
            _scoped_health_restrictions = _scoped_remaining
        _legacy_fitness_migrated = _legacy_fitness_limitation is not None

        _fitness_limitation = (
            fitness_limitation_from_profile(profile)
            if isinstance(profile, dict) else None
        ) or _conversation_fitness_limitation(_workout_scope) or _legacy_fitness_limitation
        if _fitness_limitation is None and isinstance(history, list):
            _fitness_limitation = fitness_limitation_from_history(history)
        _previous_fitness_limitation = _fitness_limitation
        _fitness_limitation = transition_fitness_limitation(
            _fitness_limitation, user_message)
        _fitness_limitation_changed = _fitness_limitation != _previous_fitness_limitation
        _self_reported_limitation_message = (
            transition_fitness_limitation(None, user_message) is not None)
        if _fitness_limitation is not None:
            profile = dict(profile or {})
            profile["_fitness_limitation_state"] = _fitness_limitation.to_record()
            _record_conversation_fitness_limitation(_workout_scope, _fitness_limitation)
        _fitness_excluded_movement_patterns = limitation_excluded_patterns(
            _fitness_limitation)
        _recovering_light_session_requested = is_recovering_light_session_request(
            user_message, _fitness_limitation)
        _fitness_training_kwargs = ({
            "fitness_excluded_movement_patterns": _fitness_excluded_movement_patterns,
            "recovering": (_fitness_limitation is not None and
                           _fitness_limitation.state is FitnessLimitationState.RECOVERING),
        } if _fitness_excluded_movement_patterns else {})

        # A clinician restriction changes only after an explicit clinician
        # clearance for the same typed movement family.
        _clinician_clearance = clinician_clearance_patterns(user_message)
        _clinician_clearance_changed = False
        if _clinician_clearance:
            profile, _clinician_clearance_changed = _apply_clinician_clearance(
                profile, _clinician_clearance)
            scoped_remaining = remove_cleared_clinician_restrictions(
                _scoped_health_restrictions, _clinician_clearance)
            if scoped_remaining != tuple(_scoped_health_restrictions):
                _replace_conversation_health_restrictions(
                    _workout_scope, scoped_remaining)

        # Medical safety is server-authoritative state, not assistant prose.  Persist it
        # before planning so flags, fallbacks, blueprints, and renderers cannot bypass it.
        _medical_hold = profile.get(_MEDICAL_HOLD_KEY) if isinstance(profile, dict) else None
        if _medical_hold is None:
            _medical_hold = _conversation_medical_hold(_workout_scope)
        _health_scope = assess_health_scope(
            message=user_message,
            conversation=history if isinstance(history, list) else (),
            profile=profile if isinstance(profile, dict) else None,
        )
        _new_explicit_health_restrictions = explicit_restrictions_from_message(user_message)
        _restriction_controlled_reply = None
        if (_new_explicit_health_restrictions and isinstance(profile, dict)
                and not _self_reported_limitation_message):
            profile = dict(profile)
            existing_restrictions = profile.get("healthRestrictions")
            if isinstance(existing_restrictions, (tuple, list, set, frozenset)):
                profile["healthRestrictions"] = [*existing_restrictions, *_new_explicit_health_restrictions]
            elif existing_restrictions:
                profile["healthRestrictions"] = [existing_restrictions, *_new_explicit_health_restrictions]
            else:
                profile["healthRestrictions"] = list(_new_explicit_health_restrictions)
            _record_conversation_health_restrictions(
                _workout_scope, _new_explicit_health_restrictions)
            try:
                project_explicit_health_restrictions(profile)
            except UnsupportedHealthRestrictionError:
                _restriction_controlled_reply = _explicit_health_restriction_reply(lang)
            else:
                if not _restriction_turn_requests_workout(user_message):
                    _restriction_controlled_reply = _explicit_health_restriction_acknowledgement(lang)
        if (_fitness_limitation_changed and _fitness_limitation is not None
                and not _restriction_turn_requests_workout(user_message)):
            _restriction_controlled_reply = _fitness_limitation_reply(
                _fitness_limitation.state, lang)
        if (_clinician_clearance_changed
                and not _restriction_turn_requests_workout(user_message)):
            _restriction_controlled_reply = _clinician_clearance_reply(lang)
        if (chat_uid and (_fitness_limitation_changed or _legacy_fitness_migrated
                          or _clinician_clearance_changed
                          or bool(_new_explicit_health_restrictions))):
            store.save_profile(chat_uid, profile)
        _new_medical_hold = _medical_hold_from_message(
            user_message, conversation=history, profile=profile)
        if _new_medical_hold is not None:
            _new_medical_hold["created_at"] = _dt.datetime.now(_dt.timezone.utc).isoformat()
            _new_medical_hold["source_message_id"] = _uuid.uuid4().hex
            profile = dict(profile or {})
            profile[_MEDICAL_HOLD_KEY] = _new_medical_hold
            _medical_hold = _new_medical_hold
            _record_conversation_medical_hold(_workout_scope, _new_medical_hold)
            if chat_uid:
                store.save_profile(chat_uid, profile)

        # Phase A2 compatibility bridge: ContextSnapshot now owns the normal-chat
        # context boundary, then its legacy adapter restores the exact variables
        # consumed by the unchanged prompt assembly below. First-contact keeps its
        # established path until its own integration phase.
        _recommendation_blueprint = None
        _recommendation_plan = None
        _recommendation_trace = None
        _recommendation_path = "legacy"
        _snapshot = None
        _shadow_decision = None
        _shadow_request_id = _uuid.uuid4().hex
        _recommendation_active = _recommendation_engine_active()
        _training_engine_active_for_request = _training_engine_active()
        _training_plan_blueprint = None
        _training_engine_failure = None
        _shoulder_safety_validation = None
        _brain_enforcement_decision = None
        _brain_enforcement_directive = None
        _brain_enforcement_exclusions = frozenset()
        _brain_enforcement_failure = False
        _brain_enforcement_prompt_addendum = ""
        enforce_event = None
        _training_advisory_signals = None
        _training_persona_expert_evaluation = None
        _persona_expert_communication_active_for_request = _persona_expert_communication_active()
        _persona_projection = None
        _expert_communication_constraints = None
        _conversation_composer_active_for_request = _conversation_composer_active()
        _conversation_policy = None
        _conversation_frame = None
        if not is_first_contact:
            _legacy_profile = profile if isinstance(profile, dict) else {}
            _legacy_history = history if isinstance(history, list) else []
            _shadow_intent = decision_engine.classify_intent(user_message)
            if _recovering_light_session_requested:
                _shadow_intent = "workout"
            if (_workout_followup is not None and _previous_workout is not None
                    and _workout_followup.requires_previous):
                _shadow_intent = "workout"
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
            _planning_request_intent = _planning_intent(
                user_message, history, _shadow_intent,
                require_explicit_workout=brain_config.brain_enforce())
            if (_workout_followup is not None and _previous_workout is not None
                    and _workout_followup.requires_previous):
                _planning_request_intent = "workout"
            if _followup_reply is not None:
                _planning_request_intent = None
                _recommendation_plan, _planning_reply = None, _followup_reply
            else:
                _recommendation_plan, _planning_reply = _plan_coaching_request(
                    _snapshot, _planning_request_intent, history, lang)
            if (_training_engine_active_for_request and _shadow_decision.outcome == "recommend"
                    and _shadow_decision.intent == "workout"
                    and not (_medical_hold and _medical_hold.get("status") == "ACTIVE_MEDICAL_HOLD")
                    and _recommendation_plan is not None
                    and _recommendation_plan.outcome is recommendation_planning.RecommendationOutcome.RECOMMEND):
                try:
                    if brain_config.brain_enforce() and _training_engine_active_for_request:
                        try:
                            (_brain_enforcement_decision, _brain_enforcement_directive,
                             _brain_enforcement_exclusions) = _resolve_brain_training_enforcement(
                                 profile, user_message, history,
                                 physiology=_brain_enforcement_physiology(chat_uid))
                        except Exception as _brain_error:
                            print(f"[enforce] training decision unavailable: {type(_brain_error).__name__}")
                            _brain_enforcement_failure = True
                            raise TrainingRuntimeError("brain enforcement unavailable")
                        if not _brain_enforcement_directive["should_generate_workout"]:
                            raise TrainingRuntimeError("brain enforcement withheld training")
                    (_training_advisory_signals,
                     _training_persona_expert_evaluation) = _evaluate_training_persona_expert(
                         _snapshot, _shadow_decision)
                    if _workout_followup is not None and _workout_followup.requires_previous:
                        _training_plan_blueprint = _active_training_plan(
                            _snapshot, _recommendation_plan,
                            followup=_workout_followup, previous_workout=_previous_workout,
                            **({"advisory_signals": _training_advisory_signals}
                               if _training_advisory_signals is not None else {}),
                            **({"brain_excluded_movement_patterns": _brain_enforcement_exclusions}
                               if _brain_enforcement_exclusions else {}),
                            **_fitness_training_kwargs,
                        )
                    else:
                        _training_plan_blueprint = _active_training_plan(
                            _snapshot, _recommendation_plan,
                            **({"advisory_signals": _training_advisory_signals}
                               if _training_advisory_signals is not None else {}),
                            **({"brain_excluded_movement_patterns": _brain_enforcement_exclusions}
                               if _brain_enforcement_exclusions else {}),
                            **_fitness_training_kwargs)
                    _training_plan_blueprint = _advance_active_training_plan(_training_plan_blueprint, data)
                    if _training_plan_blueprint is None:
                        _constraint_state = _shoulder_constraint_state(profile)
                        _training_engine_failure = {
                            "active": "training_engine_shoulder_safety_contract",
                            "unavailable": "training_engine_safety_constraints_unavailable",
                        }.get(_constraint_state, "training_engine_profile_contract")
                    else:
                        _shoulder_safety_validation = _validate_training_plan_shoulder_safety(
                            _training_plan_blueprint, profile,
                            **({"constraints": _brain_enforcement_decision.constraints}
                               if _brain_enforcement_decision is not None else {}))
                        if _shoulder_safety_validation is None:
                            _training_plan_blueprint = None
                            _training_engine_failure = "training_engine_safety_constraints_unavailable"
                        elif not _shoulder_safety_validation.passed:
                            _training_plan_blueprint = None
                            _training_engine_failure = "training_engine_shoulder_safety_contract"
                        else:
                            _recommendation_path = "deterministic_training"
                except TrainingRuntimeError as _training_error:
                    print(f"[training-engine] construction rejected: {type(_training_error).__name__}")
                    if not (_brain_enforcement_failure or
                            (_brain_enforcement_directive is not None and
                             not _brain_enforcement_directive["should_generate_workout"])):
                        _constraint_state = _shoulder_constraint_state(profile)
                        if _constraint_state == "active":
                            _training_engine_failure = "training_engine_shoulder_safety_contract"
                        elif _constraint_state == "unavailable":
                            _training_engine_failure = "training_engine_safety_constraints_unavailable"
                        elif str(_training_error) == "explicit health restriction is unsupported":
                            _training_engine_failure = "training_engine_explicit_health_restriction"
                        elif _workout_followup is not None:
                            _followup_failure_reply = followup_message(_training_error, lang)
                        else:
                            _training_engine_failure = "training_engine_profile_contract"
            _active_workout = (not (_medical_hold and _medical_hold.get("status") == "ACTIVE_MEDICAL_HOLD") and
                               not _training_engine_active_for_request and _recommendation_active and _shadow_decision.outcome == "recommend" and
                               _shadow_decision.intent == "workout"
                               and (_recommendation_plan is None or
                                    _recommendation_plan.outcome is recommendation_planning.RecommendationOutcome.RECOMMEND))
            if _active_workout:
                (_recommendation_blueprint, _recommendation_trace,
                 _recommendation_path, _persona_projection,
                 _expert_communication_constraints) = _active_workout_recommendation(
                     _snapshot, _shadow_decision, _recommendation_active,
                     _persona_expert_communication_active_for_request, _recommendation_plan)
            else:
                # Persona/expert evaluation is scheduled after authoritative delivery.
                # No shadow result is available to this request's planning or prompt.
                _shadow_persona_match = _shadow_expert_consensus = None
            # Safety enforcement retains precedence when deliberately enabled.
            # The planner still runs for observability and deterministic inputs,
            # but it must not prevent an approved safety decision from shaping
            # the same request.
            _controlled_reply = (
                _planning_reply
                if (_planning_reply is not None and
                    ((_planning_request_intent == "nutrition" and
                      nutrition_conversation.is_plan_request(user_message, history))
                     or not brain_config.brain_enforce()))
                else decision_engine.controlled_response(_shadow_decision, lang)
            )
            if _followup_reply is not None:
                _controlled_reply = _followup_reply
            if _followup_failure_reply is not None:
                _controlled_reply = _followup_failure_reply
            if _training_engine_failure is not None:
                # An incomplete or legacy browser profile must never turn an
                # explicit workout request into the generic clarify message.
                # The bounded starter session is safe, deterministic, and keeps
                # the coaching turn actionable while the profile is completed.
                if _training_engine_failure == "training_engine_safety_constraints_unavailable":
                    _controlled_reply = _safety_constraints_unavailable_reply(lang)
                elif _training_engine_failure == "training_engine_shoulder_safety_contract":
                    _controlled_reply = _shoulder_safety_failure_reply(lang)
                elif _training_engine_failure == "training_engine_explicit_health_restriction":
                    _controlled_reply = _explicit_health_restriction_reply(lang)
                else:
                    _controlled_reply = _cold_start_workout_reply(lang)
                    if _requests_workout_and_nutrition(user_message):
                        _controlled_reply += _combined_request_follow_up(lang)
            if (_restriction_controlled_reply is not None and
                    not (_medical_hold and _medical_hold.get("status") == "ACTIVE_MEDICAL_HOLD")):
                _controlled_reply = _restriction_controlled_reply
            if _conversation_composer_active_for_request:
                try:
                    _conversation_policy = conversation_composer.build_policy(
                        decision=_shadow_decision, message=user_message, conversation=history,
                        voice=voice_requested, session_start=session_start,
                        blueprint_present=(_recommendation_blueprint is not None or _training_plan_blueprint is not None),
                        recommendation_kind=("workout" if _training_plan_blueprint is not None
                                             else getattr(_recommendation_blueprint, "kind", None)),
                        structured_delivery=(_recommendation_blueprint is not None or _training_plan_blueprint is not None),
                        respect_projection_preferences=_persona_expert_communication_active_for_request,
                    )
                except Exception as _composer_error:
                    print(f"[conversation-composer] policy failed: {_composer_error}")
            if not _recommendation_active and _planning_reply is None:
                _shadow_recommendation(_snapshot, _shadow_decision, profile)
            if _recommendation_trace is not None:
                _observe_shadow_trace_for_testing(_recommendation_trace.with_delivery(
                    blueprint_invoked=(_recommendation_blueprint is not None or _training_plan_blueprint is not None),
                    production_path_used=_recommendation_path))
        else:
            _controlled_reply = None

        profile_block = ""
        decision_state = "CONTINUE_CONVERSATION"
        # First-contact safety evaluation uses the same plan-selected model as
        # final delivery, so resolve it before either execution path begins.
        model_to_use = "gpt-4o" if is_pro else "gpt-4o-mini"
        if is_first_contact:
            _first_intent = decision_engine.classify_intent(user_message)
            if _recovering_light_session_requested:
                _first_intent = "workout"
            _first_planning_intent = _planning_intent(
                user_message, history, _first_intent,
                require_explicit_workout=brain_config.brain_enforce())
            # Coaching turns begin from verified Profile Cards. They never call
            # the legacy extraction model before deterministic planning; ordinary
            # first-contact conversation retains its established extraction path.
            if _first_planning_intent is None:
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
            _snapshot = context_builder.build_context(
                intent=_first_intent,
                subject=(context_builder.Subject("account", chat_uid, True)
                         if chat_uid else
                         context_builder.Subject("anonymous_device", g.device_id or _client_ip(), False)),
                request_time=_dt.datetime.now(_dt.timezone.utc),
                access={"plan": plan, "quota_status": db_status},
                db_profile=profile if chat_uid else None,
                browser_profile=profile if not chat_uid else None,
                db_conversation=history if chat_uid else None,
                browser_conversation=history if not chat_uid else None,
                db_workouts=pers_workouts if chat_uid else None,
                legacy_profile=profile,
                legacy_conversation=history,
                legacy_workouts=pers_workouts,
            )
            _shadow_decision = decision_engine.decide(_snapshot, _first_intent)
            _recommendation_plan, _planning_reply = _plan_coaching_request(
                _snapshot, _first_planning_intent, history, lang)
            if (_training_engine_active_for_request and _shadow_decision.outcome == "recommend"
                    and _shadow_decision.intent == "workout"
                    and not (_medical_hold and _medical_hold.get("status") == "ACTIVE_MEDICAL_HOLD")
                    and _recommendation_plan is not None
                    and _recommendation_plan.outcome is recommendation_planning.RecommendationOutcome.RECOMMEND):
                try:
                    if brain_config.brain_enforce() and _training_engine_active_for_request:
                        try:
                            (_brain_enforcement_decision, _brain_enforcement_directive,
                             _brain_enforcement_exclusions) = _resolve_brain_training_enforcement(
                                 profile, user_message, history,
                                 physiology=_brain_enforcement_physiology(chat_uid), model=model_to_use)
                        except Exception as _brain_error:
                            print(f"[enforce] training decision unavailable: {type(_brain_error).__name__}")
                            _brain_enforcement_failure = True
                            raise TrainingRuntimeError("brain enforcement unavailable")
                        if not _brain_enforcement_directive["should_generate_workout"]:
                            raise TrainingRuntimeError("brain enforcement withheld training")
                    (_training_advisory_signals,
                     _training_persona_expert_evaluation) = _evaluate_training_persona_expert(
                         _snapshot, _shadow_decision)
                    _training_plan_blueprint = _active_training_plan(
                        _snapshot, _recommendation_plan,
                        **({"advisory_signals": _training_advisory_signals}
                           if _training_advisory_signals is not None else {}),
                        **({"brain_excluded_movement_patterns": _brain_enforcement_exclusions}
                           if _brain_enforcement_exclusions else {}),
                        **_fitness_training_kwargs)
                    _training_plan_blueprint = _advance_active_training_plan(_training_plan_blueprint, data)
                    if _training_plan_blueprint is None:
                        _constraint_state = _shoulder_constraint_state(profile)
                        _training_engine_failure = {
                            "active": "training_engine_shoulder_safety_contract",
                            "unavailable": "training_engine_safety_constraints_unavailable",
                        }.get(_constraint_state, "training_engine_profile_contract")
                        if str(_training_error) == "explicit health restriction is unsupported":
                            _training_engine_failure = "training_engine_explicit_health_restriction"
                    else:
                        _shoulder_safety_validation = _validate_training_plan_shoulder_safety(
                            _training_plan_blueprint, profile,
                            **({"constraints": _brain_enforcement_decision.constraints}
                               if _brain_enforcement_decision is not None else {}))
                        if _shoulder_safety_validation is None:
                            _training_plan_blueprint = None
                            _training_engine_failure = "training_engine_safety_constraints_unavailable"
                        elif not _shoulder_safety_validation.passed:
                            _training_plan_blueprint = None
                            _training_engine_failure = "training_engine_shoulder_safety_contract"
                        else:
                            _recommendation_path = "deterministic_training"
                except TrainingRuntimeError as _training_error:
                    print(f"[training-engine] construction rejected: {type(_training_error).__name__}")
                    if not (_brain_enforcement_failure or
                            (_brain_enforcement_directive is not None and
                             not _brain_enforcement_directive["should_generate_workout"])):
                        _constraint_state = _shoulder_constraint_state(profile)
                        _training_engine_failure = {
                            "active": "training_engine_shoulder_safety_contract",
                            "unavailable": "training_engine_safety_constraints_unavailable",
                        }.get(_constraint_state, "training_engine_profile_contract")
            
            # 3. Decision mapping
            if _decision.s2.halt:
                decision_state = "SAFETY_STOP"
            elif (_recommendation_plan is not None
                  and _recommendation_plan.outcome is recommendation_planning.RecommendationOutcome.RECOMMEND):
                decision_state = "PLAN_READY"
            elif _recommendation_plan is not None:
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
            _controlled_reply = _planning_reply
            if _training_engine_failure is not None:
                if _training_engine_failure == "training_engine_safety_constraints_unavailable":
                    _controlled_reply = _safety_constraints_unavailable_reply(lang)
                elif _training_engine_failure == "training_engine_shoulder_safety_contract":
                    _controlled_reply = _shoulder_safety_failure_reply(lang)
                elif _training_engine_failure == "training_engine_explicit_health_restriction":
                    _controlled_reply = _explicit_health_restriction_reply(lang)
                else:
                    _controlled_reply = _cold_start_workout_reply(lang)
                    if _requests_workout_and_nutrition(user_message):
                        _controlled_reply += _combined_request_follow_up(lang)
            profile_block = _build_profile_block(profile, lang) if isinstance(profile, dict) else ""
            
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

        _nutrition_intent = decision_engine.classify_intent(user_message)
        _combined_coaching_request = _requests_workout_and_nutrition(user_message)
        _v2_shadow_full_day = nutrition_validation.is_full_day_request(user_message, history)
        _authoritative_nutrition_targets = _daily_nutrition_targets(user_message, profile_block, history)
        _nutrition_conversation = nutrition_conversation.begin(
            message=user_message,
            history=history,
            profile=profile if isinstance(profile, dict) else {},
            profile_block=profile_block,
            intent=_nutrition_intent,
            session_start=session_start,
            medical_route=_nutrition_intent == "medical",
            lang=lang,
            authoritative_targets=_authoritative_nutrition_targets,
        )
        nutrition_request_full_day = _nutrition_conversation.plan_requested
        nutrition_delivery_targets = (_nutrition_conversation.targets
                                      if _nutrition_conversation.state is nutrition_conversation.NutritionConversationState.PLAN_READY
                                      else None)
        # All nutrition advice and plans enter one request-scoped state machine.
        # Only plan-ready requests receive the complete daily-plan contract.
        nutrition_response_guard = _nutrition_conversation.response_guard
        nutrition_guard_targets = _nutrition_conversation.targets
        nutrition_delivery_target = (int(nutrition_delivery_targets.kcal)
                                     if nutrition_delivery_targets is not None else None)
        _nutrition_v2_active_for_request = _nutrition_engine_v2_active()
        _nutrition_v2_evaluation = None
        _nutrition_v2_authoritative_plan = None
        _nutrition_revision = nutrition_conversation.parse_revision_operation(user_message)
        _revised_nutrition_plan = None
        _nutrition_revision_failure = None
        if _nutrition_revision is not None:
            if not chat_uid:
                _nutrition_revision_failure = nutrition_conversation.revision_unavailable_message(lang)
            else:
                try:
                    records = store.list_nutrition_plans(chat_uid, limit=1)
                    if not records:
                        _nutrition_revision_failure = nutrition_conversation.revision_unavailable_message(lang)
                    else:
                        active_plan = nutrition_plan.from_record(records[0]["plan"])
                        _revised_nutrition_plan = nutrition_plan.apply_revision(active_plan, _nutrition_revision)
                        _nutrition_conversation = nutrition_conversation.revised(
                            _nutrition_conversation, active_plan.targets)
                except nutrition_plan.NutritionPlanError:
                    _nutrition_revision_failure = nutrition_conversation.revision_unsupported_message(lang)
                except Exception as revision_error:
                    print(f"[chat] nutrition revision failed: {type(revision_error).__name__}")
                    _nutrition_revision_failure = nutrition_conversation.revision_unsupported_message(lang)
            # A recognized typed revision has a deterministic terminal path and
            # must not be diverted into the normal unknown-intent response.
            _controlled_reply = None

        if (_nutrition_v2_active_for_request and nutrition_delivery_targets is not None
                and _nutrition_conversation.state is nutrition_conversation.NutritionConversationState.PLAN_READY
                and not (_medical_hold and _medical_hold.get("status") == "ACTIVE_MEDICAL_HOLD")):
            try:
                from nutrition_engine.canonical_delivery import evaluate_canonical_v2
                _nutrition_v2_evaluation = evaluate_canonical_v2(
                    language=lang,
                    targets=nutrition_delivery_targets,
                    restrictions=_nutrition_restrictions(profile),
                    medical_route=(getattr(_shadow_decision, "outcome", None) == "route"),
                )
                _nutrition_v2_authoritative_plan = _nutrition_v2_evaluation.plan
            except Exception as _v2_active_error:
                print(f"[nutrition-v2] canonical evaluation failed: {type(_v2_active_error).__name__}")

        # ── Nutrition Engine V2 SHADOW (read-only, flag-off by default) ──────
        # Non-blocking: reuses the already-computed canonical typed targets, builds
        # an immutable projection, and submits it to an isolated bounded background
        # worker. It never touches quota, persistence, SSE payloads/order, voice,
        # or the response. All V2 output is discarded (bounded counters only).
        # When the flag is off (default) nothing here runs — the module is not even
        # imported — so canonical behavior is byte-identical.
        if (_nutrition_engine_v2_shadow_active()
                and not (_medical_hold and _medical_hold.get("status") == "ACTIVE_MEDICAL_HOLD")):
            try:
                from nutrition_engine import shadow_hook as _v2_shadow
                if not getattr(g, "nutrition_v2_shadow_attempted", False):
                    _v2_elig = _v2_shadow.classify_eligibility(
                        flag_enabled=True,
                        is_nutrition=_v2_shadow_full_day,
                        is_full_day=_v2_shadow_full_day,
                        calorie_target=(nutrition_delivery_targets.kcal if nutrition_delivery_targets is not None else None),
                        protein_target=(nutrition_delivery_targets.protein if nutrition_delivery_targets is not None else None),
                        route_is_medical=(getattr(_shadow_decision, "outcome", None) == "route"),
                        session_start=session_start,
                        already_attempted=False,
                        allergy_prose=(profile.get("allergies") if isinstance(profile, dict) else None),
                        preference_tokens=(profile.get("foodPreferences") if isinstance(profile, dict) else None),
                    )
                    if _v2_elig.eligible:
                        g.nutrition_v2_shadow_attempted = True  # marks ATTEMPT, before dispatch
                        _v2_shadow.record_eligible()
                        if _nutrition_v2_evaluation is not None:
                            _v2_shadow.record_evaluated_result(_nutrition_v2_evaluation.result)
                        else:
                            _v2_proj = _v2_shadow.build_projection(
                                language=lang,
                                calorie_target=nutrition_delivery_targets.kcal,
                                protein_target=nutrition_delivery_targets.protein,
                                carbs_target=nutrition_delivery_targets.carbs,
                                fat_target=nutrition_delivery_targets.fat,
                            )
                            if not _v2_shadow.dispatch(_v2_proj):
                                _v2_shadow.record_skip(_v2_shadow.ShadowSkipReason.DISPATCH_SATURATED)
                    else:
                        _v2_shadow.record_skip(_v2_elig.reason)
            except Exception as _v2_err:  # hook can never affect the request
                _v2_runtime = locals().get("_v2_shadow")
                if _v2_runtime is not None:
                    _v2_runtime.log_runtime_error("hook_error", _v2_err)
                else:
                    import logging as _logging
                    _logging.getLogger("apex.nutrition_v2_shadow").warning(
                        "[nutrition-v2-shadow] event=hook_import_failed reason=runtime_error "
                        "exception=%s worker_id=unknown", type(_v2_err).__name__)

        if _medical_hold and _medical_hold.get("status") == "ACTIVE_MEDICAL_HOLD":
            # Highest authority: no workout or plan delivery can survive a hold, even
            # when a prior deterministic blueprint or legacy fallback was prepared.
            _recommendation_blueprint = None
            _training_plan_blueprint = None
            _recommendation_plan = None
            _planning_reply = None
            _controlled_reply = _medical_hold_reply(
                lang, correction=bool(_new_medical_hold is None and
                                       ("\u0434\u0430\u0432\u0430\u0448" in user_message.casefold() or
                                        "gave me" in user_message.casefold())))
            nutrition_delivery_targets = None
            nutrition_delivery_target = None
            nutrition_response_guard = False
            _revised_nutrition_plan = None
            _nutrition_revision_failure = None

        _brain_training_turn = (
            _training_plan_blueprint is not None
            or _explicit_workout_request(user_message)
            or (_workout_followup is not None and _previous_workout is not None)
        )
        if (brain_config.brain_enforce() and _brain_training_turn
                and _controlled_reply is None):
            if _brain_enforcement_failure:
                _training_plan_blueprint = None
                _recommendation_blueprint = None
                _recommendation_plan = None
                _controlled_reply = _brain_enforcement_failure_reply(lang)
            else:
                if _brain_enforcement_directive is None:
                    try:
                        if _training_engine_active_for_request:
                            (_brain_enforcement_decision, _brain_enforcement_directive,
                             _brain_enforcement_exclusions) = _resolve_brain_training_enforcement(
                                 profile, user_message, history,
                                 physiology=_brain_enforcement_physiology(chat_uid), model=model_to_use)
                        else:
                            _brain_enforcement_decision = brain_cascade.decide(
                                profile if isinstance(profile, dict) else {}, message=user_message,
                                conversation=history if isinstance(history, list) else [],
                                physiology=_brain_enforcement_physiology(chat_uid), model=model_to_use)
                            _brain_enforcement_directive = brain_enforcement.render(
                                _brain_enforcement_decision)
                    except Exception as _brain_error:
                        print(f"[enforce] training decision unavailable: {type(_brain_error).__name__}")
                        _brain_enforcement_failure = True
                        _training_plan_blueprint = None
                        _recommendation_blueprint = None
                        _recommendation_plan = None
                        _controlled_reply = _brain_enforcement_failure_reply(lang)
                if _brain_enforcement_directive is not None:
                    enforce_event = _brain_enforcement_directive["decision_event"]
                    if not _brain_enforcement_directive["should_generate_workout"]:
                        # Terminal authority: no pre-built deterministic or legacy
                        # artifact can reach Composer, renderer, or completion SSE.
                        _training_plan_blueprint = None
                        _recommendation_blueprint = None
                        _recommendation_plan = None
                        _controlled_reply = _brain_enforcement_withheld_reply(
                            _brain_enforcement_directive, lang)
                    elif not _training_engine_active_for_request:
                        _brain_enforcement_prompt_addendum = (
                            _brain_enforcement_directive["system_prompt_addendum"])

        if _health_scope.scope is HealthSafetyScope.DECLARED_HEALTH_CONTEXT:
            system_content = system_content + "\n\n" + declared_context_prompt(lang)
        if nutrition_delivery_targets is not None:
            system_content = system_content + "\n\n" + nutrition_plan.generation_contract(
                nutrition_delivery_targets, lang)
        if (_persona_expert_communication_active_for_request
                and _training_plan_blueprint is not None
                and _training_persona_expert_evaluation is not None):
            # The deterministic engine already evaluated Persona/Expert once for
            # bounded training advice. Reuse only its ID-free wording projection.
            try:
                _match, _consensus = _training_persona_expert_evaluation
                if _match is not None and _consensus is not None:
                    _persona_projection, _expert_communication_constraints = (
                        persona_expert_projection.build_training_projections(
                            persona_adaptation=_persona_adaptation(_match),
                            profile_facts={key: fact.value for key, fact in _snapshot.profile.items()},
                            locked_preferences=_snapshot.locked_preferences.as_dict(),
                            training_plan=_training_plan_blueprint,
                            exercise_library=load_exercise_library(),
                            expert_consensus=_consensus,
                        ))
                    if (_persona_projection.is_none
                            and _expert_communication_constraints.is_none):
                        _persona_projection = _expert_communication_constraints = None
            except Exception:
                _persona_projection = _expert_communication_constraints = None
        if _training_plan_blueprint is not None:
            # Preserve the established APEX coach context. The fixed training
            # contract remains last and authoritative for immutable plan values.
            system_content = system_content + "\n\n" + training_renderer.render_prompt(
                _training_plan_blueprint, lang)
        elif _recommendation_blueprint is not None:
            system_content = recommendation_renderer.render_prompt(_recommendation_blueprint)
        if _conversation_policy is not None and _controlled_reply is None:
            try:
                _conversation_frame = conversation_composer.compose(
                    _conversation_policy,
                    verified_memory=history,
                    validated_blueprint=(_training_plan_blueprint
                                         if _training_plan_blueprint is not None
                                         else _recommendation_blueprint),
                    validated_nutrition_contract=nutrition_delivery_targets is not None,
                    authority_facts=profile if isinstance(profile, dict) else {},
                    persona_projection=_persona_projection,
                    expert_communication_constraints=_expert_communication_constraints,
                    shoulder_safety_proof=(
                        _shoulder_safety_validation.proof
                        if _shoulder_safety_validation is not None else None
                    ),
                )
                system_content = system_content + "\n\n" + conversation_composer.render_prompt(
                    _conversation_frame, lang)
            except Exception as _composer_error:
                print(f"[conversation-composer] frame failed: {_composer_error}")

        if _brain_enforcement_prompt_addendum:
            system_content = system_content + "\n\n" + _brain_enforcement_prompt_addendum

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
                kind = "workout" if (_recommendation_blueprint is not None or _training_plan_blueprint is not None) else (
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

        def _persist_reply(reply_text, authoritative_plan=None):
            """Store the exchange to the account so the coach remembers it across
            devices; save any nutrition plan to nutrition_history."""
            # A SESSION_START greeting is regenerated fresh each session from live
            # state; it is not a content turn, so it is never written to history.
            if session_start or not persist_uid or not reply_text:
                return
            try:
                store.add_conversation(persist_uid, "user", persist_user_msg, persist_lang)
                store.add_conversation(persist_uid, "assistant", reply_text, persist_lang)
                if authoritative_plan is not None:
                    store.save_nutrition_plan(persist_uid, nutrition_plan.to_record(authoritative_plan))
                    athlete_store.observe(persist_uid, "nutrition_plan_issued", {})
                low = reply_text.lower() if authoritative_plan is None else ""
                if "|" in reply_text and any(k in low for k in ("ккал", "kcal", "калории", "protein", "протеин", "въглехидрати", "carb")):
                    store.save_nutrition(persist_uid, reply_text, None)
                    # M0: nutrition-plan evidence (inferred tier; stays low until real intake).
                    athlete_store.observe(persist_uid, "nutrition_plan_issued", {})
            except Exception as _pe:
                print(f"[chat] persist failed: {_pe}")
            # M0: exchange evidence — account-only (persist_uid is non-None past the guard above).
            athlete_store.observe(persist_uid, "exchange", {})

        def _shadow_log():
            """Schedule isolated shadow work after authoritative content is fixed."""
            path = _recommendation_path
            intent = getattr(_shadow_decision, "intent", "unknown")
            if brain_config.brain_shadow() or (_snapshot is not None and _shadow_decision is not None
                                               and _shadow_decision.outcome == "recommend"
                                               and (_shadow_feature_enabled("PERSONA_MATCHER_SHADOW")
                                                    or _shadow_feature_enabled("EXPERT_CONSENSUS_SHADOW"))):
                shadow_observability.emit_metric("request_eligible", component="request", status="eligible",
                                                  locale=lang, intent_category=intent)
            if brain_config.brain_shadow():
                shadow_observability.submit(
                    locale=lang, authoritative_path=path, authoritative_intent=intent,
                    components=("brain",), task_kind="brain", timeout_ms=250,
                    work=lambda: _brain_shadow_observation(
                        persist_profile, persist_user_msg, persist_conversation, model_to_use,
                        locale=lang, authoritative_path=path, authoritative_intent=intent),
                    request_id=_shadow_request_id,
                )
            if (_snapshot is not None and _shadow_decision is not None
                    and _shadow_decision.outcome == "recommend"
                    and (_shadow_feature_enabled("PERSONA_MATCHER_SHADOW")
                         or _shadow_feature_enabled("EXPERT_CONSENSUS_SHADOW"))):
                shadow_observability.submit(
                    locale=lang, authoritative_path=path, authoritative_intent=intent,
                    components=("persona", "expert"), task_kind="persona_expert", timeout_ms=250,
                    work=lambda: _persona_expert_shadow_observation(
                        _snapshot, _shadow_decision, locale=lang, authoritative_path=path,
                        recommendation_engine_active=_recommendation_active,
                        pre_evaluated=_training_persona_expert_evaluation),
                    request_id=_shadow_request_id,
                )

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
                    if _medical_hold and _medical_hold.get("status") == "ACTIVE_MEDICAL_HOLD":
                        yield sse({"medical_hold": True, "workout_suspended": True})
                    yield sse({"t": _controlled_reply})
                    speech_event = _speech_event(
                        _controlled_reply,
                        safety_response=getattr(_shadow_decision, "outcome", None) == "route",
                    )
                    if speech_event:
                        yield sse(speech_event)
                    _persist_reply(_controlled_reply)
                    _update_learning_engine(chat_uid, user_message, _controlled_reply, profile)
                    _log_analytics(_t_start)
                    _ingest_state()
                    _shadow_log()
                    yield sse({"done": True})
                    return
                if _revised_nutrition_plan is not None:
                    reply_text = nutrition_plan.render_delivery(_revised_nutrition_plan, lang, profile)
                    yield sse({"t": reply_text})
                    speech_event = _speech_event(reply_text, preserve_visible=True)
                    if speech_event:
                        yield sse(speech_event)
                    _persist_reply(reply_text, _revised_nutrition_plan)
                    _update_learning_engine(chat_uid, user_message, reply_text, profile)
                    _log_analytics(_t_start)
                    _ingest_state()
                    _shadow_log()
                    yield sse({"done": True})
                    return
                if _nutrition_revision_failure is not None:
                    reply_text = _nutrition_revision_failure
                    yield sse({"t": reply_text})
                    speech_event = _speech_event(reply_text, preserve_visible=True)
                    if speech_event:
                        yield sse(speech_event)
                    _persist_reply(reply_text)
                    _update_learning_engine(chat_uid, user_message, reply_text, profile)
                    _log_analytics(_t_start)
                    _ingest_state()
                    _shadow_log()
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
                elif brain_config.brain_enforce():
                    # Preserve the enforcement telemetry contract for turns that are
                    # deliberately classified as ordinary conversation.  This is
                    # observability only: it cannot select or construct a workout.
                    yield sse({"decision": {"verdict": "CONTINUE_CONVERSATION"}})
                nutrition_delivery_failed = False
                if _nutrition_conversation.user_response is not None:
                    # Intake was resolved before any model call. A clarification or
                    # unsupported outcome is a complete nutrition turn, never a
                    # prelude to a second generator path.
                    reply_text = _nutrition_conversation.user_response
                    yield sse({"t": reply_text})
                    speech_event = _speech_event(reply_text, preserve_visible=True)
                    if speech_event:
                        yield sse(speech_event)
                    _persist_reply(reply_text)
                    _update_learning_engine(chat_uid, user_message, reply_text, profile)
                    _log_analytics(_t_start)
                    _ingest_state()
                    _shadow_log()
                    yield sse({"done": True})
                    return
                if _nutrition_conversation.state is nutrition_conversation.NutritionConversationState.PLAN_READY:
                    # Plan-ready nutrition is generated as structured JSON. The
                    # visible table is rendered only after canonical validation.
                    authoritative_plan = None
                    if _nutrition_v2_active_for_request:
                        _bump_plans_today()
                        authoritative_plan = _nutrition_v2_authoritative_plan
                        if authoritative_plan is None:
                            failed_nutrition_turn = nutrition_conversation.fail_generation(
                                _nutrition_conversation, lang, "nutrition_v2_delivery_rejected")
                            reply_text = (failed_nutrition_turn.user_response
                                          or nutrition_conversation.failed_message(lang))
                            nutrition_delivery_failed = True
                        else:
                            reply_text = nutrition_plan.render_delivery(authoritative_plan, lang, profile)
                        yield sse({"t": reply_text})
                        speech_event = _speech_event(reply_text, preserve_visible=nutrition_delivery_failed)
                        if speech_event:
                            yield sse(speech_event)
                        _persist_reply(reply_text, authoritative_plan)
                        _update_learning_engine(chat_uid, user_message, reply_text, profile)
                        _log_analytics(_t_start)
                        _ingest_state()
                        _shadow_log()
                        yield sse({"done": True})
                        return
                    try:
                        completion = client.chat.completions.create(
                            model=model_to_use,
                            messages=messages,
                            max_tokens=max_tokens,
                            response_format={"type": "json_object"},
                        )
                        _bump_plans_today()
                        generated = nutrition_plan.parse_generation_response(completion)
                        authoritative_plan = nutrition_plan.build_plan(
                            generated, nutrition_delivery_targets,
                            restrictions=_nutrition_restrictions(profile),
                            provenance={"generator": "openai_chat_completions_json", "model": model_to_use},
                            language=lang,
                        )
                        reply_text = nutrition_plan.render_delivery(authoritative_plan, lang, profile)
                    except nutrition_plan.NutritionPlanError as validation_error:
                        # One repair attempt is allowed for a rejected structured
                        # response. It receives only the deterministic failure,
                        # never the rejected plan, and does not consume quota or
                        # the plan counter a second time.
                        try:
                            repair_messages = messages + [{
                                "role": "system",
                                "content": nutrition_plan.regeneration_contract(
                                    validation_error, nutrition_delivery_targets, lang),
                            }]
                            repair_model = "gpt-4o" if model_to_use == "gpt-4o-mini" else model_to_use
                            completion = client.chat.completions.create(
                                model=repair_model,
                                messages=repair_messages,
                                max_tokens=max_tokens,
                                response_format={"type": "json_object"},
                            )
                            generated = nutrition_plan.parse_generation_response(completion)
                            authoritative_plan = nutrition_plan.build_plan(
                                generated, nutrition_delivery_targets,
                                restrictions=_nutrition_restrictions(profile),
                                provenance={"generator": "openai_chat_completions_json_repair", "model": repair_model},
                                language=lang,
                            )
                            reply_text = nutrition_plan.render_delivery(authoritative_plan, lang, profile)
                        except Exception as repair_error:
                            print(f"[chat] nutrition repair failed: {type(repair_error).__name__} reason={repair_error}")
                            authoritative_plan = nutrition_plan.build_source_backed_plan(
                                nutrition_delivery_targets,
                                lang,
                                restrictions=_nutrition_restrictions(profile),
                            )
                            if authoritative_plan is not None:
                                reply_text = nutrition_plan.render_delivery(authoritative_plan, lang, profile)
                            else:
                                failed_nutrition_turn = nutrition_conversation.fail_generation(
                                    _nutrition_conversation, lang, "structured_plan_validation_failed")
                                reply_text = failed_nutrition_turn.user_response or nutrition_conversation.failed_message(lang)
                                nutrition_delivery_failed = True
                    except Exception as nutrition_error:
                        print(f"[chat] nutrition orchestration failed: {type(nutrition_error).__name__} reason={nutrition_error}")
                        authoritative_plan = nutrition_plan.build_source_backed_plan(
                            nutrition_delivery_targets,
                            lang,
                            restrictions=_nutrition_restrictions(profile),
                        )
                        if authoritative_plan is not None:
                            reply_text = nutrition_plan.render_delivery(authoritative_plan, lang, profile)
                        else:
                            failed_nutrition_turn = nutrition_conversation.fail_generation(
                                _nutrition_conversation, lang, "structured_plan_validation_failed")
                            reply_text = failed_nutrition_turn.user_response or nutrition_conversation.failed_message(lang)
                            nutrition_delivery_failed = True
                    yield sse({"t": reply_text})
                    speech_event = _speech_event(reply_text, preserve_visible=nutrition_delivery_failed)
                    if speech_event:
                        yield sse(speech_event)
                    _persist_reply(reply_text, authoritative_plan)
                    _update_learning_engine(chat_uid, user_message, reply_text, profile)
                    _log_analytics(_t_start)
                    _ingest_state()
                    _shadow_log()
                    yield sse({"done": True})
                    return
                if _training_plan_blueprint is not None:
                    # Training delivery accepts only the renderer's explanation
                    # object. Explanation delivery is never allowed to suppress
                    # an already validated deterministic training plan.
                    training_completion = None
                    try:
                        try:
                            completion = client.chat.completions.create(
                                model=model_to_use,
                                messages=messages,
                                max_tokens=max_tokens,
                                response_format={"type": "json_object"},
                            )
                            _bump_plans_today()
                            raw_explanations = completion.choices[0].message.content or ""
                            explanations = training_renderer.verified_explanations(raw_explanations)
                        except Exception as explanation_error:
                            print(f"[training-engine] explanation fallback: {type(explanation_error).__name__}")
                            explanations = ()
                        if not explanations:
                            explanations = training_renderer.default_explanations(
                                _training_plan_blueprint, lang)
                        reply_text = training_renderer.render_delivery(
                            _training_plan_blueprint, load_exercise_library(), explanations, lang)
                        if _combined_coaching_request:
                            reply_text += _combined_request_follow_up(lang)
                        training_completion = training_renderer.render_completion_projection(
                            _training_plan_blueprint, load_exercise_library(), lang)
                    except Exception as training_error:
                        print(f"[training-engine] delivery rejected: {type(training_error).__name__}")
                        reply_text = decision_engine.controlled_response(
                            decision_engine.DecisionResult("clarify", "workout",
                                                           "training_engine_delivery_contract", (), 1.0), lang)
                    yield sse({"t": reply_text})
                    if training_completion is not None:
                        _remember_workout(_workout_scope, _training_plan_blueprint)
                        yield sse({"training_completion": training_completion})
                    speech_event = _speech_event(reply_text)
                    if speech_event:
                        yield sse(speech_event)
                    _persist_reply(reply_text)
                    _update_learning_engine(chat_uid, user_message, reply_text, profile)
                    _log_analytics(_t_start)
                    _ingest_state()
                    _shadow_log()
                    yield sse({"done": True})
                    return

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
                        if (not nutrition_response_guard and nutrition_delivery_target is None and
                                _recommendation_blueprint is None and _training_plan_blueprint is None):
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
                elif nutrition_response_guard:
                    # Guidance is presentation only. New authoritative plans use
                    # the structured plan-ready branch above; never inspect text
                    # to reconstruct a plan.
                    yield sse({"t": reply_text})
                speech_event = _speech_event(
                    reply_text,
                    preserve_visible=nutrition_delivery_failed,
                )
                if speech_event:
                    yield sse(speech_event)
                _persist_reply(reply_text)
                _update_learning_engine(chat_uid, user_message, reply_text, profile)
                _log_analytics(_t_start)   # M5 Observatory
                _ingest_state()      # BUILD-001 Human State (HSE_INGEST off by default)
                _shadow_log()
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
                    _log_analytics(_t_start)
                    _ingest_state()
                    _shadow_log()
                    yield sse({"done": True})
                    return
                # An upstream interruption is never a completed coaching turn.
                # Tokens may already be visible in the browser, but they remain
                # provisional: do not persist, learn from, count, or finalize them.
                if refund_subject:
                    try: store.free_usage_refund(refund_subject[0], refund_subject[1])
                    except Exception: pass
                yield sse({
                    "error": True,
                    "not_counted": True,
                    "reply": ("The response was interrupted. Please try again."
                              if lang == "en" else
                              "Отговорът беше прекъснат. Моля, опитай отново.")
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
_SELECTOR_TTS_VOICES = frozenset(("ash", "alloy"))

@app.route("/speak", methods=["POST"])
def speak():
    data = request.get_json(silent=True) or {}
    text = str(data.get("text", "")).strip()[:1600]
    lang = "en" if str(data.get("lang", "bg")).lower() == "en" else "bg"
    selected_voice = data.get("voice")
    if not text:
        return jsonify({"error": "empty"}), 400
    if (selected_voice is not None and
            (not isinstance(selected_voice, str) or selected_voice not in _SELECTOR_TTS_VOICES)):
        return jsonify({"error": "invalid_voice"}), 400
    # Cost guard: cap synthesis calls per subject (account or httpOnly device / IP).
    subj = str(g.user["id"]) if g.get("user") else (g.device_id or _client_ip())
    now = time.time()
    stamps = [t for t in _speak_rate.get(subj, []) if now - t < 300]
    if len(stamps) >= 60:
        return jsonify({"error": "rate_limited"}), 429
    stamps.append(now); _speak_rate[subj] = stamps
    try:
        audio, mime = apex_voice.synthesize(
            text, lang=lang, client=client, voice=selected_voice)
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
    if not _paid_access_enabled():
        return jsonify({'error': 'paid_access_unavailable'}), 503
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
