from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from openai import OpenAI
import os
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from openai import OpenAI

# Инициализираме Flask с правилните папки за статични файлове и шаблони
app = Flask(__name__, 
            static_folder='static', 
            template_folder='templates')
CORS(app)

# Конфигурация на OpenAI клиента
# Увери се, че в Railway си добавил OPENAI_API_KEY в Variables
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

@app.route("/")
def home():
    """Зарежда главния интерфейс на APEX MIND."""
    try:
        return render_template("index.html")
    except Exception as e:
        return f"Грешка: Файлът index.html не е намерен в папка templates. ({str(e)})", 404

@app.route("/chat", methods=["POST"])
def chat():
    """Обработва съобщенията и връща професионални съвети."""
    try:
        # 1. Проверка на данните от потребителя
        data = request.json
        if not data or "message" not in data:
            return jsonify({"reply": "Системата не получи съобщение. Моля, опитайте пак. ⚠️"}), 400
        
        user_message = data.get("message")

        # 2. Повикване на OpenAI с елитен тренировъчен промпт
        response = client.chat.completions.create(
            model="gpt-4o-mini", # Най-бързият и стабилен модел
            messages=[
                {
                    "role": "system",
                    "content": """Ти си APEX MIND - елитен AI ментор по фитнес и бодибилдинг на ниво Mr. Olympia.
                    
                    ПРАВИЛА ЗА ПОВЕДЕНИЕ:
                    - СТРУКТУРА: Винаги подреждай информацията в списъци, таблици или кратки блокове.
                    - ТОН: Професионален, авторитетен, интелигентен и силно мотивиращ. БЕЗ уличен жаргон.
                    - СЪДЪРЖАНИЕ: Давай конкретни параметри - грамажи, повторения, почивка, принципи на периодизация.
                    - ЗАБАВЛЕНИЕ: Използвай емоджита (🦾, 🔱, 💥, 🥗, 🔴) за визуална енергия.
                    - ДЕВИЗ: Винаги помни 'Train the body. Master the mind.'
                    
                    Целта ти е да дадеш на потребителя професионален план, който лесно може да бъде копиран и изпълнен."""
                },
                {"role": "user", "content": user_message}
            ],
            temperature=0.7, # Баланс между креативност и точност
            max_tokens=1000  # Достатъчно дължина за подробен план
        )

        # 3. Извличане на отговора
        reply = response.choices[0].message.content
        return jsonify({"reply": reply})

    except Exception as e:
        # Логване на грешката в конзолата на Railway за дебъгване
        print(f"CRITICAL ERROR: {str(e)}")
        return jsonify({
            "reply": "В момента имам техническо претоварване в ядрото. Моля, опитайте след минута. 🔴",
            "error": str(e)
        }), 500

if __name__ == "__main__":
    # Портът се взима автоматично от Railway
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
