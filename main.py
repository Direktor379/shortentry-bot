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

# Binance
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

def ask_gpt(signal: str, news: str, unrealized_profit: float = 0):
    prompt = f"""
Останні новини:
{news}

Сигнал: "{signal}"
Наразі позиція у прибутку: {unrealized_profit}%

Питання: чи варто підтягнути стоп ближче до поточної ціни?

Відповідай одним із варіантів:
- Підтягнути до беззбитку
- Підтягнути до +0.5%
- Не підтягувати
"""
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Ти трейдинг-аналітик. Допомагаєш з підтягуванням стопу у позиції."},
                {"role": "user", "content": prompt.strip()}
            ]
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"GPT error: {e}"

def place_short(symbol: str, usd_amount: float):
    try:
        mark_price_data = binance_client.futures_mark_price(symbol=symbol)
        entry_price = float(mark_price_data["markPrice"])
        quantity = round(usd_amount / entry_price, 5)  # 🔄 Динамічний розрахунок
        tp_price = round(entry_price * 0.99, 2)  # тейк -1%
        sl_price = round(entry_price * 1.008, 2)  # стоп +0.8%

        order = binance_client.futures_create_order(
            symbol=symbol,
            side='SELL',
            type='MARKET',
            quantity=quantity,
            positionSide='SHORT'
        )

        # тейк-профіт
        binance_client.futures_create_order(
            symbol=symbol,
            side="BUY",
            type="TAKE_PROFIT_MARKET",
            stopPrice=tp_price,
            closePosition=True,
            timeInForce="GTC"
        )

        # стоп-лосс
        binance_client.futures_create_order(
            symbol=symbol,
            side="BUY",
            type="STOP_MARKET",
            stopPrice=sl_price,
            closePosition=True,
            timeInForce="GTC"
        )

        send_message(f"✅ SHORT OPEN {entry_price}\n📦 Обсяг: {quantity} BTC\n🎯 TP: {tp_price}\n🛡 SL: {sl_price}")
        return order
    except Exception as e:
        send_message(f"❌ Binance SHORT error: {e}")
        return None

@app.post("/webhook")
async def webhook(req: Request):
    try:
        body = await req.body()
        signal = body.decode("utf-8").strip()
        news = get_latest_news()

        gpt_entry = ask_gpt(signal, news)
        send_message(f"🧠 GPT сигнал: {gpt_entry}")

        if gpt_entry in ["SHORT", "BOOSTED_SHORT"]:
            place_short(symbol="BTCUSDT", usd_amount=1000)

        return {"ok": True}
    except Exception as e:
        send_message(f"❌ Webhook error: {e}")
        return {"error": str(e)}












