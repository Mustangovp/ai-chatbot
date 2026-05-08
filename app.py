from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from openai import OpenAI
import os

app = Flask(__name__)
CORS(app)

# API ключ от Railway
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

@app.route("/")
def home():
    # Трябва да е в папка 'templates'
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
                    "content": """Ти си APEX MIND - елитен AI ментор. 
                    Тонът ти е: висок клас, интелигентен, авторитетен и силно мотивиращ. 
                    НЕ използваш уличен жаргон (брат, маняк и т.н.). 
                    Твоят девиз е: 'Train the body. Master the mind.' 
                    Даваш конкретни, научно обосновани съвети за дисциплина, фитнес и хранене. 
                    Използвай емоджита за акцент (🔴, 🦾, 🔱). 
                    Отговаряй на български, кратко и със стил."""
                },
                {"role": "user", "content": user_message}
            ]
        )
        return jsonify({"reply": response.choices[0].message.content})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
