from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from openai import OpenAI
import os

app = Flask(__name__, template_folder='.') # Слагаме това, ако index.html е в същата папка
CORS(app)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/chat", methods=["POST"])
def chat():
    user_message = request.json.get("message")

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": """Ти си най-якият фитнес треньор в България през 2026 г. 
                Говориш на 'ти', използваш жаргон (бро, машина, маняк, топ), но си професионалист. 
                Отговаряй кратко (макс 2-3 изречения). Използвай много емоджита. 
                Ако те питат за мързел - скарай им се приятелски. Ако те питат за прогрес - хайпни ги!"""
            },
            {"role": "user", "content": user_message}
        ]
    )

    reply = response.choices[0].message.content
    return jsonify({"reply": reply})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
