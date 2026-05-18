from flask import Flask, request, jsonify, render_template, session
from flask_cors import CORS
from openai import OpenAI
import stripe
import os
import hashlib
import hmac
import time
import secrets

app = Flask(__name__, static_folder='static', template_folder='templates')
app.secret_key = os.getenv("FLASK_SECRET_KEY", secrets.token_hex(32))
CORS(app, supports_credentials=True)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

# Secret for signing elite tokens — set in Railway env vars
ELITE_SECRET = os.getenv("ELITE_SECRET", "change-me-in-railway-env-vars")

# Free sessions per user
FREE_SESSIONS_LIMIT = 3

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


def make_elite_token(expires_at):
    """Create a signed token that proves user has paid until expires_at."""
    payload = f"{expires_at}"
    sig = hmac.new(
        ELITE_SECRET.encode(),
        payload.encode(),
        hashlib.sha256
    ).hexdigest()[:32]
    return f"{expires_at}.{sig}"


def verify_elite_token(token):
    """Verify a token is valid and not expired. Returns True if valid."""
    if not token or '.' not in token:
        return False
    try:
        expires_at_str, sig = token.rsplit('.', 1)
        expected_sig = hmac.new(
            ELITE_SECRET.encode(),
            expires_at_str.encode(),
            hashlib.sha256
        ).hexdigest()[:32]
        if not hmac.compare_digest(sig, expected_sig):
            return False
        expires_at = int(expires_at_str)
        return time.time() < expires_at
    except (ValueError, AttributeError):
        return False


@app.route("/")
def home():
    # If user came back from Stripe success, issue elite token
    if request.args.get('success') == 'true':
        # 30 days from now
        expires_at = int(time.time()) + (30 * 24 * 60 * 60)
        token = make_elite_token(expires_at)
        session['elite_token'] = token
        session['elite_expires'] = expires_at
        # Reset session counter
        session['chat_count'] = 0
    return render_template("index.html")


@app.route("/api/status", methods=["GET"])
def status():
    """Tell the frontend if user is elite and how many sessions remain."""
    elite_token = session.get('elite_token')
    is_elite = elite_token and verify_elite_token(elite_token)
    chat_count = session.get('chat_count', 0)
    remaining = max(0, FREE_SESSIONS_LIMIT - chat_count)
    return jsonify({
        "elite": bool(is_elite),
        "remaining": remaining if not is_elite else -1,
        "elite_token": elite_token if is_elite else None
    })


@app.route("/chat", methods=["POST"])
def chat():
    try:
        # Check elite status
        elite_token = session.get('elite_token')
        is_elite = elite_token and verify_elite_token(elite_token)
        
        # If not elite, check session count
        if not is_elite:
            chat_count = session.get('chat_count', 0)
            if chat_count >= FREE_SESSIONS_LIMIT:
                return jsonify({
                    "error": "limit_reached",
                    "message": "Достигнат е лимитът от безплатни сесии. Отключи неограничен достъп за 1.99€."
                }), 402  # Payment Required
            session['chat_count'] = chat_count + 1
        
        user_message = request.json.get("message")
        if not user_message or len(user_message) > 2000:
            return jsonify({"error": "invalid_message"}), 400
        
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
        checkout = stripe.checkout.Session.create(
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
            success_url=host_url + '/?success=true',
            cancel_url=host_url + '/?success=false',
        )
        return jsonify({'url': checkout.url})
    except Exception as e:
        return jsonify(error=str(e)), 403


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
