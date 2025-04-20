# main_13.py
# 💡 Версія: GPT Memory + Clusters + AutoAnalyze + Whale + Telegram Core
# Комбінує logіку з main_12.py і main_full_with_clusters.py

# ✳️ Починаємо з імпорту, ENV, клієнтів, FastAPI
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

# 🔌 Clients
binance_client = Client(api_key=BINANCE_API_KEY, api_secret=BINANCE_SECRET_KEY)
client = OpenAI(api_key=OPENAI_API_KEY)
last_open_interest = None

# 📬 Telegram
def send_message(text: str):
    try:
        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", data={"chat_id": CHAT_ID, "text": text})
    except:
        pass

# 📈 Далі — Market utils, Google Sheets, кластерна памʼять та GPT аналіз — у наступній частині...
 main_13.py
# 💡 Версія: GPT Memory + Clusters + AutoAnalyze + Whale + Telegram Core
# Комбінує logіку з main_12.py і main_full_with_clusters.py

# ✳️ Починаємо з імпорту, ENV, клієнтів, FastAPI
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

# 🔌 Clients
binance_client = Client(api_key=BINANCE_API_KEY, api_secret=BINANCE_SECRET_KEY)
client = OpenAI(api_key=OPENAI_API_KEY)
last_open_interest = None

# 📬 Telegram
def send_message(text: str):
    try:
        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", data={"chat_id": CHAT_ID, "text": text})
    except:
        pass

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
    except:
        send_message("❌ Quantity error")
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
    except:
        send_message("❌ VWAP error")
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
# main_13.py
# 💡 Версія: GPT Memory + Clusters + AutoAnalyze + Whale + Telegram Core
# Комбінує logіку з main_12.py і main_full_with_clusters.py

# ✳️ Починаємо з імпорту, ENV, клієнтів, FastAPI
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

# 🔌 Clients
binance_client = Client(api_key=BINANCE_API_KEY, api_secret=BINANCE_SECRET_KEY)
client = OpenAI(api_key=OPENAI_API_KEY)
last_open_interest = None

# 📬 Telegram
def send_message(text: str):
    try:
        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", data={"chat_id": CHAT_ID, "text": text})
    except:
        pass

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
    except:
        send_message("❌ Quantity error")
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
    except:
        send_message("❌ VWAP error")
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

# 📊 Cluster storage (bucket size 10$)
CLUSTER_BUCKET_SIZE = 10
CLUSTER_INTERVAL = 60  # сек
cluster_data = defaultdict(lambda: {"buy": 0.0, "sell": 0.0})
cluster_last_reset = time.time()

# 🧠 GPT памʼять (помилки)
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
        # 🧠 GPT памʼять (помилки)
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

# 📈 GPT статистика та серія перемог
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

# 🧠 GPT аналіз із контекстом
def ask_gpt_trade_with_all_context(type_, news, oi, delta, volume):
    recent_trades, win_streak = get_recent_trades_and_streak()
    stats_summary = get_stats_summary()
    clusters = get_cluster_snapshot()
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

Кластери останньої хвилини:
{clusters}

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

# 📘 GPT пояснення угод + лог у Learning Log
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
# ✅ Готово: GPT памʼять, пояснення, кластер-контекст. Далі — логіка трейдингу, WebSocket, webhook...

# 📈 Кластер WebSocket
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

# 📈 Торгова логіка
trailing_stops = {"LONG": None, "SHORT": None}

def has_open_position(side):
    try:
        positions = binance_client.futures_position_information(symbol="BTCUSDT")
        pos = next((p for p in positions if p["positionSide"] == side), None)
        return pos and float(pos["positionAmt"]) != 0
    except:
        return False

def place_long(symbol, usd):
    if has_open_position("LONG"):
        send_message("⚠️ Уже відкрита LONG позиція")
        return
    try:
        entry = float(binance_client.futures_mark_price(symbol=symbol)["markPrice"])
        qty = get_quantity(symbol, usd)
        tp = round(entry * 1.015, 2)
        sl = round(entry * 0.992, 2)
        binance_client.futures_create_order(symbol=symbol, side='BUY', type='MARKET', quantity=qty, positionSide='LONG')
        binance_client.futures_create_order(symbol=symbol, side='SELL', type='TAKE_PROFIT_MARKET', stopPrice=tp, closePosition=True, timeInForce="GTC", positionSide='LONG')
        binance_client.futures_create_order(symbol=symbol, side='SELL', type='STOP_MARKET', stopPrice=sl, closePosition=True, timeInForce="GTC", positionSide='LONG')
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
# 🛡 Трейлінг стоп
async def monitor_trailing_stops():
    while True:
        try:
            for side in ["LONG", "SHORT"]:
                pos = next((p for p in binance_client.futures_position_information(symbol="BTCUSDT")
                            if p["positionSide"] == side), None)
                if pos and float(pos["positionAmt"]) != 0:
                    entry = float(pos["entryPrice"])
                    mark = float(binance_client.futures_mark_price(symbol="BTCUSDT")["markPrice"])
                    profit_pct = (mark - entry) / entry * 100 if side == "LONG" else (entry - mark) / entry * 100

                    if profit_pct >= 0.5 and not trailing_stops[side]:
                        trailing_stops[side] = entry
                        send_message(f"🛡 {side}: Стоп у беззбиток")

                    if trailing_stops[side] and profit_pct >= 1.0:
                        new_stop = round(entry * (1 + (profit_pct - 1) / 100), 2) if side == "LONG" else round(entry * (1 - (profit_pct - 1) / 100), 2)
                        trailing_stops[side] = new_stop
                        send_message(f"🔁 {side}: Новий трейлінг-стоп {new_stop}")
        except:
            pass
        await asyncio.sleep(15)

# 💰 Моніторинг закриття угод
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
                explanation = explain_trade_outcome(type_, result, pnl or "0")
                log_learning_entry(type_, result, explanation, pnl)
                break
    except Exception as e:
        send_message(f"❌ Update result error: {e}")

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
# 📬 Webhook для прийому сигналів із TradingView
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

# 🚀 Запуск FastAPI + потоків
if __name__ == "__main__":
    import uvicorn

    def start_cluster():
        asyncio.run(monitor_cluster_trades())

    def start_trailing():
        asyncio.run(monitor_trailing_stops())

    def start_closures():
        asyncio.run(monitor_closures())

    threading.Thread(target=start_cluster).start()
    threading.Thread(target=start_trailing).start()
    threading.Thread(target=start_closures).start()

    port = int(os.environ.get("PORT", 10000))
    uvicorn.run("main_13:app", host="0.0.0.0", port=port)
