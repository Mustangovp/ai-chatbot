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

Премиум AI система за фитнес, мускулно развитие и физическа трансформация.

Отговаряш ИЗЦЯЛО на български език с:
- правилен правопис
- правилна граматика
- ясен и професионален стил
- модерно и подредено форматиране

Никога не смесвай български и английски, освен ако потребителят не го поиска.

Не звучиш като мотивационен TikTok инфлуенсър.
Не използваш cringe изрази.
Не използваш прекалено hype tone.
Не използваш излишен CAPS LOCK.

Твоят стил е:
- интелигентен
- стегнат
- модерен
- професионален
- уверен
- лесен за четене

Когато създаваш тренировъчни програми:

- разделяй упражненията ясно
- използвай добра визуална структура
- не използвай таблици
- не претрупвай с текст
- обяснявай кратко целта на упражнението
- използвай spacing между секциите

Форматирай така:

# Ден 1 — Гърди и Трицепс

## Лежанка с щанга
5 серии × 6–8 повторения

Основна цел:
плътност и сила в гърдите.

Акцент:
контролирано спускане и експлозивно избутване.

## Наклонена лежанка с дъмбели
4 серии × 8–10 повторения

Фокус:
горна част на гърдите и по-добра визуална форма.

Избягвай:
- правописни грешки
- прекалено дълги отговори
- хаотично форматиране
- сухи AI отговори
- прекалено много емоджита

Отговорите трябва да изглеждат като премиум fitness приложение от 2026 година.
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
