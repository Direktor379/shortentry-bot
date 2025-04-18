from fastapi import FastAPI, Request
import requests
import os
from dotenv import load_dotenv
from openai import OpenAI
from binance.client import Client
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import asyncio
import json
import websockets

# 🌍 Завантажуємо змінні середовища
load_dotenv()
app = FastAPI()

@app.get("/")
async def healthcheck():
    return {"status": "running"}

# 🔐 ENV
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
NEWS_API_KEY = os.getenv("NEWS_API_KEY")
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
BINANCE_SECRET_KEY = os.getenv("BINANCE_SECRET_KEY")
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")

# 🔌 Clients
binance_client = Client(api_key=BINANCE_API_KEY, api_secret=BINANCE_SECRET_KEY)
client = OpenAI(api_key=OPENAI_API_KEY)
last_open_interest = None

# 📊 Google Sheets
def log_to_sheet(type_, entry, tp, sl, qty, result=None, comment=""):
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name("/etc/secrets/credentials.json", scope)
        gclient = gspread.authorize(creds)

        sh = gclient.open_by_key(GOOGLE_SHEET_ID)
        sheet = sh.worksheets()[0]

        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        row = [now, type_, entry, tp, sl, qty, result or "", comment]
        sheet.append_row(row)
    except Exception as e:
        send_message(f"❌ Sheets error: {e}")

# 📬 Telegram
def send_message(text: str):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": text}
    requests.post(url, data=data)

# 📈 Ринок
def get_latest_news():
    try:
        url = f"https://cryptopanic.com/api/v1/posts/?auth_token={NEWS_API_KEY}&filter=important"
        r = requests.get(url)
        news = r.json()
        return "\n".join([item["title"] for item in news.get("results", [])[:3]])
    except:
        return "⚠️ Новини не вдалося завантажити."

def get_open_interest(symbol="BTCUSDT"):
    try:
        r = requests.get("https://fapi.binance.com/fapi/v1/openInterest", params={"symbol": symbol})
        return float(r.json()["openInterest"]) if r.ok else None
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
        price = float(binance_client.futures_mark_price(symbol=symbol)["markPrice"])
        for s in info["symbols"]:
            if s["symbol"] == symbol:
                step = float(next(f["stepSize"] for f in s["filters"] if f["filterType"] == "LOT_SIZE"))
                qty = usd / price
                return round(qty - (qty % step), 8)
    except Exception as e:
        send_message(f"❌ Quantity error: {e}")
        return None

# 🤖 GPT
def ask_gpt_trade(type_, news, oi, delta, volume):
    prompt = f"""
Останні новини:
{news}

Open Interest: {oi:,.0f}
Зміна: {delta:.2f}%
Обєм за 1хв: {volume}

Сигнал: {type_.upper()}

Чи підтверджуєш цей сигнал?
- LONG / BOOSTED_LONG / SHORT / BOOSTED_SHORT / SKIP
"""
    try:
        res = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Ти трейдинг-аналітик. Відповідай лише одним зі слів: LONG, BOOSTED_LONG, SHORT, BOOSTED_SHORT, SKIP."},
                {"role": "user", "content": prompt}
            ]
        )
        return res.choices[0].message.content.strip()
    except:
        return "SKIP"

@app.post("/webhook")
async def webhook(req: Request):
    global last_open_interest
    try:
        data = await req.json()
        signal = data.get("message", "").strip().upper()
        send_message(f"📩 Отримано сигнал: {signal}")

        news = get_latest_news()
        oi = get_open_interest("BTCUSDT")
        delta = ((oi - last_open_interest) / last_open_interest) * 100 if last_open_interest and oi else 0
        last_open_interest = oi
        volume = get_volume("BTCUSDT")

        decision = ask_gpt_trade(signal, news, oi, delta, volume)
        send_message(f"🤖 GPT вирішив: {decision}")
        log_to_sheet("GPT_DECISION", "", "", "", "", "", f"{signal} → {decision}")

        if decision in ["LONG", "BOOSTED_LONG"]:
            place_long("BTCUSDT", 1000)
        elif decision in ["SHORT", "BOOSTED_SHORT"]:
            place_short("BTCUSDT", 1000)

        return {"ok": True}
    except Exception as e:
        send_message(f"❌ Webhook error: {e}")
        return {"error": str(e)}

# 🔵 Whale Detector (AggTrades)
agg_trades = []

async def monitor_agg_trades():
    uri = "wss://fstream.binance.com/ws/btcusdt@aggTrade"
    async with websockets.connect(uri) as websocket:
        while True:
            try:
                msg = json.loads(await websocket.recv())
                price = float(msg['p'])
                qty = float(msg['q'])
                direction = 'sell' if msg['m'] else 'buy'
                total = price * qty
                ts = msg['T']

                if total >= 100_000:
                    agg_trades.append({"ts": ts, "value": total, "dir": direction})
                    send_message(f"🐋 {direction.upper()} {round(total):,} USD")

                now = int(datetime.utcnow().timestamp() * 1000)
                agg_trades[:] = [x for x in agg_trades if now - x['ts'] <= 5000]

                for side in ['buy', 'sell']:
                    sum_side = sum(t['value'] for t in agg_trades if t['dir'] == side)
                    if sum_side >= 1_000_000:
                        signal = 'BOOSTED_LONG' if side == 'buy' else 'BOOSTED_SHORT'
                        send_message(f"💥 {signal} — $1M+ агресивно за 5 секунд")

                        news = get_latest_news()
                        oi = get_open_interest("BTCUSDT")
                        delta = 0
                        volume = get_volume("BTCUSDT")

                        decision = ask_gpt_trade(signal, news, oi, delta, volume)
                        send_message(f"🤖 GPT вирішив: {decision}")
                        log_to_sheet("GPT_DECISION", "", "", "", "", "", f"{signal} → {decision}")

                        if decision in ["BOOSTED_LONG", "LONG"]:
                            place_long("BTCUSDT", 1000)
                        elif decision in ["BOOSTED_SHORT", "SHORT"]:
                            place_short("BTCUSDT", 1000)
            except Exception as e:
                send_message(f"⚠️ WebSocket error: {e}")
                await asyncio.sleep(5)

# 🚀 Запуск сервера і вебсокета
if __name__ == "__main__":
    import uvicorn
    import threading

    def start_ws():
        asyncio.run(monitor_agg_trades())

    threading.Thread(target=start_ws).start()
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)


