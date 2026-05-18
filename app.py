from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from openai import OpenAI
import stripe
import os

app = Flask(__name__, static_folder='static', template_folder='templates')
CORS(app)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

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
- Завършвай с: 🔱 ELITE STATUS: ACTIVE, последвано от медицинското предупреждение (СТРИКТНО ПРЕВЕДЕНО НА ЕЗИКА, НА КОЙТО ОТГОВАРЯШ!).

═══════════════════════════════════════════════════════════
CRITICAL LANGUAGE RULE (ЕЗИКОВО ПРАВИЛО):
═══════════════════════════════════════════════════════════
ALWAYS respond in the EXACT same language as the user's prompt!
- If the user writes in English (EN), your ENTIRE response MUST be in 100% perfect English. This includes ALL headers, tables, exercises, foods, tips, AND THE FINAL MEDICAL DISCLAIMER. NO Bulgarian words allowed!
- Ако потребителят пише на Български (BG), отговаряй на 100% Български език.
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
            success_url=host_url + '/?success=true',
            cancel_url=host_url + '/?success=false',
        )
        return jsonify({'url': session.url})
    except Exception as e:
        return jsonify(error=str(e)), 403

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
