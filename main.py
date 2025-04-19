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

load_dotenv()
app = FastAPI()

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
NEWS_API_KEY = os.getenv("NEWS_API_KEY")
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
BINANCE_SECRET_KEY = os.getenv("BINANCE_SECRET_KEY")
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
TRADE_USD_AMOUNT = float(os.getenv("TRADE_USD_AMOUNT", 300))

binance_client = Client(api_key=BINANCE_API_KEY, api_secret=BINANCE_SECRET_KEY)
client = OpenAI(api_key=OPENAI_API_KEY)
last_open_interest = None

# 📊 Лог для зведень
gpt_decision_log = []
skip_counter = 0


def send_message(text: str):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": text}
    try:
        requests.post(url, data=data)
    except Exception as e:
        print(f"Telegram error: {e}")

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

def calculate_vwap(symbol="BTCUSDT", interval="1m", limit=10):
    try:
        candles = binance_client.futures_klines(symbol=symbol, interval=interval, limit=limit)
        total_volume = 0
        total_price_volume = 0
        for candle in candles:
            high = float(candle[2])
            low = float(candle[3])
            close = float(candle[4])
            volume = float(candle[5])
            typical_price = (high + low + close) / 3
            total_volume += volume
            total_price_volume += typical_price * volume
        vwap = total_price_volume / total_volume if total_volume > 0 else None
        return vwap
    except Exception as e:
        send_message(f"❌ VWAP error: {e}")
        return None

def is_flat_zone(symbol="BTCUSDT"):
    try:
        price = float(binance_client.futures_mark_price(symbol=symbol)["markPrice"])
        vwap = calculate_vwap(symbol)
        if not vwap:
            return False
        return abs(price - vwap) / price < 0.005
    except:
        return False

def get_last_trades(limit=10):
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name("/etc/secrets/credentials.json", scope)
        gclient = gspread.authorize(creds)
        sh = gclient.open_by_key(GOOGLE_SHEET_ID)
        sheet = sh.worksheets()[0]
        data = sheet.get_all_values()[1:]
        data.reverse()
        gpt_logs = [row for row in data if row[1] in ["LONG", "SHORT", "BOOSTED_LONG", "BOOSTED_SHORT"] and row[6]]
        recent = gpt_logs[:limit]
        result = [f"{i+1}. {row[1]} → {row[6]}" for i, row in enumerate(recent)]
        return "\n".join(result)
    except:
        return ""

def get_stats_summary():
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name("/etc/secrets/credentials.json", scope)
        gclient = gspread.authorize(creds)
        sheet = gclient.open_by_key(GOOGLE_SHEET_ID).worksheet("Stats")
        data = sheet.get_all_values()[1:]
        lines = []
        for row in data:
            if len(row) >= 5:
                lines.append(f"{row[0]}: {row[4]}%")
        return "\n".join(lines)
    except:
        return "Статистика недоступна."

def ask_gpt_trade(type_, news, oi, delta, volume):
    recent_trades = get_last_trades()
    stats_summary = get_stats_summary()

    if is_flat_zone("BTCUSDT") and "BOOSTED" not in type_ and volume < 300:
        return "SKIP\n(Флет із низьким обсягом — сигнал проігноровано.)"

    prompt = f"""
GPT минулі сигнали:
{recent_trades}

Winrate по типах:
{stats_summary}

Open Interest: {oi:,.0f}
Зміна OI: {delta:.2f}%
Обʼєм за 1хв: {volume}

Сигнал: {type_.upper()}

Проаналізуй свої минулі рішення, winrate по типах і дай відповідь:
1. Перший рядок: лише одне слово — сигнал (LONG / SHORT / BOOSTED / SKIP)
2. Другий рядок: твій короткий коментар або логіка
"""

    try:
        res = client.chat.completions.create(
            model="gpt-4-turbo",
            messages=[
                {"role": "system", "content": "Ти професійний трейдинг-аналітик. Відповідай коротко."},
                {"role": "user", "content": prompt}
            ]
        )
        return res.choices[0].message.content.strip()
    except:
        return "SKIP\n(GPT error)"









