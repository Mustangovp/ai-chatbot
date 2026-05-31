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
# - founding: €1.99 (active until May 31, 2026)
# - core: €9.99 (from June 1, 2026)
# - pro: €14.99 (from June 1, 2026)
# ═══════════════════════════════════════════════════════════
PLANS = {
    "founding": {"name": "APEX PULSE ELITE PRO - 30 Дни", "amount": 199, "memory": 10},
    "core":     {"name": "APEX PULSE CORE - 30 Days",     "amount": 999, "memory": 10},
    "pro":      {"name": "APEX PULSE PRO - 30 Days",      "amount": 1499, "memory": 30},
}


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


def make_token(expiry_timestamp: int) -> str:
    """Create a signed access token (30 days for paying customers)."""
    payload = str(expiry_timestamp).encode()
    signature = hmac.new(SECRET.encode(), payload, hashlib.sha256).hexdigest()[:16]
    token = base64.urlsafe_b64encode(f"{expiry_timestamp}.{signature}".encode()).decode().rstrip("=")
    return token


def verify_token(token: str) -> bool:
    """Verify a token. Accepts DEV_TOKEN (unlimited) or signed Stripe token (30 days)."""
    if DEV_TOKEN and token == DEV_TOKEN:
        return True
    try:
        padded = token + "=" * (-len(token) % 4)
        decoded = base64.urlsafe_b64decode(padded).decode()
        expiry_str, signature = decoded.split(".")
        expiry = int(expiry_str)
        if time.time() > expiry:
            return False
        expected = hmac.new(SECRET.encode(), expiry_str.encode(), hashlib.sha256).hexdigest()[:16]
        return hmac.compare_digest(signature, expected)
    except Exception:
        return False


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
        plan_hint = data.get("plan", "")  # 'core' or 'pro' — frontend may send this

        is_elite = bool(token) and verify_token(token)
        messages = [{"role": "system", "content": SYSTEM_INSTRUCTIONS}]

        # Memory cap based on plan:
        # - PRO plan → 30 messages
        # - CORE / founding / dev_token → 10 messages
        # - FREE (no token) → 6 messages (taste of memory feature)
        if is_elite:
            memory_cap = 30 if plan_hint == "pro" else 10
        else:
            memory_cap = 6

        if isinstance(history, list):
            safe_history = history[-memory_cap:]
            for msg in safe_history:
                if isinstance(msg, dict) and msg.get("role") in ("user", "assistant"):
                    content = str(msg.get("content", ""))[:4000]
                    messages.append({"role": msg["role"], "content": content})

        messages.append({"role": "user", "content": user_message})

        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages
            )
            return jsonify({"reply": response.choices[0].message.content})
        except Exception as openai_error:
            # Log real error for ourselves
            print(f"[chat] OpenAI error: {openai_error}")
            # Return friendly message to user
            return jsonify({
                "reply": "AI треньорът е претоварен в момента. Моля, опитай отново след 30 секунди."
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
        plan_key = data.get('plan', 'founding')
        if plan_key not in PLANS:
            plan_key = 'founding'
        
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
            expiry = int(time.time()) + (30 * 24 * 60 * 60)
            token = make_token(expiry)
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


@app.route('/verify-token', methods=['POST'])
def verify_token_endpoint():
    """Frontend asks: is this stored token still valid?"""
    token = request.json.get('token', '')
    return jsonify({'valid': verify_token(token)})


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
        
        # Try sending via Gmail SMTP; fall back to logging if not configured
        gmail_user = os.getenv('GMAIL_USER', '')
        gmail_pass = os.getenv('GMAIL_APP_PASSWORD', '')
        
        if gmail_user and gmail_pass:
            try:
                import smtplib
                from email.mime.text import MIMEText
                from email.mime.multipart import MIMEMultipart
                
                msg = MIMEMultipart()
                msg['From'] = gmail_user
                msg['To'] = gmail_user  # send to self
                if email:
                    msg['Reply-To'] = email
                msg['Subject'] = f'[Apex Feedback] {type_label}'
                msg.attach(MIMEText(email_body, 'plain', 'utf-8'))
                
                with smtplib.SMTP_SSL('smtp.gmail.com', 465, timeout=10) as smtp:
                    smtp.login(gmail_user, gmail_pass)
                    smtp.send_message(msg)
                
                print(f'[feedback] Email sent for type={fb_type}')
            except Exception as e:
                # Don't fail the request — feedback is logged in Railway logs
                print(f'[feedback] SMTP error: {e}')
                print(f'[feedback] FALLBACK LOG:\n{email_body}')
        else:
            # Gmail not configured — log to Railway logs
            print('[feedback] Gmail not configured. FALLBACK LOG:')
            print(email_body)
        
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
