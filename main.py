from fastapi import FastAPI, Request
import requests
import os
from dotenv import load_dotenv
from openai import OpenAI
from binance.client import Client

load_dotenv()
app = FastAPI()

# Telegram
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

# GPT
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY)

# CryptoPanic
NEWS_API_KEY = os.getenv("NEWS_API_KEY")

# Binance API
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
BINANCE_SECRET_KEY = os.getenv("BINANCE_SECRET_KEY")
binance_client = Client(api_key=BINANCE_API_KEY, api_secret=BINANCE_SECRET_KEY)

def send_message(text: str):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": text}
    requests.post(url, data=data)

def get_latest_news():
    try:
        url = f"https://cryptopanic.com/api/v1/posts/?auth_token={NEWS_API_KEY}&filter=important"
        response = requests.get(url)
        news = response.json()
        headlines = [item["title"] for item in news.get("results", [])[:3]]
        return "\n".join(headlines)
    except:
        return "⚠️ Новини не вдалося завантажити."

def ask_gpt(signal: str, news: str):
    prompt = f"""
Останні новини:
{news}

Сигнал: "{signal}"
Відповідай лише одним словом:
- SHORT
- BOOSTED_SHORT
- SKIP
"""
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Ти трейдинг-аналітик. Відповідай лише: SHORT, BOOSTED_SHORT або SKIP."},
                {"role": "user", "content": prompt.strip()}
            ]
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"GPT error: {e}"

def place_short(symbol: str, quantity: float):
    try:
        order = binance_client.futures_create_order(
            symbol=symbol,
            side='SELL',
            type='MARKET',
            quantity=quantity
            # positionSide параметр прибрано
        )
        send_message(f"📉 Відкрито SHORT: {symbol}, обсяг: {quantity}")
        return order
    except Exception as e:
        send_message(f"❌ Binance SHORT error: {e}")
        return None

@app.post("/webhook")
async def webhook(req: Request):
    try:
        body = await req.body()
        signal = body.decode("utf-8").strip()
        news_context = get_latest_news()
        gpt_response = ask_gpt(signal, news_context)
        send_message(f"🧠 GPT-відповідь: {gpt_response}")

        if gpt_response in ["SHORT", "BOOSTED_SHORT"]:
            place_short(symbol="BTCUSDT", quantity=0.01)

        return {"ok": True}
    except Exception as e:
        send_message(f"❌ Webhook error: {e}")
        return {"error": str(e)}









