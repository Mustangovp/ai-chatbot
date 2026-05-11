from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from openai import OpenAI
import stripe
import os

# Инициализация на Flask приложението
app = Flask(__name__, static_folder='static', template_folder='templates')
CORS(app)

# --- КОНФИГУРАЦИЯ НА КЛЮЧОВЕТЕ ---
# Ключовете се вземат от Railway Variables за максимална сигурност
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

# --- СИСТЕМНИ ИНСТРУКЦИИ (AI ПРОФИЛ) ---
SYSTEM_INSTRUCTIONS = """
Ти си APEX PULSE PRO – най-високотехнологичният AI биохакер и фитнес ментор в света.
Твоята цел е да предоставиш елитно преживяване на Атлетите.

ПРАВИЛА:
1. ПРАВОПИС: Използвай перфектен, богат и професионален български език. Без грешки!
2. ФОРМАТ: Всички планове, макроси и графици ВИНАГИ се представят в Markdown ТАБЛИЦИ.
3. СТИЛ: Тонът е "Elite Performance". Наричай потребителя "Атлет" или "Шампион".
4. СЪДЪРЖАНИЕ: Бъди конкретен. Давай точни грамажи, повторения и почивки.
5. ЗАВЪРШЕК: Всеки твой отговор задължително завършва с този блок:
---
🔱 **ELITE STATUS: ACTIVE** 🔱
*Feel the Pulse. Reach the Apex.*
"""

@app.route("/")
def home():
    """Зарежда основната страница на приложението."""
    try:
        return render_template("index.html")
    except Exception as e:
        return f"Грешка при зареждане на интерфейса: {str(e)}", 500

@app.route("/chat", methods=["POST"])
def chat():
    """Обработва съобщенията към AI."""
    try:
        data = request.get_json()
        user_message = data.get("message")
        
        if not user_message:
            return jsonify({"reply": "Моля, въведи своята цел, Атлет. 🔱"}), 400

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_INSTRUCTIONS},
                {"role": "user", "content": user_message}
            ],
            temperature=0.7
        )
        
        reply = response.choices[0].message.content
        return jsonify({"reply": reply})
    
    except Exception as e:
        print(f"Грешка в AI модула: {e}")
        return jsonify({"reply": "Системата се оптимизира в момента. Моля, опитай пак след малко. ⚡"}), 500

@app.route('/create-checkout-session', methods=['POST'])
def create_checkout_session():
    try:
        # Взимаме базовия адрес на твоя сайт (напр. https://4727.up.railway.app)
        # Използваме 'https', защото Stripe изисква защитена връзка
        host_url = "https://" + request.host 
        
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'eur',
                    'product_data': {
                        'name': 'APEX PULSE ELITE PRO - 30 Дни',
                        'description': 'Пълен неограничен достъп до AI ментор.',
                    },
                    'unit_amount': 199,
                },
                'quantity': 1,
            }],
            mode='payment',
            # Ето тук добавяме "success=true" ръчно към линка
            success_url=host_url + '/?success=true',
            cancel_url=host_url + '/?success=false',
        )
        return jsonify({'url': session.url})
    except Exception as e:
        # Принтираме грешката в лога на Railway, за да я виждаш
        print(f"Stripe Error: {e}")
        return jsonify(error=str(e)), 403

if __name__ == "__main__":
    # Railway динамично задава порта чрез променливата PORT
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
