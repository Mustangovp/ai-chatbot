from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from openai import OpenAI
import os

app = Flask(__name__, static_folder='static', template_folder='templates')
CORS(app)

# Инициализация на клиента
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ТОП ИНСТРУКЦИИ ЗА ЕЛИТЕН AI ТРЕНЬОР
SYSTEM_INSTRUCTIONS = """
Ти си APEX PULSE PRO - последно поколение AI за биохакинг, фитнес и трансформация.
Твоята цел е да предоставиш преживяване за 200€ на цена от 1.99€.

ПРАВИЛА:
1. ПРАВОПИС: Пиши на перфектен, академичен български език. Без жаргон (освен фитнес терминология).
2. ТАБЛИЦИ: Всички планове, макроси и графици ВИНАГИ се представят в Markdown таблици.
3. ТОН: Тонът е "Luxury & High-Performance". Наричай потребителя "Атлет" или "Шампион".
4. СТРУКТУРА: Използвай професионални термини (напр. "Хипертрофия", "Гликогенен синтез").
5. ЕМОДЖИТА: Използвай 🔱, ⚡, 🔴 за акцент.
6. ЗАВЪРШЕК: Всеки отговор завършва с:
---
🔱 **ELITE STATUS: ACTIVE** 🔱
*Feel the Pulse. Reach the Apex.*
"""

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/chat", methods=["POST"])
def chat():
    try:
        user_data = request.json
        user_message = user_data.get("message")
        
        response = client.chat.completions.create(
            model="gpt-4o-mini", # Най-бързият и прецизен модел за случая
            messages=[
                {"role": "system", "content": SYSTEM_INSTRUCTIONS},
                {"role": "user", "content": user_message}
            ],
            temperature=0.7
        )
        return jsonify({"reply": response.choices[0].message.content})
    except Exception as e:
        return jsonify({"error": "Системата се оптимизира. Опитай отново. ⚡"}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
