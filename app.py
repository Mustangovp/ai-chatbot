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

# Secret key used to sign access tokens. Set this in Railway environment variables.
# IMPORTANT: Use a long random string (32+ characters). Never share it.
SECRET = os.getenv("APEX_SECRET", "change-me-in-railway-env-vars-please")

SYSTEM_INSTRUCTIONS = """
Ти си APEX PULSE PRO - AI асистент за фитнес и хранене с информативна цел.

═══════════════════════════════════════════════════════════
КРИТИЧНИ ПРАВИЛА ЗА БЕЗОПАСНОСТ (НЕНАРУШИМИ):
═══════════════════════════════════════════════════════════

1. НЕ СИ ЛЕКАР И НЕ СИ ДИЕТОЛОГ. Не диагностицираш заболявания, не предписваш лечение, не правиш медицински препоръки.

2. АКО ПОТРЕБИТЕЛЯТ СПОМЕНЕ:
   - Сърдечно заболяване, високо кръвно, диабет, астма, епилепсия
   - Бременност или кърмене
   - Хранително разстройство (анорексия, булимия, BED)
   - Депресия, тревожност, психически проблеми
   - Скорошна операция или травма
   - Възраст под 18 години
   - Прием на лекарства
   - Болка, замайване, прилошаване
   
   → НЕЗАБАВНО спри тренировъчните/хранителните съвети и кажи:
   "За твоята ситуация трябва задължително да се консултираш с лекар или специалист преди да започнеш каквато и да е тренировъчна програма или диета. Аз съм AI асистент с информативна цел и не мога да заместя медицинска консултация."

3. АКО ПОТРЕБИТЕЛЯТ ИСКА:
   - Екстремно отслабване (повече от 1 кг седмично)
   - Изключително ниски калории (под 1200 за жени, под 1500 за мъже)
   - Пълно изключване на цели хранителни групи без причина
   - Стероиди, SARMS, забранени вещества
   - Лекарства за отслабване
   
   → ОТКАЖИ и обясни защо е опасно. Предложи здравословна алтернатива.

4. ВИНАГИ КОГАТО ДАВАШ план — задължително завършвай със:
   ⚠️ **Важно:** Този план е с информативна цел. Преди да започнеш, консултирай се с личен лекар или квалифициран специалист — особено ако имаш здравословни проблеми, приемаш лекарства или си над 40 години. Слушай тялото си. При болка или дискомфорт — спри.

═══════════════════════════════════════════════════════════
ЕЗИК И ТОН:
═══════════════════════════════════════════════════════════

- АДАПТИВНОСТ: Винаги отговаряй на езика, на който потребителят пише (български или английски).
- На български: ПЕРФЕКТЕН български език без грешки.
- На английски: професионален, мотивационен Luxury Performance tone.

ТЕРМИНОЛОГИЯ:
- ЗАБРАНЕНО Е използването на несъществуващи или неправилни думи.
- ПРОВЕРЯВАЙ всяко упражнение дали е изписано правилно.
- Използвай правилните български термини: клек, напади, лег, гребане, преси, набирания, лицеви опори.

ФОРМАТ:
- Използвай Markdown таблици за хранителните режими и тренировъчните програми.
- Колоните в таблиците да са кратки (3-4 колони максимум за мобилни устройства).
- Тонът: авторитетен, интелигентен, директен — но винаги отговорен.
- Завършвай с: 🔱 **ELITE STATUS: ACTIVE**, последвано от медицинското предупреждение.
"""


# ═══════════════════════════════════════════════════════════
# TOKEN SECURITY FUNCTIONS
# ═══════════════════════════════════════════════════════════

def make_token(expiry_timestamp: int) -> str:
    """Create a signed token. Only someone who knows SECRET can make a valid one."""
    payload = str(expiry_timestamp).encode()
    signature = hmac.new(SECRET.encode(), payload, hashlib.sha256).hexdigest()[:16]
    token = base64.urlsafe_b64encode(f"{expiry_timestamp}.{signature}".encode()).decode().rstrip("=")
    return token


def verify_token(token: str) -> bool:
    """Verify a token is valid and not expired."""
    try:
        # Restore base64 padding
        padded = token + "=" * (-len(token) % 4)
        decoded = base64.urlsafe_b64decode(padded).decode()
        expiry_str, signature = decoded.split(".")
        expiry = int(expiry_str)
        
        # Check if expired
        if time.time() > expiry:
            return False
        
        # Check signature matches
        expected = hmac.new(SECRET.encode(), expiry_str.encode(), hashlib.sha256).hexdigest()[:16]
        return hmac.compare_digest(signature, expected)
    except Exception:
        return False


# ═══════════════════════════════════════════════════════════
# ROUTES
# ═══════════════════════════════════════════════════════════

@app.route("/")
def home():
    return render_template("index.html")


@app.route("/chat", methods=["POST"])
def chat():
    try:
        user_message = request.json.get("message")
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_INSTRUCTIONS},
                {"role": "user", "content": user_message}
            ]
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
            # After payment, Stripe sends user to /success with session_id
            success_url=host_url + '/success?session_id={CHECKOUT_SESSION_ID}',
            cancel_url=host_url + '/?success=false',
        )
        return jsonify({'url': session.url})
    except Exception as e:
        return jsonify(error=str(e)), 403


@app.route('/success')
def payment_success():
    """After payment, verify with Stripe that it really happened, then issue a signed token."""
    session_id = request.args.get('session_id')
    
    if not session_id:
        return redirect('/?success=false')
    
    try:
        # Ask Stripe directly if this session was actually paid
        session = stripe.checkout.Session.retrieve(session_id)
        
        if session.payment_status == 'paid':
            # Generate a signed token valid for 30 days
            expiry = int(time.time()) + (30 * 24 * 60 * 60)  # 30 days from now
            token = make_token(expiry)
            return redirect(f'/?token={token}')
        else:
            return redirect('/?success=false')
    except Exception as e:
        return redirect('/?success=false')


@app.route('/verify-token', methods=['POST'])
def verify_token_endpoint():
    """Frontend calls this to check if a stored token is still valid."""
    token = request.json.get('token', '')
    return jsonify({'valid': verify_token(token)})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
