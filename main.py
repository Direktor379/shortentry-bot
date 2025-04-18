from fastapi import FastAPI, Request
import requests
import os
import asyncio
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

# Пам'ять
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

def get_volume(symbol="BTCUSDT"):
    try:
        klines = binance_client.futures_klines(symbol=symbol, interval="1m", limit=1)
        return float(klines[-1][7])  # обʼєм
    except:
        return None

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

def ask_gpt_long(news: str, oi: float, delta_oi: float, volume: float):
    prompt = f"""
Останні новини:
{news}

Open Interest: {oi:,.0f}
Зміна Open Interest: {delta_oi:.2f}%
Обʼєм за 1 хвилину: {volume} USDT

Питання: чи варто відкривати LONG позицію?

Відповідай лише одним словом:
- LONG
- BOOSTED_LONG
- SKIP
"""
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Ти трейдинг-аналітик. Відповідай тільки: LONG, BOOSTED_LONG або SKIP."},
                {"role": "user", "content": prompt.strip()}
            ]
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        send_message(f"❌ GPT error: {e}")
        return "SKIP"

def place_long(symbol: str, usd_amount: float):
    try:
        entry = float(binance_client.futures_mark_price(symbol=symbol)["markPrice"])
        qty = get_quantity(symbol, usd_amount)
        if not qty or qty == 0:
            send_message("❌ Неможливо визначити обсяг для LONG.")
            return

        tp = round(entry * 1.015, 2)
        sl = round(entry * 0.992, 2)

        binance_client.futures_create_order(
            symbol=symbol,
            side='BUY',
            type='MARKET',
            quantity=qty,
            positionSide='LONG'
        )

        binance_client.futures_create_order(
            symbol=symbol,
            side="SELL",
            type="TAKE_PROFIT_MARKET",
            stopPrice=tp,
            closePosition=True,
            timeInForce="GTC",
            positionSide="LONG"
        )

        binance_client.futures_create_order(
            symbol=symbol,
            side="SELL",
            type="STOP_MARKET",
            stopPrice=sl,
            closePosition=True,
            timeInForce="GTC",
            positionSide="LONG"
        )

        send_message(f"🟢 LONG OPEN {entry}\n📦 Обсяг: {qty}\n🎯 TP: {tp}\n🛡 SL: {sl}")
    except Exception as e:
        send_message(f"❌ Binance LONG error: {e}")

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

        gpt_response = signal  # коротко, бо signal вже від TradingView
        if gpt_response in ["SHORT", "BOOSTED_SHORT"]:
            place_short(symbol="BTCUSDT", usd_amount=1000)

        return {"ok": True}
    except Exception as e:
        send_message(f"❌ Webhook error: {e}")
        return {"error": str(e)}

# ⏱ LONG-цикл щохвилини
async def long_checker():
    global last_open_interest
    await asyncio.sleep(5)  # стартова затримка
    while True:
        try:
            oi_now = get_open_interest()
            volume = get_volume()
            news = get_latest_news()

            if oi_now and last_open_interest:
                delta = ((oi_now - last_open_interest) / last_open_interest) * 100
            else:
                delta = 0

            last_open_interest = oi_now

            gpt_decision = ask_gpt_long(news, oi_now, delta, volume)
            send_message(f"🤖 GPT по LONG: {gpt_decision}")

            if gpt_decision in ["LONG", "BOOSTED_LONG"]:
                place_long("BTCUSDT", 1000)

        except Exception as e:
            send_message(f"❌ LONG loop error: {e}")

        await asyncio.sleep(60)  # чекати 1 хвилину

# Запуск фонового loop при старті сервера
@app.on_event("startup")
async def startup_event():
    asyncio.create_task(long_checker())







