from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from openai import OpenAI
import stripe
import os

app = Flask(__name__, static_folder='static', template_folder='templates')
CORS(app)

# Инициализация с проверка
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY", "no-key"))
stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "no-key")

@app.route("/")
def home():
    try:
        return render_template("index.html")
    except Exception as e:
        return f"Грешка при зареждане на шаблона: {e}", 500

@app.route("/chat", methods=["POST"])
def chat():
    try:
        data = request.get_json()
        user_message = data.get("message")
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Ти си APEX PULSE PRO - елитен треньор. Използвай Markdown таблици."},
                {"role": "user", "content": user_message}
            ]
        )
        return jsonify({"reply": response.choices[0].message.content})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/create-checkout-session', methods=['POST'])
def create_checkout_session():
    try:
        # Проверка дали Stripe е конфигуриран
        if stripe.api_key == "no-key":
            return jsonify({"error": "Stripe не е конфигуриран"}), 500

        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'eur',
                    'product_data': {'name': 'APEX PULSE PRO ACCESS'},
                    'unit_amount': 199,
                },
                'quantity': 1,
            }],
            mode='payment',
            success_url=request.host_url + '?success=true',
            cancel_url=request.host_url + '?cancel=true',
        )
        return jsonify({'url': session.url})
    except Exception as e:
        return jsonify(error=str(e)), 403

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
