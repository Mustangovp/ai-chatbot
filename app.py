from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from openai import OpenAI
import stripe
import os

app = Flask(__name__, static_folder='static', template_folder='templates')
CORS(app)

# Ключове от Environment Variables
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

SYSTEM_INSTRUCTIONS = """
Ти си APEX PULSE PRO - елитен AI биохакер. 
1. ПРАВОПИС: Перфектен български език.
2. ТАБЛИЦИ: Използвай Markdown таблици за всички режими.
3. ТОН: Авторитетен и мотивиращ.
4. ЗАВЪРШЕК: 🔱 **ELITE STATUS: ACTIVE** 🔱
"""

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
            success_url='https://' + request.host + '/?success=true',
            cancel_url='https://' + request.host + '/?cancel=true',
        )
        return jsonify({'url': session.url})
    except Exception as e:
        return jsonify(error=str(e)), 403

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
