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
# (залишено без змін, твоя логіка log_to_sheet)

# 📬 Telegram
# (залишено без змін)

# 📈 Ринок, get_open_interest(), get_volume(), get_quantity()
# (залишено без змін)

# 🤖 GPT: ask_gpt_trade()
# (залишено без змін)

# 🟢/🔴 place_long() і place_short()
# (залишено без змін)

# ✅ Webhook
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

# 🐋 Whale Detector (AggTrades)
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

# 🚀 Запуск сервера + WebSocket
if __name__ == "__main__":
    import uvicorn
    import threading

    def start_ws():
        asyncio.run(monitor_agg_trades())

    threading.Thread(target=start_ws).start()
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)



