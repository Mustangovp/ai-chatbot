from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from openai import OpenAI
import os
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from openai import OpenAI

app = Flask(__name__, static_folder='static', template_folder='templates')
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
                    "content": """Ти си APEX MIND - елитен фитнес ментор. 
                    ОТГОВАРЯЙ ВИНАГИ В MARKDOWN ТАБЛИЦИ ЗА ПРОГРАМИ.
                    Използвай черти (|) за колони. 
                    Валута: EUR (€).
                    Тон: Професионален, агресивен, мотивиращ. 
                    Завършвай с: Train the body. Master the mind."""
                },
                {"role": "user", "content": user_message}
            ]
        )
        return jsonify({"reply": response.choices[0].message.content})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
