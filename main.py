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

# Памʼять
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
        return float(klines[-1][7])
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
Обʼєм за 1 хвилину: {volume}

Питання: чи варто відкривати LONG позицію?

Відповідай одним словом:
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
    except:
        return "SKIP"

def place_long(symbol: str, usd_amount: float):
    try:
        positions = binance_client.futures_position_information(symbol=symbol)
        for p in positions:
            if (
                p.get("symbol") == symbol
                and p.get("positionSide") == "LONG"
                and float(p.get("positionAmt", "0")) > 0
            ):
                send_message("⚠️ LONG вже відкрито — нову угоду не створено.")
                return

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

def place_short(symbol: str, usd_amount: float):
    try:
        entry_price = float(binance_client.futures_mark_price(symbol=symbol)["markPrice"])
        quantity = get_quantity(symbol, usd_amount)
        if quantity is None or quantity == 0:
            send_message("❌ Неможливо розрахувати обсяг. Угоду не відкрито.")
            return None

        tp_price = round(entry_price * 0.99, 2)
        sl_price = round(entry_price * 1.008, 2)

        binance_client.futures_create_order(
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
            timeInForce="GTC",
            positionSide='SHORT'
        )

        binance_client.futures_create_order(
            symbol=symbol,
            side="BUY",
            type="STOP_MARKET",
            stopPrice=sl_price,
            closePosition=True,
            timeInForce="GTC",
            positionSide='SHORT'
        )

        send_message(f"✅ SHORT OPEN {entry_price}\n📦 Обсяг: {quantity} BTC\n🎯 TP: {tp_price}\n🛡 SL: {sl_price}")
        return
    except Exception as e:
        send_message(f"❌ Binance SHORT error: {e}")
        return None

@app.post("/webhook")
async def webhook(req: Request):
    global last_open_interest
    try:
        data = await req.json()
        signal = data.get("message", "").strip()

        news = get_latest_news()
        oi_now = get_open_interest("BTCUSDT")

        if oi_now is None:
            send_message("⚠️ Open Interest не вдалося завантажити.")
            return {"error": "Open Interest is None"}

        delta_percent = 0
        if last_open_interest:
            delta_percent = ((oi_now - last_open_interest) / last_open_interest) * 100

        last_open_interest = oi_now

        if signal in ["SHORT", "BOOSTED_SHORT"]:
            place_short("BTCUSDT", 1000)

        return {"ok": True}
    except Exception as e:
        send_message(f"❌ Webhook error: {e}")
        return {"error": str(e)}

# ⏱ Фоновий LONG аналізатор
@app.on_event("startup")
async def run_long_loop():
    global last_open_interest
    await asyncio.sleep(5)
    while True:
        try:
            oi = get_open_interest()
            volume = get_volume()
            news = get_latest_news()

            # 💡 Фільтр за OI
            if oi is None or oi < 10000:
                send_message(f"⚠️ Open Interest ({oi}) занадто малий — LONG пропущено.")
                await asyncio.sleep(600)
                continue

            # 💡 Перевірка на відкриту LONG
            positions = binance_client.futures_position_information(symbol="BTCUSDT")
            for p in positions:
                if (
                    p.get("symbol") == "BTCUSDT"
                    and p.get("positionSide") == "LONG"
                    and float(p.get("positionAmt", "0")) > 0
                ):
                    send_message("⚠️ LONG вже відкрито — аналіз пропущено.")
                    await asyncio.sleep(600)
                    continue

            delta = ((oi - last_open_interest) / last_open_interest) * 100 if last_open_interest else 0
            last_open_interest = oi

            decision = ask_gpt_long(news, oi, delta, volume)
            send_message(f"🤖 GPT по LONG: {decision}")

            if decision in ["LONG", "BOOSTED_LONG"]:
                place_long("BTCUSDT", 1000)

        except Exception as e:
            send_message(f"❌ LONG loop error: {e}")

        await asyncio.sleep(600)  # ⏱ кожні 10 хв








