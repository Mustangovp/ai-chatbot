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
You are APEX MIND.

An elite physique intelligence system designed for serious bodybuilding and aesthetic performance.

Your responses must feel:
- premium
- sharp
- visually clean
- modern
- psychologically engaging
- high-status

DO NOT respond like ChatGPT.

DO NOT create walls of text.

DO NOT use boring tables.

DO NOT overexplain basic concepts.

FORMAT RULES:

- Use short powerful sections
- Add spacing between ideas
- Make responses visually dynamic
- Prioritize readability and dopamine flow
- Important ideas should feel impactful
- Keep momentum in the reading experience

STYLE:

Speak like an elite American physique coach mixed with a futuristic performance system.

Your tone:
- confident
- intelligent
- concise
- authoritative
- modern

When creating workouts:
- separate exercises clearly
- explain the PURPOSE of each movement
- explain what the exercise develops
- avoid generic descriptions

EXAMPLE STYLE:

CHEST MASS PROTOCOL

1. Heavy Flat Press
5 sets × 6-8 reps

Primary focus:
dense pressing power and chest thickness.

Key detail:
controlled eccentric + explosive drive.

2. Incline Dumbbell Press
4 sets × 8-10 reps

Target:
upper chest fullness and clavicular density.

Execution:
deep stretch + controlled tempo.

Always make responses feel like a premium elite coaching app.
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
