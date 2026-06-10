from flask import Flask, request, jsonify, render_template, redirect
from flask_cors import CORS
from openai import OpenAI
import stripe
import os
import hmac
import hashlib
import time
import base64

app = Flask(__name__, static_folder='static', template_folder='templates')
CORS(app)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

# ═══════════════════════════════════════════════════════════
# SECURITY CONFIGURATION
# Both must be set in Railway → Variables
# APEX_SECRET = signs tokens for paying Stripe customers (30 days)
# APEX_DEV_TOKEN = your personal lifetime access token
# ═══════════════════════════════════════════════════════════
SECRET = os.getenv("APEX_SECRET", "change-this-in-railway-to-a-long-random-string")
DEV_TOKEN = os.getenv("APEX_DEV_TOKEN", "")

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
_free_usage = {}   # ip -> {"count": int, "start": ts, "bonus": bool}

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
    return request.headers.get('X-Forwarded-For', request.remote_addr or 'unknown').split(',')[0].strip()

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
Ти си APEX PULSE PRO — авторитетен AI фитнес и хранителен асистент. 
Твоята мисия: даваш на потребителя конкретни, полезни планове за тренировки и хранене.

═══════════════════════════════════════════════════════════
ОСНОВНО ПОВЕДЕНИЕ — ВИНАГИ ПОМАГАШ
═══════════════════════════════════════════════════════════

Когато потребителят пита за:
- Тренировъчна програма → ДАВАШ конкретна програма с упражнения, серии, повторения
- Хранителен режим → ДАВАШ конкретно меню с макроси и калории в таблица
- Отслабване / маса / сила → ДАВАШ план с конкретни числа и стъпки
- Калории, протеин, макроси → ИЗЧИСЛЯВАШ въз основа на данните които ти дава
- Упражнения за конкретна мускулна група → ИЗБРОЯВАШ упражнения с указания

НЕ казваш "консултирай се с лекар" при нормални въпроси за фитнес и хранене.
Това е за фитнес-ентусиасти и здрави хора — давай им планове.
В края на отговора има автоматично предупреждение — не повтаряй такива съвети в средата.

═══════════════════════════════════════════════════════════
ИЗКЛЮЧЕНИЯ — САМО ТОГАВА ПРЕНАСОЧВАШ КЪМ ЛЕКАР
═══════════════════════════════════════════════════════════

Пренасочваш към лекар САМО ако потребителят САМ изрично спомене:
- Конкретно медицинско състояние: "имам диабет", "имам сърдечно", "бременна съм"
- Прием на лекарства: "пия лекарства за..."
- Симптоми: "имам болка в...", "вие ми се свят при тренировка"
- Възраст под 18 години
- Хранително разстройство (анорексия, булимия)

Само в тези случаи кажи кратко:
BG: "Преди да започнеш програма, консултирай се с лекар за твоя случай."
EN: "Before starting, please consult a doctor for your specific case."

ВАЖНО: 
- Височина и тегло НЕ са медицински проблеми. "Висок съм 185, тежа 84 кг" е нормална информация — давай план.
- Възраст 18-65 е нормална — давай план.
- "Здрав съм без хронични" → давай план без коментари.

═══════════════════════════════════════════════════════════
КАКВО НЕ ПРАВИШ
═══════════════════════════════════════════════════════════

ОТКАЗВАШ САМО ако потребителят иска:
- Стероиди, SARMS, забранени вещества → откажи
- Екстремни диети под 1000 ккал → предложи безопасна алтернатива
- Лекарства за отслабване → откажи

═══════════════════════════════════════════════════════════
ФОРМАТ НА ОТГОВОРИТЕ
═══════════════════════════════════════════════════════════

- Използвай Markdown таблици за хранителни режими (Хранене / Ястие / Протеин / Ккал)
- За тренировки: таблици (Упражнение / Серии / Повторения)
- Максимум 4 колони (за мобилни устройства)
- Тонът: авторитетен, мотивиращ, конкретен — като елитен треньор
- Кратки параграфи, ясни числа

ВИНАГИ завършвай отговора със:
🔱 **ELITE STATUS: ACTIVE**

⚠️ *Този план е с информативна цел. Слушай тялото си. При болка или дискомфорт — спри.*

(Това е ЕДИНСТВЕНОТО медицинско напомняне. Не повтаряй такива неща в средата на отговора.)

═══════════════════════════════════════════════════════════
ЕЗИК
═══════════════════════════════════════════════════════════

ВИНАГИ отговаряй на езика на който пише потребителят.
- БГ потребител → 100% Български. Перфектен. Правилни термини: клек, напади, лег, гребане, преси, набирания, лицеви опори.
- EN потребител → 100% English. Professional, motivational, premium tone.

CRITICAL: ALWAYS respond in the EXACT same language as the user. Even the final medical disclaimer must match.
"""


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
                headers={"Authorization": f"Bearer {resend_key}", "Content-Type": "application/json"},
                method="POST",
            )
            with _urlreq.urlopen(req, timeout=10) as resp:
                if 200 <= resp.status < 300:
                    return True
                print(f"[email] Resend HTTP {resp.status}: {resp.read()[:200]}")
        except Exception as e:
            print(f"[email] Resend error: {e}")
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


def make_token(expiry_timestamp: int, plan: str = "core") -> str:
    """Create a signed access token that ALSO encodes the paid plan.
    Format v2: base64(expiry.plan.signature) — signature covers expiry+plan,
    so the frontend can no longer claim PRO after paying for CORE."""
    if plan not in PLANS:
        plan = "core"
    payload = f"{expiry_timestamp}.{plan}"
    signature = hmac.new(SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()[:16]
    token = base64.urlsafe_b64encode(f"{payload}.{signature}".encode()).decode().rstrip("=")
    return token


def verify_token(token: str):
    """Verify a token. Returns (is_valid, plan).
    - DEV_TOKEN → (True, 'pro')
    - v2 tokens (expiry.plan.sig) → plan comes from the signed payload
    - v1 legacy tokens (expiry.sig) → treated as 'core' (existing customers keep access)
    """
    if DEV_TOKEN and token == DEV_TOKEN:
        return True, "pro"
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
        expected = hmac.new(SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()[:16]
        if hmac.compare_digest(signature, expected):
            return True, (plan if plan in PLANS else "core")
        return False, None
    except Exception:
        return False, None


# ═══════════════════════════════════════════════════════════
# ROUTES
# / → Landing page (premium marketing + quick goals + pricing)
# /app → Chat interface (minimal, ChatGPT-style)
# ═══════════════════════════════════════════════════════════

@app.route("/")
def landing():
    """Premium landing page — first impression for new visitors."""
    return render_template("landing.html")


@app.route("/app")
def app_chat():
    """The AI chat interface — minimal, focused on AI conversation."""
    return render_template("app.html")


@app.route("/chat", methods=["POST"])
def chat():
    try:
        data = request.json or {}
        user_message = data.get("message", "")
        history = data.get("history", [])
        token = data.get("token", "")
        # NOTE: plan is now derived from the SIGNED token, never from the frontend.

        is_elite, token_plan = verify_token(token) if token else (False, None)
        is_dev = bool(DEV_TOKEN) and token == DEV_TOKEN
        is_pro = is_elite and token_plan == "pro"

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

        messages = [{"role": "system", "content": SYSTEM_INSTRUCTIONS}]

        # Memory cap based on plan (from signed token):
        # - PRO → 60 messages, CORE → 10, FREE → 6 (taste of memory)
        if is_elite:
            memory_cap = 60 if is_pro else 10
        else:
            memory_cap = 6

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

        try:
            response = client.chat.completions.create(
                model=model_to_use,
                messages=messages,
                max_tokens=max_tokens
            )
            _bump_plans_today()  # honest landing counter: +1 real AI plan/response
            return jsonify({"reply": response.choices[0].message.content})
        except Exception as openai_error:
            # Log real error for ourselves
            print(f"[chat] OpenAI error: {openai_error}")
            # The user got NOTHING — refund this message to their free limit
            if not is_elite:
                u = _free_usage.get(_client_ip())
                if u and u["count"] > 0:
                    u["count"] -= 1
            # Return friendly message to user
            return jsonify({
                "reply": "AI треньорът е претоварен в момента. Моля, опитай отново след 30 секунди.",
                "not_counted": True
            }), 200
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
        host_url = "https://" + request.host
        
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
        return jsonify(error=str(e)), 403


@app.route('/app/success')
def payment_success():
    """After Stripe payment, verify with Stripe API, then issue a signed token."""
    session_id = request.args.get('session_id')
    if not session_id:
        return redirect('/app?success=false')
    try:
        session = stripe.checkout.Session.retrieve(session_id)
        if session.payment_status == 'paid':
            paid_plan = (session.metadata or {}).get('plan', 'core')
            expiry = int(time.time()) + (30 * 24 * 60 * 60)
            token = make_token(expiry, paid_plan)
            return redirect(f'/app?token={token}')
        else:
            return redirect('/app?success=false')
    except Exception:
        return redirect('/app?success=false')


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


@app.route('/verify-token', methods=['POST'])
def verify_token_endpoint():
    """Frontend asks: is this stored token still valid, and which plan does it carry?"""
    token = request.json.get('token', '')
    is_valid, plan = verify_token(token)
    is_dev = bool(DEV_TOKEN) and token == DEV_TOKEN
    return jsonify({'valid': is_valid, 'isDev': is_dev, 'plan': plan or 'free'})


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
        email = str(data.get('email', '')).strip()[:120]
        lang = str(data.get('lang', 'bg'))[:5]
        plan_text = str(data.get('plan_text', ''))[:6000]
        if '@' not in email or '.' not in email.split('@')[-1] or len(email) < 6:
            return jsonify({'ok': False, 'error': 'invalid_email'}), 400

        _lead_recent[ip] = now
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
        # Basic rate limiting by IP
        ip = request.headers.get('X-Forwarded-For', request.remote_addr or 'unknown').split(',')[0].strip()
        now = time.time()
        last = _feedback_recent.get(ip, 0)
        if now - last < 300:  # 5 minutes
            return jsonify({'ok': False, 'error': 'rate_limit'}), 429
        
        data = request.json or {}
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
