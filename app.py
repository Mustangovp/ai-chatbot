from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from openai import OpenAI
import os
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from openai import OpenAI

app = Flask(__name__, 
            static_folder='static', 
            template_folder='templates')
CORS(app)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

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
                {
                    "role": "system", 
                    "content": """Ти си APEX MIND – най-високото ниво AI за фитнес подготовка в България. 
                    Твоите знания съответстват на елитните треньори от 'Mr. Olympia' в САЩ.
                    
                    Твоята мисия: Да предоставиш професионален, научно обоснован подход, който липсва на местния пазар.
                    
                    Инструкции за поведение:
                    1. Анализираш нуждите на всеки индивидуално (възраст, тегло, стаж, цели).
                    2. Използваш терминология от съвременната спортна наука (хипертрофия, периодизация, макронутриенти).
                    3. Тонът ти е авторитетен, безкомпромисен към мързела, но изключително интелигентен и професионален.
                    4. Девиз: 'Train the body. Master the mind.'
                    5. Говориш на български език, чисто и без улични изрази.
                    
                    Ти си стандартът за качество, който България не е виждала досега."""
                },
                {"role": "user", "content": user_message}
            ]
        )
        return jsonify({"reply": response.choices[0].message.content})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
