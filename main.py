from fastapi import FastAPI, Request
import requests
import os
import asyncio
from dotenv import load_dotenv
from openai import OpenAI
from binance.client import Client

load_dotenv()
app = FastAPI()

# Конфіг
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
NEWS_API_KEY = os.getenv("NEWS_API_KEY")
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
BINANCE_SECRET_KEY = os.getenv("BINANCE_SECRET_KEY")

# Binance клієнт
binance_client = Client(api_key=BINANCE_API_KEY, api_secret=BINANCE_SECRET_KEY)
client = OpenAI(api_key=OPENAI_API_KEY)
last_open_interest = None

def send_message(text: str):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": CHAT_ID, "text": text})

def get_latest_news():
    try:
        url = f"https://cryptopanic.com/api/v1/posts/?auth_token={NEWS_API_KEY}&filter=important"
        response = requests.get(url)
        headlines = [item["title"] for item in response.json().get("results", [])[:3]]
        return "\n".join(headlines)
    except:
        return "⚠️ Новини не вдалося завантажити."

def get_open_interest(symbol="BTCUSDT"):
    try:
        res = requests.get("https://fapi.binance.com/fapi/v1/openInterest", params={"symbol": symbol})
        return float(res.json()["openInterest"]) if res.ok else None
    except:
        return None

def get_volume(symbol="BTCUSDT"):
    try:
        data = binance_client.futures_klines(symbol=symbol, interval="1m", limit=1)
        return float(data[-1][7])
    except:
        return None

def get_quantity(symbol: str, usd: float):
    try:
        info = binance_client.futures_exchange_info()
        mark_price = float(binance_client.futures_mark_price(symbol=symbol)["markPrice"])
        for s in info["symbols"]:
            if s["symbol"] == symbol:
                step = float(next(f["stepSize"] for f in s["filters"] if f["filterType"] == "LOT_SIZE"))
                raw = usd / mark_price
                return round(raw - (raw % step), 8)
    except Exception as e:
        send_message(f"❌ Quantity error: {e}")
        return None

def ask_gpt_long(news: str, oi: float, delta: float, volume: float):
    prompt = f"""
Останні новини:
{news}

Open Interest: {oi:,.0f}
Зміна OI: {delta:.2f}%
Обʼєм: {volume}

Чи варто відкривати LONG?

Відповідь одним словом:
- LONG
- BOOSTED_LONG
- SKIP
"""
    try:
        res = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Ти трейдинг-аналітик. Відповідай тільки: LONG, BOOSTED_LONG або SKIP."},
                {"role": "user", "content": prompt}
            ]
        )
        return res.choices[0].message.content.strip()
    except:
        return "SKIP"

def place_long(symbol: str, usd: float):
    try:
        pos = binance_client.futures_position_information(symbol=symbol)
        if any(p["positionSide"] == "LONG" and float(p["positionAmt"]) > 0 for p in pos):
            send_message("⚠️ LONG вже відкрито")
            return

        entry = float(binance_client.futures_mark_price(symbol=symbol)["markPrice"])
        qty = get_quantity(symbol, usd)
        if not qty:
            send_message("❌ Обсяг не визначено.")
            return

        tp = round(entry * 1.015, 2)
        sl = round(entry * 0.992, 2)

        binance_client.futures_create_order(symbol=symbol, side='BUY', type='MARKET', quantity=qty, positionSide='LONG')
        binance_client.futures_create_order(symbol=symbol, side='SELL', type='TAKE_PROFIT_MARKET',
            stopPrice=tp, closePosition=True, timeInForce="GTC", positionSide='LONG')
        binance_client.futures_create_order(symbol=symbol, side='SELL', type='STOP_MARKET',
            stopPrice=sl, closePosition=True, timeInForce="GTC", positionSide='LONG')

        send_message(f"🟢 LONG OPEN {entry}\n📦 Qty: {qty}\n🎯 TP: {tp}\n🛡 SL: {sl}")
    except Exception as e:
        send_message(f"❌ Binance LONG error: {e}")

def place_short(symbol: str, usd: float):
    try:
        pos = binance_client.futures_position_information(symbol=symbol)
        if any(p["positionSide"] == "SHORT" and float(p["positionAmt"]) > 0 for p in pos):
            send_message("⚠️ SHORT вже відкрито")
            return

        entry = float(binance_client.futures_mark_price(symbol=symbol)["markPrice"])
        qty = get_quantity(symbol, usd)
        if not qty:
            send_message("❌ Обсяг не визначено.")
            return

        tp = round(entry * 0.99, 2)
        sl = round(entry * 1.008, 2)

        binance_client.futures_create_order(symbol=symbol, side='SELL', type='MARKET', quantity=qty, positionSide='SHORT')
        binance_client.futures_create_order(symbol=symbol, side='BUY', type='TAKE_PROFIT_MARKET',
            stopPrice=tp, closePosition=True, timeInForce="GTC", positionSide='SHORT')
        binance_client.futures_create_order(symbol=symbol, side='BUY', type='STOP_MARKET',
            stopPrice=sl, closePosition=True, timeInForce="GTC", positionSide='SHORT')

        send_message(f"🔴 SHORT OPEN {entry}\n📦 Qty: {qty}\n🎯 TP: {tp}\n🛡 SL: {sl}")
    except Exception as e:
        send_message(f"❌ Binance SHORT error: {e}")

@app.post("/webhook")
async def webhook(req: Request):
    global last_open_interest
    try:
        data = await req.json()
        signal = data.get("message", "").strip().upper()

        news = get_latest_news()
        oi = get_open_interest("BTCUSDT")
        delta = ((oi - last_open_interest) / last_open_interest) * 100 if last_open_interest and oi else 0
        last_open_interest = oi

        if signal in ["SHORT", "BOOSTED_SHORT"]:
            place_short("BTCUSDT", 1000)
        elif signal in ["LONG", "BOOSTED_LONG"]:
            place_long("BTCUSDT", 1000)

        return {"ok": True}
    except Exception as e:
        send_message(f"❌ Webhook error: {e}")
        return {"error": str(e)}

# 🕒 Фоновий LONG запуск — кожні 10 хв
@app.on_event("startup")
async def long_loop():
    global last_open_interest
    await asyncio.sleep(5)
    while True:
        try:
            oi = get_open_interest("BTCUSDT")
            if not oi or oi < 10000:
                send_message(f"⚠️ OI ({oi}) надто низький")
                await asyncio.sleep(600)
                continue

            pos = binance_client.futures_position_information(symbol="BTCUSDT")
            if any(p["positionSide"] == "LONG" and float(p["positionAmt"]) > 0 for p in pos):
                send_message("⛔️ LONG вже відкрито — пропускаємо")
                await asyncio.sleep(600)
                continue

            vol = get_volume()
            news = get_latest_news()
            delta = ((oi - last_open_interest) / last_open_interest) * 100 if last_open_interest else 0
            last_open_interest = oi

            decision = ask_gpt_long(news, oi, delta, vol)
            send_message(f"🤖 GPT по LONG: {decision}")
            if decision in ["LONG", "BOOSTED_LONG"]:
                place_long("BTCUSDT", 1000)

        except Exception as e:
            send_message(f"❌ LONG цикл помилка: {e}")
        await asyncio.sleep(600)









