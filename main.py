# main.py — повна фінальна версія

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
import time
from collections import defaultdict

# 🌍 ENV
load_dotenv()
app = FastAPI()

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
NEWS_API_KEY = os.getenv("NEWS_API_KEY")
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
BINANCE_SECRET_KEY = os.getenv("BINANCE_SECRET_KEY")
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
TRADE_USD_AMOUNT = float(os.getenv("TRADE_USD_AMOUNT", 1000))

binance_client = Client(api_key=BINANCE_API_KEY, api_secret=BINANCE_SECRET_KEY)
client = OpenAI(api_key=OPENAI_API_KEY)
last_open_interest = None

# 📬 Telegram

def send_message(text: str):
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data={"chat_id": CHAT_ID, "text": text}
        )
    except Exception as e:
        print(f"Telegram error: {e}")

# 📈 Market utils

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
        return total_price_volume / total_volume if total_volume > 0 else None
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

# Далі — кластерна памʼять, GPT памʼять і логіка трейдів
...
# main_13.py — повна фінальна версія

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
import time
from collections import defaultdict

# 🌍 ENV
load_dotenv()
app = FastAPI()

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
NEWS_API_KEY = os.getenv("NEWS_API_KEY")
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
BINANCE_SECRET_KEY = os.getenv("BINANCE_SECRET_KEY")
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
TRADE_USD_AMOUNT = float(os.getenv("TRADE_USD_AMOUNT", 1000))

binance_client = Client(api_key=BINANCE_API_KEY, api_secret=BINANCE_SECRET_KEY)
client = OpenAI(api_key=OPENAI_API_KEY)
last_open_interest = None

# 📬 Telegram

def send_message(text: str):
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data={"chat_id": CHAT_ID, "text": text}
        )
    except Exception as e:
        print(f"Telegram error: {e}")

# 📈 Market utils

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
        return total_price_volume / total_volume if total_volume > 0 else None
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

# 📊 Cluster storage
CLUSTER_BUCKET_SIZE = 10
CLUSTER_INTERVAL = 60
cluster_data = defaultdict(lambda: {"buy": 0.0, "sell": 0.0})
cluster_last_reset = time.time()

# 🧠 GPT памʼять

def get_recent_mistakes(limit=5):
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name("/etc/secrets/credentials.json", scope)
        gclient = gspread.authorize(creds)
        sheet = gclient.open_by_key(GOOGLE_SHEET_ID).worksheet("Learning Log")
        data = sheet.get_all_values()[1:]
        mistakes = [row for row in reversed(data) if row[2].strip().upper() == "LOSS" and row[4].strip()]
        return "\n".join(f"- {row[4]}" for row in mistakes[:limit])
    except:
        return ""
           
        return ""

def get_recent_trades_and_streak(limit=10):
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name("/etc/secrets/credentials.json", scope)
        gclient = gspread.authorize(creds)
        sheet = gclient.open_by_key(GOOGLE_SHEET_ID).worksheets()[0]
        data = sheet.get_all_values()[1:]
        data.reverse()
        trades = [row for row in data if row[1] in ["LONG", "SHORT", "BOOSTED_LONG", "BOOSTED_SHORT"] and row[6]]
        recent = trades[:limit]
        formatted = [f"{i+1}. {row[1]} → {row[6]}" for i, row in enumerate(recent)]
        streak = 0
        for row in trades:
            if row[6].strip().upper() == "WIN":
                streak += 1
            else:
                break
        return "\n".join(formatted), streak
    except:
        return "", 0

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
        return "Немає статистики"

def ask_gpt_trade_with_all_context(type_, news, oi, delta, volume):
    recent_trades, win_streak = get_recent_trades_and_streak()
    stats_summary = get_stats_summary()
    mistakes = get_recent_mistakes()
    prompt = f"""
GPT минулі сигнали:
{recent_trades}

Winrate по типах:
{stats_summary}

Серія перемог: {win_streak}/5

Попередні помилки:
{mistakes}

Сигнал: {type_.upper()}
Обʼєм: {volume}, Open Interest: {oi}, Зміна OI: {delta:.2f}%
Останні новини:
{news}

Ціль: досягти 5 win-підряд. Прийми зважене рішення. Вибери тільки одне: LONG / SHORT / BOOSTED_LONG / BOOSTED_SHORT / SKIP.
"""
    try:
        res = client.chat.completions.create(
            model="gpt-4-turbo",
            messages=[
                {"role": "system", "content": "Ти скальп-аналітик. Вибери одне: LONG, SHORT, BOOSTED_LONG, BOOSTED_SHORT або SKIP."},
                {"role": "user", "content": prompt}
            ]
        )
        return res.choices[0].message.content.strip()
    except:
        return "SKIP"

def log_learning_entry(trade_type, result, reason, pnl=None):
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name("/etc/secrets/credentials.json", scope)
        gclient = gspread.authorize(creds)
        sh = gclient.open_by_key(GOOGLE_SHEET_ID)
        try:
            sheet = sh.worksheet("Learning Log")
        except:
            sheet = sh.add_worksheet(title="Learning Log", rows="1000", cols="10")
            sheet.append_row(["Time", "Type", "Result", "PnL", "GPT Analysis"])
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        row = [now, trade_type, result, pnl or "", reason]
        sheet.append_row(row)
    except Exception as e:
        send_message(f"❌ Learning Log error: {e}")

def explain_trade_outcome(trade_type, result, pnl):
    try:
        prompt = f"""
Тип угоди: {trade_type}
Результат: {result}
PnL: {pnl}
Поясни коротко (1 реченням), чому результат був таким. Якщо помилка — вкажи її.
"""
        res = client.chat.completions.create(
            model="gpt-4-turbo",
            messages=[
                {"role": "system", "content": "Ти трейдинг-аналітик. Поясни результат угоди коротко."},
                {"role": "user", "content": prompt}
            ]
        )
        return res.choices[0].message.content.strip()
    except:
        return "GPT не зміг проаналізувати угоду"
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
import time
from collections import defaultdict

# 🌍 ENV
load_dotenv()
app = FastAPI()

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
NEWS_API_KEY = os.getenv("NEWS_API_KEY")
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
BINANCE_SECRET_KEY = os.getenv("BINANCE_SECRET_KEY")
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
TRADE_USD_AMOUNT = float(os.getenv("TRADE_USD_AMOUNT", 1000))

binance_client = Client(api_key=BINANCE_API_KEY, api_secret=BINANCE_SECRET_KEY)
client = OpenAI(api_key=OPENAI_API_KEY)
last_open_interest = None

# 📬 Telegram

def send_message(text: str):
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data={"chat_id": CHAT_ID, "text": text}
        )
    except Exception as e:
        print(f"Telegram error: {e}")

# 📈 Market utils

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
        return total_price_volume / total_volume if total_volume > 0 else None
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

# 📊 Cluster storage
CLUSTER_BUCKET_SIZE = 10
CLUSTER_INTERVAL = 60
cluster_data = defaultdict(lambda: {"buy": 0.0, "sell": 0.0})
cluster_last_reset = time.time()

# 🧠 GPT памʼять

def get_recent_mistakes(limit=5):
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name("/etc/secrets/credentials.json", scope)
        gclient = gspread.authorize(creds)
        sheet = gclient.open_by_key(GOOGLE_SHEET_ID).worksheet("Learning Log")
        data = sheet.get_all_values()[1:]
        mistakes = [row for row in reversed(data) if row[2].strip().upper() == "LOSS" and row[4].strip()]
        return "\n".join(f"- {row[4]}" for row in mistakes[:limit])
    except:
        return ""

def get_recent_trades_and_streak(limit=10):
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name("/etc/secrets/credentials.json", scope)
        gclient = gspread.authorize(creds)
        sheet = gclient.open_by_key(GOOGLE_SHEET_ID).worksheets()[0]
        data = sheet.get_all_values()[1:]
        data.reverse()
        trades = [row for row in data if row[1] in ["LONG", "SHORT", "BOOSTED_LONG", "BOOSTED_SHORT"] and row[6]]
        recent = trades[:limit]
        formatted = [f"{i+1}. {row[1]} → {row[6]}" for i, row in enumerate(recent)]
        streak = 0
        for row in trades:
            if row[6].strip().upper() == "WIN":
                streak += 1
            else:
                break
        return "\n".join(formatted), streak
    except:
        return "", 0

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
        return "Немає статистики"

def ask_gpt_trade_with_all_context(type_, news, oi, delta, volume):
    recent_trades, win_streak = get_recent_trades_and_streak()
    stats_summary = get_stats_summary()
    mistakes = get_recent_mistakes()
    prompt = f"""
GPT минулі сигнали:
{recent_trades}

Winrate по типах:
{stats_summary}

Серія перемог: {win_streak}/5

Попередні помилки:
{mistakes}

Сигнал: {type_.upper()}
Обʼєм: {volume}, Open Interest: {oi}, Зміна OI: {delta:.2f}%
Останні новини:
{news}

Ціль: досягти 5 win-підряд. Прийми зважене рішення. Вибери тільки одне: LONG / SHORT / BOOSTED_LONG / BOOSTED_SHORT / SKIP.
"""
    try:
        res = client.chat.completions.create(
            model="gpt-4-turbo",
            messages=[
                {"role": "system", "content": "Ти скальп-аналітик. Вибери одне: LONG, SHORT, BOOSTED_LONG, BOOSTED_SHORT або SKIP."},
                {"role": "user", "content": prompt}
            ]
        )
        return res.choices[0].message.content.strip()
    except:
        return "SKIP"

def log_learning_entry(trade_type, result, reason, pnl=None):
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name("/etc/secrets/credentials.json", scope)
        gclient = gspread.authorize(creds)
        sh = gclient.open_by_key(GOOGLE_SHEET_ID)
        try:
            sheet = sh.worksheet("Learning Log")
        except:
            sheet = sh.add_worksheet(title="Learning Log", rows="1000", cols="10")
            sheet.append_row(["Time", "Type", "Result", "PnL", "GPT Analysis"])
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        row = [now, trade_type, result, pnl or "", reason]
        sheet.append_row(row)
    except Exception as e:
        send_message(f"❌ Learning Log error: {e}")

def explain_trade_outcome(trade_type, result, pnl):
    try:
        prompt = f"""
Тип угоди: {trade_type}
Результат: {result}
PnL: {pnl}
Поясни коротко (1 реченням), чому результат був таким. Якщо помилка — вкажи її.
"""
        res = client.chat.completions.create(
            model="gpt-4-turbo",
            messages=[
                {"role": "system", "content": "Ти трейдинг-аналітик. Поясни результат угоди коротко."},
                {"role": "user", "content": prompt}
            ]
        )
        return res.choices[0].message.content.strip()
    except:
        return "GPT не зміг проаналізувати угоду"     
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
import time
from collections import defaultdict

# 🌍 ENV
load_dotenv()
app = FastAPI()

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
NEWS_API_KEY = os.getenv("NEWS_API_KEY")
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
BINANCE_SECRET_KEY = os.getenv("BINANCE_SECRET_KEY")
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
TRADE_USD_AMOUNT = float(os.getenv("TRADE_USD_AMOUNT", 1000))

binance_client = Client(api_key=BINANCE_API_KEY, api_secret=BINANCE_SECRET_KEY)
client = OpenAI(api_key=OPENAI_API_KEY)
last_open_interest = None

# 📬 Telegram

def send_message(text: str):
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data={"chat_id": CHAT_ID, "text": text}
        )
    except Exception as e:
        print(f"Telegram error: {e}")

# 📈 Market utils

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
        return total_price_volume / total_volume if total_volume > 0 else None
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

# 📊 Cluster storage
CLUSTER_BUCKET_SIZE = 10
CLUSTER_INTERVAL = 60
cluster_data = defaultdict(lambda: {"buy": 0.0, "sell": 0.0})
cluster_last_reset = time.time()

# 🧠 GPT памʼять

def get_recent_mistakes(limit=5):
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name("/etc/secrets/credentials.json", scope)
        gclient = gspread.authorize(creds)
        sheet = gclient.open_by_key(GOOGLE_SHEET_ID).worksheet("Learning Log")
        data = sheet.get_all_values()[1:]
        mistakes = [row for row in reversed(data) if row[2].strip().upper() == "LOSS" and row[4].strip()]
        return "\n".join(f"- {row[4]}" for row in mistakes[:limit])
    except:
        return ""

def get_recent_trades_and_streak(limit=10):
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name("/etc/secrets/credentials.json", scope)
        gclient = gspread.authorize(creds)
        sheet = gclient.open_by_key(GOOGLE_SHEET_ID).worksheets()[0]
        data = sheet.get_all_values()[1:]
        data.reverse()
        trades = [row for row in data if row[1] in ["LONG", "SHORT", "BOOSTED_LONG", "BOOSTED_SHORT"] and row[6]]
        recent = trades[:limit]
        formatted = [f"{i+1}. {row[1]} → {row[6]}" for i, row in enumerate(recent)]
        streak = 0
        for row in trades:
            if row[6].strip().upper() == "WIN":
                streak += 1
            else:
                break
        return "\n".join(formatted), streak
    except:
        return "", 0

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
        return "Немає статистики"

def ask_gpt_trade_with_all_context(type_, news, oi, delta, volume):
    recent_trades, win_streak = get_recent_trades_and_streak()
    stats_summary = get_stats_summary()
    mistakes = get_recent_mistakes()
    prompt = f"""
GPT минулі сигнали:
{recent_trades}

Winrate по типах:
{stats_summary}

Серія перемог: {win_streak}/5

Попередні помилки:
{mistakes}

Сигнал: {type_.upper()}
Обʼєм: {volume}, Open Interest: {oi}, Зміна OI: {delta:.2f}%
Останні новини:
{news}

Ціль: досягти 5 win-підряд. Прийми зважене рішення. Вибери тільки одне: LONG / SHORT / BOOSTED_LONG / BOOSTED_SHORT / SKIP.
"""
    try:
        res = client.chat.completions.create(
            model="gpt-4-turbo",
            messages=[
                {"role": "system", "content": "Ти скальп-аналітик. Вибери одне: LONG, SHORT, BOOSTED_LONG, BOOSTED_SHORT або SKIP."},
                {"role": "user", "content": prompt}
            ]
        )
        return res.choices[0].message.content.strip()
    except:
        return "SKIP"

def log_learning_entry(trade_type, result, reason, pnl=None):
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name("/etc/secrets/credentials.json", scope)
        gclient = gspread.authorize(creds)
        sh = gclient.open_by_key(GOOGLE_SHEET_ID)
        try:
            sheet = sh.worksheet("Learning Log")
        except:
            sheet = sh.add_worksheet(title="Learning Log", rows="1000", cols="10")
            sheet.append_row(["Time", "Type", "Result", "PnL", "GPT Analysis"])
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        row = [now, trade_type, result, pnl or "", reason]
        sheet.append_row(row)
    except Exception as e:
        send_message(f"❌ Learning Log error: {e}")

def explain_trade_outcome(trade_type, result, pnl):
    try:
        prompt = f"""
Тип угоди: {trade_type}
Результат: {result}
PnL: {pnl}
Поясни коротко (1 реченням), чому результат був таким. Якщо помилка — вкажи її.

        res = client.chat.completions.create(
            model="gpt-4-turbo",
                {"role": "system", "content": "Ти трейдинг-аналітик. Поясни результат угоди коротко."},
        try:
    res = client.chat.completions.create(
        model="gpt-4-turbo",
        messages=[
            {"role": "system", "content": "Ти трейдинг-аналітик. Поясни результат угоди коротко."},
            {"role": "user", "content": prompt}
        ]
    )
    return res.choices[0].message.content.strip()
    return res.choices[0].message.content.strip()
except Exception as e:
    return f"GPT не зміг проаналізувати угоду: {e}"

    def place_long(symbol, usd):
    if has_open_position("LONG"):
        send_message("⚠️ Уже відкрита LONG позиція")
        return
    try:
        entry = float(binance_client.futures_mark_price(symbol=symbol)["markPrice"])
        qty = get_quantity(symbol, usd)
        if not qty:
            send_message("❌ Обсяг не визначено.")
            return
        tp = round(entry * 1.015, 2)
        sl = round(entry * 0.992, 2)

        binance_client.futures_create_order(
            symbol=symbol, side='BUY', type='MARKET', quantity=qty, positionSide='LONG')
        binance_client.futures_create_order(
            symbol=symbol, side='SELL', type='TAKE_PROFIT_MARKET',
            stopPrice=tp, closePosition=True, timeInForce="GTC", positionSide='LONG')
        binance_client.futures_create_order(
            symbol=symbol, side='SELL', type='STOP_MARKET',
            stopPrice=sl, closePosition=True, timeInForce="GTC", positionSide='LONG')

        send_message(f"🟢 LONG OPEN {entry}\n📦 Qty: {qty}\n🎯 TP: {tp}\n🛡 SL: {sl}")
        log_to_sheet("LONG", entry, tp, sl, qty, None, "GPT сигнал")
        update_stats_sheet()
    except Exception as e:
        send_message(f"❌ Binance LONG error: {e}")

def place_short(symbol, usd):
    if has_open_position("SHORT"):
        send_message("⚠️ Уже відкрита SHORT позиція")
        return
    try:
        entry = float(binance_client.futures_mark_price(symbol=symbol)["markPrice"])
        qty = get_quantity(symbol, usd)
        tp = round(entry * 0.99, 2)
        sl = round(entry * 1.008, 2)
        binance_client.futures_create_order(symbol=symbol, side='SELL', type='MARKET', quantity=qty, positionSide='SHORT')
        binance_client.futures_create_order(symbol=symbol, side='BUY', type='TAKE_PROFIT_MARKET', stopPrice=tp, closePosition=True, timeInForce="GTC", positionSide='SHORT')
        binance_client.futures_create_order(symbol=symbol, side='BUY', type='STOP_MARKET', stopPrice=sl, closePosition=True, timeInForce="GTC", positionSide='SHORT')
        send_message(f"🔴 SHORT OPEN {entry}\n📦 Qty: {qty}\n🎯 TP: {tp}\n🛡 SL: {sl}")
        log_to_sheet("SHORT", entry, tp, sl, qty, None, "GPT сигнал")
        update_stats_sheet()
    except Exception as e:
        send_message(f"❌ Binance SHORT error: {e}")
# 📡 Кластерний WebSocket аналіз
def has_open_position(side):
    try:
        positions = binance_client.futures_position_information(symbol="BTCUSDT")
        pos = next((p for p in positions if p["positionSide"] == side), None)
        return pos and float(pos["positionAmt"]) != 0
    except:
        return False

async def monitor_cluster_trades():
    uri = "wss://fstream.binance.com/ws/btcusdt@aggTrade"
    async with websockets.connect(uri) as websocket:
        global cluster_last_reset
        while True:
            try:
                msg = json.loads(await websocket.recv())
                price = float(msg['p'])
                qty = float(msg['q'])
                is_sell = msg['m']
                bucket = round(price / CLUSTER_BUCKET_SIZE) * CLUSTER_BUCKET_SIZE
                if is_sell:
                    cluster_data[bucket]['sell'] += qty
                else:
                    cluster_data[bucket]['buy'] += qty

                now = time.time()
                if now - cluster_last_reset >= CLUSTER_INTERVAL:
                    news = get_latest_news()
                    oi = get_open_interest("BTCUSDT")
                    volume = get_volume("BTCUSDT")
                    decision = ask_gpt_trade_with_all_context("CLUSTER", news, oi, 0, volume)
                    if decision in ["LONG", "BOOSTED_LONG"]:
                        place_long("BTCUSDT", TRADE_USD_AMOUNT)
                    elif decision in ["SHORT", "BOOSTED_SHORT"]:
                        place_short("BTCUSDT", TRADE_USD_AMOUNT)
                    else:
                        send_message(f"🤖 GPT кластер: {decision}")
                    cluster_data.clear()
                    cluster_last_reset = now
            except Exception as e:
                send_message(f"⚠️ Cluster WS error: {e}")
                await asyncio.sleep(5)
                # 📡 Кластерний WebSocket аналіз
def has_open_position(side):
    try:
        positions = binance_client.futures_position_information(symbol="BTCUSDT")
        pos = next((p for p in positions if p["positionSide"] == side), None)
        return pos and float(pos["positionAmt"]) != 0
    except:
        return False

async def monitor_cluster_trades():
    uri = "wss://fstream.binance.com/ws/btcusdt@aggTrade"
    async with websockets.connect(uri) as websocket:
        global cluster_last_reset
        while True:
            try:
                msg = json.loads(await websocket.recv())
                price = float(msg['p'])
                qty = float(msg['q'])
                is_sell = msg['m']
                bucket = round(price / CLUSTER_BUCKET_SIZE) * CLUSTER_BUCKET_SIZE
                if is_sell:
                    cluster_data[bucket]['sell'] += qty
                else:
                    cluster_data[bucket]['buy'] += qty

                now = time.time()
                if now - cluster_last_reset >= CLUSTER_INTERVAL:
                    news = get_latest_news()
                    oi = get_open_interest("BTCUSDT")
                    volume = get_volume("BTCUSDT")
                    decision = ask_gpt_trade_with_all_context("CLUSTER", news, oi, 0, volume)
                    if decision in ["LONG", "BOOSTED_LONG"]:
                        place_long("BTCUSDT", TRADE_USD_AMOUNT)
                    elif decision in ["SHORT", "BOOSTED_SHORT"]:
                        place_short("BTCUSDT", TRADE_USD_AMOUNT)
                    else:
                        send_message(f"🤖 GPT кластер: {decision}")
                    cluster_data.clear()
                    cluster_last_reset = now
            except Exception as e:
                send_message(f"⚠️ Cluster WS error: {e}")
                await asyncio.sleep(5)

# 💰 Моніторинг закриття угод
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
            except:
                pass
        await asyncio.sleep(60)

# 📬 Webhook від TradingView
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
        decision = ask_gpt_trade_with_all_context(signal, news, oi, delta, volume)
        send_message(f"🤖 GPT вирішив: {decision}")
        log_to_sheet("GPT_DECISION", "", "", "", "", "", f"{signal} → {decision}")
        if decision in ["LONG", "BOOSTED_LONG"]:
            place_long("BTCUSDT", TRADE_USD_AMOUNT)
        elif decision in ["SHORT", "BOOSTED_SHORT"]:
            place_short("BTCUSDT", TRADE_USD_AMOUNT)
        return {"ok": True}
    except Exception as e:
        send_message(f"❌ Webhook error: {e}")
        return {"error": str(e)}

# 🚀 Запуск FastAPI + моніторів
if __name__ == "__main__":
    import uvicorn

    def start_cluster():
        asyncio.run(monitor_cluster_trades())

    def start_closures():
        asyncio.run(monitor_closures())

    threading.Thread(target=start_cluster).start()
    threading.Thread(target=start_closures).start()

    port = int(os.environ.get("PORT", 10000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
