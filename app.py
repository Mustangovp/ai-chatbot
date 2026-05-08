from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from openai import OpenAI
import os

app = Flask(__name__)
CORS(app)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

@app.route("/")
def home():
    # Файлът index.html трябва да е в папка 'templates'
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
                    "content": """Ти си официалният AI асистент на APEX MIND. 
                    Твоят тон е сериозен, професионален, уважителен и силно мотивиращ. 
                    Използваш учтивата форма (Вие), когато е уместно, или директен, но културен изказ. 
                    Девизът ти е: 'Train the body. Master the mind.' 
                    Избягвай уличен жаргон. Давай експертни съвети за тренировки, хранене и психическа устойчивост. 
                    Отговаряй кратко и по същество на български език."""
                },
                {"role": "user", "content": user_message}
            ]
        )
        return jsonify({"reply": response.choices[0].message.content})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
