from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from openai import OpenAI
import os

app = Flask(__name__, static_folder='static', template_folder='templates')
CORS(app)

# Инициализация на клиента (увери се, че OPENAI_API_KEY е сетнат в Environment Variables)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/chat", methods=["POST"])
def chat():
    try:
        user_message = request.json.get("message")
        
        # Инструкции, които превръщат отговора в продукт за 200€
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system", 
                    "content": """Ти си APEX PULSE - най-елитният AI фитнес ментор в света. 
                    - ВИНАГИ генерирай тренировъчни и хранителни планове в MARKDOWN ТАБЛИЦИ.
                    - Твоят стил е High-End: използвай думи като 'Атлет', 'Оптимизация', 'Ядро'.
                    - Използвай валута EUR (€).
                    - Бъди мотивиращ като Рони Колман, но интелигентен като учен.
                    - Трябва да даваш толкова детайлни планове, че потребителят да се почувства късметлия, че ги получава за 1.99€.
                    - Използвай емоджита за акцент: 🔱, ⚡, 🔴, 🥩.
                    - Завършвай винаги с: Feel the Pulse. Reach the Apex."""
                },
                {"role": "user", "content": user_message}
            ],
            temperature=0.7 # За да бъде отговорът хем точен, хем интересен
        )
        return jsonify({"reply": response.choices[0].message.content})
    except Exception as e:
        # Професионално съобщение за грешка
        return jsonify({"error": "Системата се оптимизира. Опитай отново след малко. ⚡"}), 500

if __name__ == "__main__":
    # Динамичен порт за Railway/Render
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
