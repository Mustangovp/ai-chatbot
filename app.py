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


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/chat", methods=["POST"])
def chat():
    try:
        data = request.json or {}
        user_message = data.get("message", "")
        history = data.get("history", [])  # Optional: list of {role, content} from ELITE users
        token = data.get("token", "")

        # Verify if ELITE token is valid — only ELITE users may send history
        is_elite = bool(token) and verify_token(token)

        # Build message list
        messages = [{"role": "system", "content": SYSTEM_INSTRUCTIONS}]

        if is_elite and isinstance(history, list):
            # Keep only last 10 messages from history (safety cap)
            safe_history = history[-10:]
            for msg in safe_history:
                if isinstance(msg, dict) and msg.get("role") in ("user", "assistant"):
                    content = str(msg.get("content", ""))[:4000]  # cap each message
                    messages.append({"role": msg["role"], "content": content})

        messages.append({"role": "user", "content": user_message})

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages
        )
        return jsonify({"reply": response.choices[0].message.content})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/create-checkout-session', methods=['POST'])
def create_checkout_session():
    try:
        host_url = "https://" + request.host
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'eur',
                    'product_data': {'name': 'APEX PULSE ELITE PRO - 30 Дни'},
                    'unit_amount': 199,
                },
                'quantity': 1,
            }],
            mode='payment',
            allow_promotion_codes=True,  # 👈 ТОВА Е НОВИЯТ РЕД, КОЙТО СЛАГАШ ТУК!
            success_url=host_url + '/success?session_id={CHECKOUT_SESSION_ID}',
            cancel_url=host_url + '/?success=false',
        )
        return jsonify({'url': session.url})
    except Exception as e:
        return jsonify(error=str(e)), 403


@app.route('/success')
def payment_success():
    """After Stripe payment, verify with Stripe API, then issue a signed token."""
    session_id = request.args.get('session_id')
    if not session_id:
        return redirect('/?success=false')
    try:
        session = stripe.checkout.Session.retrieve(session_id)
        if session.payment_status == 'paid':
            expiry = int(time.time()) + (30 * 24 * 60 * 60)
            token = make_token(expiry)
            return redirect(f'/?token={token}')
        else:
            return redirect('/?success=false')
    except Exception:
        return redirect('/?success=false')


@app.route('/verify-token', methods=['POST'])
def verify_token_endpoint():
    """Frontend asks: is this stored token still valid?"""
    token = request.json.get('token', '')
    return jsonify({'valid': verify_token(token)})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
