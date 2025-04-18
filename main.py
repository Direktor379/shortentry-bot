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

# Пам'ять для Open Interest
last_open_interest = None

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

def get_open_interest(symbol="BTCUSDT"):
    try:
        url = "https://fapi.binance.com/fapi/v1/openInterest"
        params = {"symbol": symbol}
        response = requests.get(url, params=params)
        if response.status_code == 200:
            data = response.json()
            return float(data["openInterest"])
        return None
    except:
        return None

def ask_gpt(signal: str, news: str, open_interest: float, delta_percent: float):
    oi_str = f"{open_interest:,.0f}" if open_interest is not None else "невідомо"
    delta_str = f"{delta_percent:.2f}%" if delta_percent is not None else "0.00%"

    prompt = f"""
Останні новини:
{news}

Open Interest (поточне): {oi_str}
Зміна Open Interest з минулого сигналу: {delta_str}

Сигнал із TradingView: "{signal}"

Враховуючи зміну Open Interest, новини і сигнал — відповідай одним словом:
- SHORT
- BOOSTED_SHORT
- SKIP
"""
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Ти трейдинг-аналітик. Приймай рішення тільки: SHORT, BOOSTED_SHORT або SKIP."},
                {"role": "user", "content": prompt.strip()}
            ]
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"GPT error: {e}"

def get_quantity(symbol: str, usd_amount: float):
    try:
        info = binance_client.futures_exchange_info()
        for s in info["symbols"]:
            if s["symbol"] == symbol:
                step_size = float(next(f["stepSize"] for f in s["filters"] if f["filterType"] == "LOT_SIZE"))
                mark_price = float(binance_client.futures_mark_price(symbol=symbol)["markPrice"])
                raw_qty = usd_amount / mark_price
                qty = round(raw_qty - (raw_qty % step_size), 8)
                return qty
    except Exception as e:
        send_message(f"❌ Quantity error: {e}")
        return None

def place_short(symbol: str, usd_amount: float):
    try:
        entry_price = float(binance_client.futures_mark_price(symbol=symbol)["markPrice"])
        quantity = get_quantity(symbol, usd_amount)
        if quantity is None or quantity == 0:
            send_message("❌ Неможливо розрахувати обсяг. Угоду не відкрито.")
            return None

        tp_price = round(entry_price * 0.99, 2)
        sl_price = round(entry_price * 1.008, 2)

        order = binance_client.futures_create_order(
            symbol=symbol,
            side='SELL',
            type='MARKET',
            quantity=quantity,
            positionSide='SHORT'
        )

        binance_client.futures_create_order(
            symbol=symbol,
            side="BUY",
            type="TAKE_PROFIT_MARKET",
            stopPrice=tp_price,
            closePosition=True,
            timeInForce="GTC"
        )

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
    global last_open_interest
    try:
        body = await req.body()
        signal = body.decode("utf-8").strip()

        news = get_latest_news()
        oi_now = get_open_interest("BTCUSDT")

        if oi_now is None:
            send_message("⚠️ Open Interest не вдалося завантажити. Пропускаємо сигнал.")
            return {"error": "Open Interest is None"}

        delta_percent = 0
        if last_open_interest:
            delta_percent = ((oi_now - last_open_interest) / last_open_interest) * 100

        last_open_interest = oi_now

        gpt_response = ask_gpt(signal, news, oi_now, delta_percent)
        send_message(f"🧠 GPT-відповідь: {gpt_response}")

        if gpt_response in ["SHORT", "BOOSTED_SHORT"]:
            place_short(symbol="BTCUSDT", usd_amount=1000)

        return {"ok": True}
    except Exception as e:
        send_message(f"❌ Webhook error: {e}")
        return {"error": str(e)}







