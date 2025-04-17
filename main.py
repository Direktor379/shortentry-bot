from fastapi import FastAPI, Request
import requests
import os
from dotenv import load_dotenv
import openai

# 🤖 Оновлення GPT логіки — серія перевірки для Render
# Завантаження токенів із .env
load_dotenv()
app = FastAPI()

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai.api_key = OPENAI_API_KEY

# Функція надсилання повідомлення в Telegram
def send_message(text: str):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": text}
    requests.post(url, data=data)

# Функція запиту до GPT
def ask_gpt(signal: str):
    prompt = f"""
    Є сигнал на SHORT. Поточний текст сигналу: "{signal}"
    Визнач чи варто входити в позицію. Відповідь має бути лише однією з трьох:
    - SHORT
    - BOOSTED_SHORT
    - SKIP
    """
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "Ти трейдинг аналітик. Відповідай лише: SHORT, BOOSTED_SHORT або SKIP."},
                {"role": "user", "content": prompt.strip()}
            ]
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"GPT error: {e}"

# Webhook обробляє сигнал
@app.post("/webhook")
async def webhook(req: Request):
    try:
        body = await req.body()
        signal = body.decode("utf-8").strip()

        gpt_response = ask_gpt(signal)
        send_message(f"📩 GPT-відповідь на сигнал '{signal}': {gpt_response}")
        return {"ok": True}
    except Exception as e:
        send_message(f"❌ Помилка Webhook: {e}")
        return {"error": str(e)}





