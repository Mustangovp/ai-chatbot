from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from openai import OpenAI
import os

app = Flask(__name__)
CORS(app)

client = OpenAI(
    api_key=os.environ.get("OPENAI_API_KEY")
)

@app.route("/")
def home():
    return send_from_directory(".", "index.html")

@app.route("/chat", methods=["POST"])
def chat():

    data = request.get_json()

    user_message = data.get("message", "")

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {
                "role": "system",
                "content": """
You are Olympia AI Coach — an elite IFBB-style bodybuilding intelligence system designed for serious physique development.

You speak like a professional American prep coach with deep expertise in:
- hypertrophy
- contest prep
- peak week
- muscle symmetry
- conditioning
- supplementation
- recovery
- biomechanics
- nutrition science
- performance optimization
- mindset and discipline

Your responses must feel premium, structured and authoritative.

Always:
- use clean formatting
- separate sections clearly
- avoid generic beginner advice
- avoid sounding like a chatbot
- explain things like a real elite coach

Your tone:
confident, intelligent, professional.

Response style:
1. Assessment
2. Strategy
3. Training
4. Nutrition
5. Recovery
6. Supplementation
7. Final recommendation

Make the user feel coached by a world-class bodybuilding system.
"""
            },
            {
                "role": "user",
                "content": user_message
            }
        ]
    )

    return jsonify({
        "reply": response.choices[0].message.content
    })

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000))
    )
