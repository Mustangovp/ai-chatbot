from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from openai import OpenAI
import os
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from openai import OpenAI

# Инициализираме Flask с изрично посочени папки
app = Flask(__name__, 
            static_folder='static', 
            template_folder='templates')
CORS(app)

# Твоят OpenAI клиент
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

@app.route("/")
def home():
    # Това ще зареди новия index.html от папка templates
    return render_template("index.html")

@app.route("/chat", methods=["POST"])
def chat():
    try:
        user_message = request.json.get("message")
        
        response = client.chat.completions.create(
            model="gpt-4o-mini", # Увери се, че е този модел!
            messages=[
                {
                    "role": "system", 
                    "content": "Ти си APEX MIND - елитен AI ментор. Тонът ти е професионален и авторитетен. Девиз: Train the body. Master the mind."
                },
                {"role": "user", "content": user_message}
            ]
        )
        return jsonify({"reply": response.choices[0].message.content})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
