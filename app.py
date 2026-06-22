from flask import Flask, request, jsonify, render_template, redirect, Response, stream_with_context, make_response
from flask_cors import CORS
from openai import OpenAI
import stripe
import os
import hmac
import hashlib
import time
import base64
import threading

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
# SERVER-SIDE FREE LIMIT (per IP, in-memory)
# localStorage alone is trivially bypassed (incognito = reset).
# This is a second wall. Resets on Railway redeploy — acceptable.
# Users who leave their email get +LEAD_BONUS extra messages.
# ═══════════════════════════════════════════════════════════
FREE_DAILY_LIMIT = 10
LEAD_BONUS = 5
FREE_WINDOW_SECONDS = 24 * 60 * 60
_free_usage = {}      # ip -> {"count": int, "start": ts, "bonus": bool}
_pending_tokens = {}  # stripe session_id -> (signed_token, issued_at) pairs

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

def _get_free_usage(ip):
    now = time.time()
    u = _free_usage.get(ip)
    if not u or now - u["start"] >= FREE_WINDOW_SECONDS:
        u = {"count": 0, "start": now, "bonus": False}
        _free_usage[ip] = u
    # prevent unbounded memory growth
    if len(_free_usage) > 5000:
        cutoff = now - FREE_WINDOW_SECONDS
        for k in list(_free_usage.keys()):
            if _free_usage[k]["start"] < cutoff:
                del _free_usage[k]
    return u


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
- Препращай към профила в текста: "При теб, с 80 кг и начинаещо ниво..." — не говори в трето лице

═══════════════════════════════════════════════════════════
ОБЯСНЯВАЙ ЗАЩО — ЗА ВСЯКА ПРЕПОРЪКА
═══════════════════════════════════════════════════════════

НИКОГА не давай препоръка без конкретно обяснение защо е точно за ТОЗИ човек:
- Храна: "Овесени ядки сутринта — бавни въглехидрати, задържат глада при дефицит като твоя (500 ккал под поддържащото)"
- Упражнение: "Клекът е основен за теб — при начинаещо ниво изгражда долната верига едновременно, не само бедрата"
- Количество: "180 г пилешко — при теб (75 кг, цел маса) = ~45 г протеин само от основното ястие, целта е ~150 г/ден"
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
- ХВАЛИ САМО с числа: "80 кг и 3 тренировки — реалистично за 4 кг маса за 12 седмици."
- МОТИВИРАЙ с факти: "При дефицит 400 ккал/ден → ~1.5 кг мастна тъкан на месец. При теб — 6 кг за 4 месеца."
- НЕ казвай: "Чудесна цел!", "Страхотно!", "Браво!", "Разбира се!", "Отлично!", "Супер въпрос!"
- КАЗВАЙ: "Реалистично.", "Може.", "Работи.", "Това е грешка — ето защо:", "Добре — ето как:"

═══════════════════════════════════════════════════════════
ПЪРВИ ОТГОВОР — ПРИЗНАНИЕ НА ЦЕЛТА
═══════════════════════════════════════════════════════════

САМО при ПЪРВИЯ отговор (историята НЕ съдържа предишни AI отговори):
- 1-2 изречения, признай целта СПРЯМО ПРОФИЛА: "При 85 кг и цел отслабване — дефицит 450-500 ккал/ден е правилната посока."
- ПОСЛЕ — планът директно
При СЛЕДВАЩИ отговори: НЕ повтаряй признанието. Говори директно.

EN first response: "At 85 kg targeting fat loss — 450-500 kcal daily deficit is the right approach." Then the plan.

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
ЕЗИК
═══════════════════════════════════════════════════════════

ВИНАГИ отговаряй на езика на потребителя. БГ → 100% Български. EN → 100% English.
Дори финалното предупреждение е на същия език.
"""


def _build_profile_block(profile: dict) -> str:
    """Serialize the user profile dict into a system-prompt context block."""
    if not profile or not isinstance(profile, dict):
        return ""
    gender_map = {'m': 'Мъж', 'f': 'Жена', 'male': 'Мъж', 'female': 'Жена'}
    level_map = {
        'beginner': 'Начинаещ', 'intermediate': 'Среден', 'advanced': 'Напреднал',
        'начинаещ': 'Начинаещ', 'среден': 'Среден', 'напреднал': 'Напреднал',
    }
    equip_map = {
        'gym': 'Пълна зала', 'home': 'Вкъщи (дъмбели/турник)', 'none': 'Без оборудване',
        'зала': 'Пълна зала', 'вкъщи': 'Вкъщи (дъмбели/турник)', 'без': 'Без оборудване',
    }
    lines = []
    gender = gender_map.get(str(profile.get('gender', '')).lower(), profile.get('gender', ''))
    if gender:        lines.append(f"  Пол: {gender}")
    if profile.get('age'):    lines.append(f"  Възраст: {profile['age']} г.")
    if profile.get('weight'): lines.append(f"  Тегло: {profile['weight']} кг")
    if profile.get('height'): lines.append(f"  Височина: {profile['height']} см")
    level = level_map.get(str(profile.get('level', '')).lower(), profile.get('level', ''))
    if level:         lines.append(f"  Ниво: {level}")
    equip = equip_map.get(str(profile.get('equipment', '')).lower(), profile.get('equipment', ''))
    if equip:         lines.append(f"  Оборудване: {equip}")
    if profile.get('injuries') and str(profile['injuries']).strip():
        lines.append(f"  Наранявания/Ограничения: {profile['injuries']}")
    if profile.get('goal') and str(profile['goal']).strip():
        lines.append(f"  Заявена цел: {profile['goal']}")
    if not lines:
        return ""
    block = "═══ ПРОФИЛ НА КЛИЕНТА ═══\n" + "\n".join(lines) + "\n═══════════════════════"
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
# In-memory; resets on Railway redeploy. The withdrawal request email to
# coach@apexpulse.pro IS the durable audit trail.
_revoked_tokens = set()


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
    response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
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
    """The AI chat interface — minimal, focused on AI conversation."""
    return render_template("app.html")


@app.route("/chat", methods=["POST"])
def chat():
    try:
        data = request.json or {}
        token = data.get("token", "")
        # NOTE: plan is now derived from the SIGNED token, never from the frontend.

        is_elite, token_plan = verify_token(token) if token else (False, None)
        is_dev = bool(DEV_TOKEN) and token == DEV_TOKEN
        is_pro = is_elite and token_plan == "pro"

        msg_limit = 4000 if is_elite else 1000
        user_message = str(data.get("message", ""))[:msg_limit]
        history = data.get("history", [])
        profile = data.get("profile") or {}

        # ── SERVER-SIDE FREE LIMIT ──
        # localStorage limit is the soft wall; this is the real one.
        if not is_elite:
            ip = _client_ip()
            usage = _get_free_usage(ip)
            limit = FREE_DAILY_LIMIT + (LEAD_BONUS if usage.get("bonus") else 0)
            if usage["count"] >= limit:
                hours_left = max(1, int((FREE_WINDOW_SECONDS - (time.time() - usage["start"])) // 3600) + 1)
                return jsonify({"limit_reached": True, "hours_left": hours_left}), 200
            usage["count"] += 1

        profile_block = _build_profile_block(profile) if isinstance(profile, dict) else ""
        system_content = (profile_block + "\n\n" + SYSTEM_INSTRUCTIONS) if profile_block else SYSTEM_INSTRUCTIONS
        messages = [{"role": "system", "content": system_content}]

        # Memory cap based on plan (from signed token):
        # - PRO → 60 messages, CORE → 10, FREE → 12 (plan + follow-up questions fit)
        if is_elite:
            memory_cap = 60 if is_pro else 10
        else:
            memory_cap = 12

        if isinstance(history, list):
            safe_history = history[-memory_cap:]
            for msg in safe_history:
                if isinstance(msg, dict) and msg.get("role") in ("user", "assistant"):
                    content = str(msg.get("content", ""))[:4000]
                    messages.append({"role": msg["role"], "content": content})

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
        ip_for_refund = _client_ip() if not is_elite else None

        def sse(obj):
            return "data: " + _json.dumps(obj, ensure_ascii=False) + "\n\n"

        def generate():
            full = []
            try:
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
                        yield sse({"t": delta})
                _bump_plans_today()  # honest landing counter: +1 real AI plan
                yield sse({"done": True})
            except Exception as openai_error:
                print(f"[chat] OpenAI error: {openai_error}")
                if full:
                    # Потребителят вече получи почти всичко — завършваме чисто
                    _bump_plans_today()
                    yield sse({"done": True})
                else:
                    # Нищо не е стигнало → връщаме съобщението в лимита му
                    if ip_for_refund:
                        u = _free_usage.get(ip_for_refund)
                        if u and u["count"] > 0:
                            u["count"] -= 1
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
            _pending_tokens[session.id] = (token, time.time())
            print(f'[webhook] Token issued for session {session.id[:20]}... plan={paid_plan}')
    return jsonify({'ok': True})


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
    stale = [k for k, (_, ts) in _pending_tokens.items() if now - ts > _PENDING_TOKEN_TTL]
    for k in stale:
        del _pending_tokens[k]

    # Primary path: webhook already stored the token
    entry = _pending_tokens.pop(session_id, None)
    if entry:
        token, _ = entry
        return jsonify({'ready': True, 'token': token})

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
            print(f'[poll-token] Fallback token issued for session {session_id[:20]}...')
            return jsonify({'ready': True, 'token': token})
    except Exception as e:
        print(f'[poll-token] Stripe error: {e}')
    return jsonify({'ready': False})


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


@app.route('/owner-mode')
def owner_mode():
    """Sets a long-lived cookie that suppresses GA4 tracking on this device.
    Visit /owner-mode to activate, /owner-mode?off=1 to deactivate."""
    turning_off = request.args.get('off') == '1'
    next_url = request.args.get('next', '/')
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
    return jsonify({'valid': is_valid, 'isDev': is_dev, 'plan': plan or 'free'})


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

    # ─────────── WITHIN 7-DAY WINDOW → revoke + refund ───────────
    if hours_since <= WITHDRAW_WINDOW_HOURS:
        # Revoke immediately so the token stops working even if cached client-side.
        _revoked_tokens.add(token)

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
        # Grant the bonus messages to this IP's free window
        usage = _get_free_usage(ip)
        usage["bonus"] = True

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


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
