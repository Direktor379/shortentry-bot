# 🔐 ENV і запуск FastAPI
from fastapi import FastAPI, Request
import os
from dotenv import load_dotenv
import requests
from datetime import datetime
from openai import OpenAI
from binance.client import Client
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import asyncio
import json
import websockets
import threading
import time
from collections import defaultdict

# 🌍 Завантаження змінних середовища
load_dotenv()
app = FastAPI()

@app.get("/")
async def healthcheck():
    return {"status": "running"}

# 🔐 Змінні оточення
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
NEWS_API_KEY = os.getenv("NEWS_API_KEY")
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
BINANCE_SECRET_KEY = os.getenv("BINANCE_SECRET_KEY")
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
TRADE_USD_AMOUNT = float(os.getenv("TRADE_USD_AMOUNT", 1000))
DRY_RUN = os.getenv("DRY_RUN", "false").lower() == "true"  # 🧪 режим тесту

# 🔌 Ініціалізація клієнтів
binance_client = Client(api_key=BINANCE_API_KEY, api_secret=BINANCE_SECRET_KEY)
client = OpenAI(api_key=OPENAI_API_KEY)
last_open_interest = None

# 📬 Відправка повідомлень у Telegram
def send_message(text: str):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        data = {"chat_id": CHAT_ID, "text": text}
        requests.post(url, data=data)
    except Exception as e:
        print(f"Telegram error: {e}")  # <-- тут закінчується функція

# 📊 Запис у Google Sheets
def log_to_sheet(type_, entry, tp, sl, qty, result=None, comment=""):
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name("/etc/secrets/credentials.json", scope)
        gclient = gspread.authorize(creds)
        sheet = gclient.open_by_key(GOOGLE_SHEET_ID).worksheets()[0]
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        row = [now, type_, entry, tp, sl, qty, result or "", comment]
        sheet.append_row(row, value_input_option='RAW')
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
            if len(data[i]) >= 7 and data[i][1] == type_ and data[i][6] == "":
                sheet.update_cell(i + 1, 7, result)
                if pnl is not None:
                    sheet.update_cell(i + 1, 8, f"{pnl} USDT")
                break
    except Exception as e:
        send_message(f"❌ Update result error: {e}")

def update_stats_sheet():
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name("/etc/secrets/credentials.json", scope)
        gclient = gspread.authorize(creds)
        sh = gclient.open_by_key(GOOGLE_SHEET_ID)
        data = sh.worksheets()[0].get_all_values()
        rows = data[1:]

        stats = {}
        for row in rows:
            if len(row) < 7:
                continue
            gpt_type = row[1]
            result = row[6].strip().upper()
            if gpt_type not in stats:
                stats[gpt_type] = {"WIN": 0, "LOSS": 0}
            if result == "WIN":
                stats[gpt_type]["WIN"] += 1
            elif result == "LOSS":
                stats[gpt_type]["LOSS"] += 1

        stat_rows = [["Type", "WIN", "LOSS", "Total", "Winrate %"]]
        for k, v in stats.items():
            total = v["WIN"] + v["LOSS"]
            winrate = round(v["WIN"] / total * 100, 2) if total > 0 else 0
            stat_rows.append([k, v["WIN"], v["LOSS"], total, winrate])

        try:
            stat_sheet = sh.worksheet("Stats")
            stat_sheet.clear()
        except:
            stat_sheet = sh.add_worksheet(title="Stats", rows="20", cols="5")

        stat_sheet.update("A1", stat_rows)
    except Exception as e:
        send_message(f"❌ Stats error: {e}")
def get_latest_news():
    try:
        url = f"https://cryptopanic.com/api/v1/posts/?auth_token={NEWS_API_KEY}&filter=important"
        r = requests.get(url)
        news = r.json()
        return "\n".join([item["title"] for item in news.get("results", [])[:3]])
    except Exception as e:
        send_message(f"❌ News error: {e}")
        return "⚠️ Новини не вдалося завантажити."

def get_open_interest(symbol="BTCUSDT"):
    try:
        r = requests.get("https://fapi.binance.com/fapi/v1/openInterest", params={"symbol": symbol})
        return float(r.json()["openInterest"]) if r.ok else None
    except Exception as e:
        send_message(f"❌ OI error: {e}")
        return None

def get_volume(symbol="BTCUSDT"):
    try:
        data = binance_client.futures_klines(symbol=symbol, interval="1m", limit=1)
        return float(data[-1][7])
    except Exception as e:
        send_message(f"❌ Volume error: {e}")
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
    except Exception as e:
        send_message(f"❌ Flat zone error: {e}")
        return False
def get_gspread_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name("/etc/secrets/credentials.json", scope)
    return gspread.authorize(creds)

def get_last_trades(limit=10):
    try:
        gclient = get_gspread_client()
        sheet = gclient.open_by_key(GOOGLE_SHEET_ID).worksheets()[0]
        data = sheet.get_all_values()[1:]
        data.reverse()
        gpt_logs = [row for row in data if len(row) >= 7 and row[1] in ["LONG", "SHORT", "BOOSTED_LONG", "BOOSTED_SHORT"] and row[6]]
        recent = gpt_logs[:limit]
        return "\n".join(f"{i+1}. {row[1]} → {row[6]}" for i, row in enumerate(recent))
    except Exception as e:
        send_message(f"❌ Last trades error: {e}")
        return ""

def get_stats_summary():
    try:
        gclient = get_gspread_client()
        sheet = gclient.open_by_key(GOOGLE_SHEET_ID).worksheet("Stats")
        data = sheet.get_all_values()[1:]
        lines = [f"{row[0]}: {row[4]}%" for row in data if len(row) >= 5]
        return "\n".join(lines)
    except Exception as e:
        send_message(f"❌ Stats summary error: {e}")
        return "Немає статистики"

def get_recent_mistakes(limit=5):
    try:
        gclient = get_gspread_client()
        sheet = gclient.open_by_key(GOOGLE_SHEET_ID).worksheet("Learning Log")
        data = sheet.get_all_values()[1:]
        mistakes = [row for row in reversed(data) if len(row) >= 5 and row[2].strip().upper() == "LOSS" and row[4].strip()]
        return "\n".join(f"- {row[4]}" for row in mistakes[:limit])
    except Exception as e:
        send_message(f"❌ Mistakes error: {e}")
        return ""

def get_recent_trades_and_streak(limit=10):
    try:
        gclient = get_gspread_client()
        sheet = gclient.open_by_key(GOOGLE_SHEET_ID).worksheets()[0]
        data = sheet.get_all_values()[1:]
        data.reverse()
        trades = [row for row in data if len(row) >= 7 and row[1] in ["LONG", "SHORT", "BOOSTED_LONG", "BOOSTED_SHORT"] and row[6]]
        recent = trades[:limit]
        formatted = [f"{i+1}. {row[1]} → {row[6]}" for i, row in enumerate(recent)]
        streak = 0
        for row in trades:
            if row[6].strip().upper() == "WIN":
                streak += 1
            else:
                break
        return "\n".join(formatted), streak
    except Exception as e:
        send_message(f"❌ Streak error: {e}")
        return "", 0
def ask_gpt_trade_with_all_context(type_, news, oi, delta, volume):
    try:
        recent_trades, win_streak = get_recent_trades_and_streak()
        stats_summary = get_stats_summary()
        mistakes = get_recent_mistakes()

        type_upper = type_.upper()

        # Захист від флету + низького обʼєму (крім BOOSTED)
        if is_flat_zone("BTCUSDT") and "BOOSTED" not in type_upper and (volume is None or volume < 300):
            return "SKIP"

        oi_text = f"{oi:,.0f}" if oi is not None else "невідомо"
        delta_text = f"{delta:.2f}%" if delta is not None else "невідомо"

        prompt = f"""
GPT минулі сигнали:
{recent_trades}

Winrate по типах:
{stats_summary}

Серія перемог: {win_streak}/5

Попередні помилки:
{mistakes}

Сигнал: {type_upper}
Обʼєм за 1 хв: {volume}
Open Interest: {oi_text}
Зміна OI: {delta_text}
Новини:
{news}

Ціль: досягти 5 перемог поспіль. Прийми зважене рішення.
❗️ Обери одне з:
- LONG / BOOSTED_LONG / SHORT / BOOSTED_SHORT / SKIP
"""

        res = client.chat.completions.create(
            model="gpt-4-turbo",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Ти досвідчений скальп-трейдер. "
                        "Вибери лише одне слово з цього списку: LONG, BOOSTED_LONG, SHORT, BOOSTED_SHORT або SKIP. "
                        "Не додавай пояснень. Не пояснюй свій вибір. Відповідай строго лише одним словом."
                    )
                },
                {"role": "user", "content": prompt}
            ]
        )

        gpt_answer = res.choices[0].message.content.strip()
        send_message(f"📤 GPT: {gpt_answer}")
        return gpt_answer

    except Exception as e:
        send_message(f"❌ GPT error: {e}")
        return "SKIP"
# 📒 Learning Log — пояснення втрат і логування GPT

def get_gspread_client():
    try:
        scope = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive"
        ]
        creds = ServiceAccountCredentials.from_json_keyfile_name(
            "/etc/secrets/credentials.json", scope
        )
        return gspread.authorize(creds)
    except Exception as e:
        send_message(f"❌ GSpread auth error: {e}")
        return None

def explain_trade_outcome(trade_type, result, pnl):
    try:
        prompt = f"""
Тип угоди: {trade_type}
Результат: {result}
PnL: {pnl}

Поясни коротко (1 реченням), чому результат був таким. Якщо була помилка — вкажи її.
"""
        res = client.chat.completions.create(   
            model="gpt-4-turbo",
            messages=[
                {"role": "system", "content": "Ти трейдинг-аналітик. Поясни, чому угода завершилась з таким результатом. Відповідь має бути короткою, по суті."},
                {"role": "user", "content": prompt}
            ]
        )
        return res.choices[0].message.content.strip()
    except Exception as e:
        send_message(f"❌ GPT (explain_trade) error: {e}")
        return "Не вдалося отримати пояснення від GPT."

def log_learning_entry(trade_type, result, reason, pnl=None):
    try:
        gclient = get_gspread_client()
        if not gclient:
            return

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
# 📡 Кластерна логіка: bucket'и по $10 і імпульс на 5 секундах

CLUSTER_BUCKET_SIZE = 10
CLUSTER_INTERVAL = 60  # перевірка раз на 60 сек
cluster_data = defaultdict(lambda: {"buy": 0.0, "sell": 0.0})
cluster_last_reset = time.time()
cluster_is_processing = False  # захист від дублів

async def monitor_cluster_trades():
    global cluster_last_reset, cluster_is_processing
    uri = "wss://fstream.binance.com/ws/btcusdt@aggTrade"
    async with websockets.connect(uri) as websocket:
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
                if now - cluster_last_reset >= CLUSTER_INTERVAL and not cluster_is_processing:
                    cluster_is_processing = True  # блокуємо повтори

                    # Фіксуємо імпульс
                    strongest_bucket = max(cluster_data.items(), key=lambda x: x[1]["buy"] + x[1]["sell"])
                    total_buy = strongest_bucket[1]["buy"]
                    total_sell = strongest_bucket[1]["sell"]
                    total = total_buy + total_sell

                    signal = None
                    if total_buy >= 1000:
                    signal = "BOOSTED_LONG"
                    elif total_sell >= 1000:
                    signal = "BOOSTED_SHORT"

# 📊 Логуємо потужні кластери, які не стали BOOSTED
                    if signal is None and (total_buy > 300 or total_sell > 300):
                    send_message(f"📊 Кластер {strongest_bucket[0]} → Buy: {round(total_buy)}, Sell: {round(total_sell)} | Не BOOSTED (поріг: 1000)")

                        signal = "BOOSTED_SHORT"

                    if signal:
                        news = get_latest_news()
                        oi = get_open_interest("BTCUSDT")
                        volume = get_volume("BTCUSDT")
                        decision = await ask_gpt_trade_with_all_context(signal, news, oi, 0, volume)

                        send_message(f"💥 {signal} — кластер {strongest_bucket[0]} | Buy: {round(total_buy)}, Sell: {round(total_sell)}")
                        send_message(f"🤖 GPT кластер: {decision}")

                        if decision in ["LONG", "BOOSTED_LONG"]:
                            await asyncio.to_thread(place_long, "BTCUSDT", TRADE_USD_AMOUNT)
                        elif decision in ["SHORT", "BOOSTED_SHORT"]:
                            await asyncio.to_thread(place_short, "BTCUSDT", TRADE_USD_AMOUNT)

                    cluster_data.clear()
                    cluster_last_reset = now
                    cluster_is_processing = False  # розблокування

            except Exception as e:
                send_message(f"⚠️ Cluster WS error: {e}")
                await asyncio.sleep(5)
# 📈 Торгівля: відкриття LONG/SHORT з DRY_RUN та перевірками

def has_open_position(side):
    try:
        positions = binance_client.futures_position_information(symbol="BTCUSDT")
        for p in positions:
            amt = float(p["positionAmt"])
            if side == "LONG" and amt > 0:
                return True
            if side == "SHORT" and amt < 0:
                return True
        return False
    except Exception as e:
        send_message(f"❌ Position check error: {e}")
        return False

def get_quantity(symbol, usd_amount):
    try:
        mark_price = float(binance_client.futures_mark_price(symbol=symbol)["markPrice"])
        return round(usd_amount / mark_price, 3)  # округлення до 0.001 BTC
    except Exception as e:
        send_message(f"❌ Quantity calc error: {e}")
        return None

def place_long(symbol, usd):
    if has_open_position("LONG"):
        send_message("⚠️ Уже відкрита LONG позиція")
        return

    try:
        entry = float(binance_client.futures_mark_price(symbol=symbol)["markPrice"])
        qty = get_quantity(symbol, usd)
        if not qty:
            send_message("❌ Не вдалося розрахувати кількість")
            return

        tp = round(entry * 1.015, 2)
        sl = round(entry * 0.992, 2)

        if DRY_RUN:
            send_message(f"🤖 [DRY_RUN] LONG\n📍 Entry: {entry}\n📦 Qty: {qty}\n🎯 TP: {tp}\n🛡 SL: {sl}")
        else:
            binance_client.futures_create_order(
                symbol=symbol, side='BUY', type='MARKET', quantity=qty, positionSide='LONG')
            binance_client.futures_create_order(
                symbol=symbol, side='SELL', type='TAKE_PROFIT_MARKET',
                stopPrice=tp, closePosition=True, timeInForce="GTC", positionSide='LONG')
            binance_client.futures_create_order(
                symbol=symbol, side='SELL', type='STOP_MARKET',
                stopPrice=sl, closePosition=True, timeInForce="GTC", positionSide='LONG')

            send_message(f"🟢 LONG OPEN\n📍 Entry: {entry}\n📦 Qty: {qty}\n🎯 TP: {tp}\n🛡 SL: {sl}")

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
        if not qty:
            send_message("❌ Не вдалося розрахувати кількість")
            return

        tp = round(entry * 0.99, 2)
        sl = round(entry * 1.008, 2)

        if DRY_RUN:
            send_message(f"🤖 [DRY_RUN] SHORT\n📍 Entry: {entry}\n📦 Qty: {qty}\n🎯 TP: {tp}\n🛡 SL: {sl}")
        else:
            binance_client.futures_create_order(
                symbol=symbol, side='SELL', type='MARKET', quantity=qty, positionSide='SHORT')
            binance_client.futures_create_order(
                symbol=symbol, side='BUY', type='TAKE_PROFIT_MARKET',
                stopPrice=tp, closePosition=True, timeInForce="GTC", positionSide='SHORT')
            binance_client.futures_create_order(
                symbol=symbol, side='BUY', type='STOP_MARKET',
                stopPrice=sl, closePosition=True, timeInForce="GTC", positionSide='SHORT')

            send_message(f"🔴 SHORT OPEN\n📍 Entry: {entry}\n📦 Qty: {qty}\n🎯 TP: {tp}\n🛡 SL: {sl}")

        log_to_sheet("SHORT", entry, tp, sl, qty, None, "GPT сигнал")
        update_stats_sheet()

    except Exception as e:
        send_message(f"❌ Binance SHORT error: {e}")
# 🔁 Трейлінг-стоп логіка

trailing_stops = {"LONG": None, "SHORT": None}

# 🧰 Утиліта для скасування старих STOP-ордерів
def cancel_existing_stop_order(side):
    try:
        orders = binance_client.futures_get_open_orders(symbol="BTCUSDT")  # перевірено
        for o in orders:
            if o["type"] == "STOP_MARKET" and o["positionSide"] == side:
                binance_client.futures_cancel_order(symbol="BTCUSDT", orderId=o["orderId"])
    except Exception as e:
        send_message(f"❌ Cancel stop error ({side}): {e}")

# 🧠 Основний цикл перевірки трейлінг-стопів
async def monitor_trailing_stops():
    while True:
        try:
            for side in ["LONG", "SHORT"]:
                pos = next((p for p in binance_client.futures_position_information(symbol="BTCUSDT")
                            if float(p["positionAmt"]) != 0 and
                               ((side == "LONG" and float(p["positionAmt"]) > 0) or
                                (side == "SHORT" and float(p["positionAmt"]) < 0))), None)

                if pos:
                    entry = float(pos["entryPrice"])
                    mark = float(binance_client.futures_mark_price(symbol="BTCUSDT")["markPrice"])
                    profit_pct = (mark - entry) / entry * 100 if side == "LONG" else (entry - mark) / entry * 100

                    # Стоп у беззбиток при +0.5%
                    if profit_pct >= 0.5 and trailing_stops[side] is None:
                        new_sl = round(entry, 2)
                        trailing_stops[side] = new_sl
                        send_message(f"🛡 {side}: Стоп у беззбитку {new_sl} (+{profit_pct:.2f}%)")

                        if not DRY_RUN:
                            cancel_existing_stop_order(side)
                            binance_client.futures_create_order(
                                symbol="BTCUSDT",
                                side='SELL' if side == "LONG" else 'BUY',
                                type='STOP_MARKET',
                                stopPrice=new_sl,
                                closePosition=True,
                                timeInForce="GTC",
                                positionSide=side
                            )

                    # Трейлінг при +1.0% і більше
                    if trailing_stops[side] and profit_pct >= 1.0:
                        new_sl = (
                            round(entry * (1 + (profit_pct - 1) / 100), 2)
                            if side == "LONG"
                            else round(entry * (1 - (profit_pct - 1) / 100), 2)
                        )

                        if new_sl != trailing_stops[side]:
                            trailing_stops[side] = new_sl
                            send_message(f"🔁 {side}: Новий трейлінг-стоп {new_sl} (+{profit_pct:.2f}%)")

                            if not DRY_RUN:
                                cancel_existing_stop_order(side)
                                binance_client.futures_create_order(
                                    symbol="BTCUSDT",
                                    side='SELL' if side == "LONG" else 'BUY',
                                    type='STOP_MARKET',
                                    stopPrice=new_sl,
                                    closePosition=True,
                                    timeInForce="GTC",
                                    positionSide=side
                                )

        except Exception as e:
            send_message(f"⚠️ Trailing error: {e}")

        await asyncio.sleep(15)
# 🤖 Автоматичний аналіз без сигналу (щохвилини)

async def monitor_auto_signals():
    global last_open_interest
    while True:
        try:
            oi = get_open_interest("BTCUSDT")
            volume = get_volume("BTCUSDT")
            news = get_latest_news()

            if not oi or not volume:
                await asyncio.sleep(60)
                continue

            delta = ((oi - last_open_interest) / last_open_interest) * 100 if last_open_interest else 0
            last_open_interest = oi

            # Генеруємо базовий сигнал
            if delta > 0.2:
                signal = "LONG"
            elif delta < -0.2:
                signal = "SHORT"
            else:
                signal = None

            if not signal:
                await asyncio.sleep(60)
                continue

            decision = ask_gpt_trade_with_all_context(...)  
            send_message(f"🤖 GPT (auto): {decision} на базі delta {delta:.2f}%")

            if decision in ["LONG", "BOOSTED_LONG"]:
                await asyncio.to_thread(place_long, "BTCUSDT", TRADE_USD_AMOUNT)
            elif decision in ["SHORT", "BOOSTED_SHORT"]:
                await asyncio.to_thread(place_short, "BTCUSDT", TRADE_USD_AMOUNT)

        except Exception as e:
            send_message(f"❌ Auto-signal error: {e}")

        await asyncio.sleep(60)
# 📬 Webhook для TradingView

@app.post("/webhook")
async def webhook(req: Request):
    global last_open_interest
    try:
        data = await req.json()
        signal = data.get("message", "").strip().upper()
        send_message(f"📩 Отримано сигнал: {signal}")

        if signal not in ["LONG", "SHORT", "BOOSTED_LONG", "BOOSTED_SHORT"]:
            send_message(f"⚠️ Невідомий сигнал: {signal}")
            return {"error": "Invalid signal"}

        oi = get_open_interest("BTCUSDT")
        volume = get_volume("BTCUSDT")
        news = get_latest_news()

        delta = ((oi - last_open_interest) / last_open_interest) * 100 if last_open_interest and oi else 0
        last_open_interest = oi

        send_message(f"📊 OI: {oi:,.0f} | Volume: {volume} | ΔOI: {delta:.2f}%")

        decision = ask_gpt_trade_with_all_context(signal, news, oi, delta, volume)
        send_message(f"🤖 GPT вирішив: {decision}")

        if decision in ["LONG", "BOOSTED_LONG"]:
            await asyncio.to_thread(place_long, "BTCUSDT", TRADE_USD_AMOUNT)
        elif decision in ["SHORT", "BOOSTED_SHORT"]:
            await asyncio.to_thread(place_short, "BTCUSDT", TRADE_USD_AMOUNT)

        return {"ok": True}
    except Exception as e:
        send_message(f"❌ Webhook error: {e}")
        return {"error": str(e)}
# 💰 Моніторинг закриття позицій + GPT пояснення

closed_positions_handled = set()

async def monitor_closures():
    while True:
        try:
            for side in ["LONG", "SHORT"]:
                positions = binance_client.futures_position_information(symbol="BTCUSDT")
                pos = next((p for p in positions if
                            float(p["positionAmt"]) == 0 and
                            ((side == "LONG" and float(p["entryPrice"]) > 0) or
                             (side == "SHORT" and float(p["entryPrice"]) > 0))), None)

                if pos:
                    pos_id = f"{side}-{pos['updateTime']}"
                    if pos_id in closed_positions_handled:
                        continue
                    closed_positions_handled.add(pos_id)

                    entry = float(pos["entryPrice"])
                    mark = float(binance_client.futures_mark_price(symbol="BTCUSDT")["markPrice"])

                    if entry == 0:
                        continue  # захист від ділення на 0

                    pnl = round((mark - entry) * 1000, 2) if side == "LONG" else round((entry - mark) * 1000, 2)
                    result = "WIN" if pnl > 0 else "LOSS"

                    update_result_in_sheet(side, result, f"{pnl:+.2f}")

                    # GPT пояснення при LOSS
                    if result == "LOSS":
                        reason = explain_trade_outcome(side, result, pnl)
                        log_learning_entry(side, result, reason, pnl)
                        send_message(f"🧠 GPT пояснення збитку:\n{reason}")

                    # Обмеження на розмір set
                    if len(closed_positions_handled) > 100:
                        closed_positions_handled.clear()

        except Exception as e:
            send_message(f"⚠️ Closure check error: {e}")

        await asyncio.sleep(60)
# 🚀 Запуск FastAPI + кластер + трейлінг + автоаналіз

if __name__ == "__main__":
    import uvicorn

    def start_cluster():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(monitor_cluster_trades())

    def start_trailing():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(monitor_trailing_stops())

    def start_auto_signals():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(monitor_auto_signals())

    # Запускаємо всі фонові процеси
    threading.Thread(target=start_cluster).start()
    threading.Thread(target=start_trailing).start()
    threading.Thread(target=start_auto_signals).start()

    # Запускаємо FastAPI сервер
    port = int(os.getenv("PORT", 10000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)

