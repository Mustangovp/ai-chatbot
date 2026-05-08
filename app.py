from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from openai import OpenAI
import os

app = Flask(__name__)
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
                "content": """Ти си APEX MIND - най-мощният AI за физическа и ментална трансформация. 
                Твоят девиз е 'Train the body. Master the mind.' 
                Говориш директно, мотивиращо и малко сурово, като елитен треньор. 
                Използваш червени емоджита (💥, 🔴, 🔱, 🦾). 
                Отговаряй на български, кратко и с фокус върху дисциплината и резултатите. 
                Не си просто асистент, ти си лидерът на техния прогрес."""
            },
            {"role": "user", "content": user_message}
        ]
    )

    return jsonify({"reply": response.choices[0].message.content})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
