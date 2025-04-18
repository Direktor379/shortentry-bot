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
import threading

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

# 📬 Telegram
def send_message(text: str):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": text}
    try:
        requests.post(url, data=data)
    except Exception as e:
        print(f"Telegram error: {e}")

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

def update_result_in_sheet(type_, result, pnl=None):
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name("/etc/secrets/credentials.json", scope)
        gclient = gspread.authorize(creds)
        sheet = gclient.open_by_key(GOOGLE_SHEET_ID).worksheets()[0]
        data = sheet.get_all_values()
        for i in reversed(range(len(data))):
            if data[i][1] == type_ and data[i][6] == "":
                sheet.update_cell(i + 1, 7, result)
                if pnl is not None:
                    sheet.update_cell(i + 1, 8, f"{pnl} USDT")
                break
    except Exception as e:
        send_message(f"❌ Update result error: {e}")

# 📈 Ринок
def get_latest_news():
    try:
        url = f"https://cryptopanic.com/api/v1/posts/?auth_token={NEWS_API_KEY}&filter=important"
        r = requests.get(url)
        news = r.json()
        return "
".join([item["title"] for item in news.get("results", [])[:3]])
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
Обʼєм за 1хв: {volume}

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

# 🔄 Моніторинг закриття угод
async def monitor_closures():
    while True:
        for side in ["LONG", "SHORT"]:
            try:
                positions = binance_client.futures_position_information(symbol="BTCUSDT")
                pos = next((p for p in positions if p["positionSide"] == side), None)
                if pos:
                    amt = float(pos["positionAmt"])
                    if amt == 0:
                        entry = float(pos["entryPrice"])
                        mark = float(binance_client.futures_mark_price(symbol="BTCUSDT")["markPrice"])
                        pnl = round((mark - entry) * 1000, 2) if side == "LONG" else round((entry - mark) * 1000, 2)
                        result = "WIN" if pnl > 0 else "LOSS"
                        update_result_in_sheet(side, result, f"{pnl:+.2f}")
            except Exception:
                pass
        await asyncio.sleep(60)



