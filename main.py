from fastapi import FastAPI, Request
import telegram
import os
from dotenv import load_dotenv
import openai

load_dotenv()

TELEGRAM_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

bot = telegram.Bot(token=TELEGRAM_TOKEN)
openai.api_key = OPENAI_API_KEY

app = FastAPI()

@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    message = data.get("message", "empty")

    # GPT аналіз (тестова відповідь)
    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "Ти криптоаналітик, що дає коротку оцінку сигналу."},
            {"role": "user", "content": f"Оціни цей шорт-сигнал: {message}"}
        ]
    )
    gpt_reply = response["choices"][0]["message"]["content"]

    text = f"📉 SHORT сигнал: {message}\n\n💡 GPT-аналіз: {gpt_reply}"
    await bot.send_message(chat_id=CHAT_ID, text=text)
    return {"ok": True}

