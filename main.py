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
# 🔁 Cooldown між входами (щоб не спамити)
last_trade_time = 0
cached_oi = None
cached_volume = None
cached_vwap = None
COOLDOWN_SECONDS = 90
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

# 🔧 Додані відсутні змінні та функції
trailing_stops = {"LONG": None, "SHORT": None}
cluster_data = defaultdict(lambda: {"buy": 0, "sell": 0})
cluster_last_reset = time.time()
cluster_is_processing = False
last_ws_restart_time = 0  # ⏰ час останнього перепідключення WebSocket
CLUSTER_BUCKET_SIZE = 10  # $10 діапазон
CLUSTER_INTERVAL = 10  # кожні 10 сек оновлення

def get_quantity(symbol, usd):
    try:
        price = float(binance_client.futures_mark_price(symbol=symbol)["markPrice"])
        return round(usd / price, 3) if price > 0 else None
    except Exception as e:
        send_message(f"❌ Quantity error: {e}")
        return None

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
        streaks = {}

        for row in rows:
            if len(row) < 7:
                continue
            gpt_type = row[1]
            result = row[6].strip().upper()
            if gpt_type not in stats:
                stats[gpt_type] = {"WIN": 0, "LOSS": 0}
                streaks[gpt_type] = {"current": 0, "max": 0}

            if result == "WIN":
                stats[gpt_type]["WIN"] += 1
                streaks[gpt_type]["current"] += 1
                if streaks[gpt_type]["current"] > streaks[gpt_type]["max"]:
                    streaks[gpt_type]["max"] = streaks[gpt_type]["current"]
            elif result == "LOSS":
                stats[gpt_type]["LOSS"] += 1
                streaks[gpt_type]["current"] = 0

        stat_rows = [["Type", "WIN", "LOSS", "Total", "Winrate %", "Max Streak"]]
        for k, v in stats.items():
            total = v["WIN"] + v["LOSS"]
            winrate = round(v["WIN"] / total * 100, 2) if total > 0 else 0
            max_streak = streaks[k]["max"]
            stat_rows.append([k, v["WIN"], v["LOSS"], total, winrate, max_streak])

        try:
            stat_sheet = sh.worksheet("Stats")
            stat_sheet.clear()
        except:
            stat_sheet = sh.add_worksheet(title="Stats", rows="20", cols="6")

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
def get_candle_summary(symbol="BTCUSDT", interval="1m", limit=5):
    try:
        candles = binance_client.futures_klines(symbol=symbol, interval=interval, limit=limit)
        summary = []
        for c in candles:
            open_, high, low, close = map(float, [c[1], c[2], c[3], c[4]])
            direction = "🟢" if close > open_ else "🔴"
            body = abs(close - open_)
            wick = (high - low) - body
            if wick > body * 1.5:
                shape = "🐍 хвіст"
            elif body > wick * 2:
                shape = "🚀 імпульс"
            else:
                shape = "💤 звичайна"
            summary.append(f"{direction} {shape} (від {round(open_, 1)} до {round(close, 1)})")
        return "\n".join(summary)
    except Exception as e:
        send_message(f"❌ Candle summary error: {e}")
        return "⚠️ Дані свічок недоступні"
def get_orderbook_snapshot(symbol="BTCUSDT", depth=50):
    try:
        depth_data = binance_client.futures_order_book(symbol=symbol, limit=depth)
        bids = depth_data["bids"]
        asks = depth_data["asks"]

        max_bid = max(float(b[1]) for b in bids)
        max_ask = max(float(a[1]) for a in asks)

        bid_wall = next((b for b in bids if float(b[1]) > max_bid * 0.7), None)
        ask_wall = next((a for a in asks if float(a[1]) > max_ask * 0.7), None)

        text = ""
        if ask_wall:
            text += f"🟥 Sell wall: {ask_wall[0]} ({round(float(ask_wall[1]), 1)} BTC)\n"
        if bid_wall:
            text += f"🟦 Buy wall: {bid_wall[0]} ({round(float(bid_wall[1]), 1)} BTC)\n"

        return text.strip() or "⚠️ Стін не знайдено"
    except Exception as e:
        send_message(f"❌ Orderbook error: {e}")
        return "⚠️ Дані про стіни недоступні"

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
def round_safe(value, digits=1):
    try:
        return round(value, digits)
    except:
        return "невідомо"

def analyze_candle_gpt(candle, vwap, cluster_buy, cluster_sell, support_level=None, resistance_level=None):
    try:
        open_, high, low, close, volume = map(float, [
            candle["open"], candle["high"], candle["low"], candle["close"], candle["volume"]
        ])
        body = abs(close - open_)
        wick = (high - low) - body
        tail_ratio = round(wick / body, 2) if body else 0
        direction = "🟢" if close > open_ else "🔴"

        if wick > body * 1.5:
            shape = "🐍 хвіст"
        elif body > wick * 2:
            shape = "🚀 імпульс"
        else:
            shape = "💤 звичайна"

        is_near_support = bool(support_level and abs(close - support_level) / close < 0.002)
        is_near_resistance = bool(resistance_level and abs(close - resistance_level) / close < 0.002)

        support_text = "🟦 Біля підтримки" if is_near_support else ""
        resistance_text = "🟥 Біля опору" if is_near_resistance else ""

        prompt = f"""
Свічка BTCUSDT (1 хв):
- Напрям: {direction} {shape} ({round(open_, 1)} → {round(close, 1)})
- Обʼєм: ${round(volume):,}
- Кластери: buy ${round(cluster_buy):,}, sell ${round(cluster_sell):,}
- VWAP: {round_safe(vwap)}, close: {round_safe(close)}
- Tail/body ratio: {tail_ratio}
- {support_text}
- {resistance_text}

Вибери одне:
SKIP — нічого не робити  
NORMAL — можливо, але не впевнено  
BOOSTED — потужний імпульс

Відповідь строго у форматі: SKIP / NORMAL / BOOSTED — і коротке пояснення.
"""

        response = client.chat.completions.create(
            model="gpt-4-turbo",
            messages=[
                {"role": "system", "content": "Ти досвідчений трейдинг-аналітик. Відповідай лише одним із слів: SKIP / NORMAL / BOOSTED. Додай коротке пояснення."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
        )

        reply = response.choices[0].message.content.strip()
        decision = reply.split()[0].upper()

        if decision not in ["SKIP", "NORMAL", "BOOSTED"]:
            decision = "SKIP"
            reply = f"SKIP — невідома відповідь від GPT: {reply}"

        return {
            "decision": decision,
            "reason": reply
        }

    except Exception as e:
        return {
            "decision": "SKIP",
            "reason": f"GPT error: {e}"
        }

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
        sh = gclient.open_by_key(GOOGLE_SHEET_ID)
        try:
            sheet = sh.worksheet("Learning Log")
        except:
            # Якщо листа немає — створюємо його з заголовками
            sheet = sh.add_worksheet(title="Learning Log", rows="1000", cols="10")
            sheet.append_row(["Time", "Type", "Result", "PnL", "GPT Analysis"])
            return "❕ Помилки ще не зафіксовані."

        data = sheet.get_all_values()[1:]
        mistakes = [row for row in reversed(data) if len(row) >= 5 and row[2].strip().upper() == "LOSS" and row[4].strip()]
        return "\n".join(f"- {row[4]}" for row in mistakes[:limit]) or "❕ Немає нещодавніх помилок."
    except Exception as e:
        send_message(f"❌ Mistakes fallback error: {e}")
        return "❕ GPT тимчасово без памʼяті."
    
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
async def ask_gpt_trade_with_all_context(type_, news, oi, delta, volume):
    try:
        recent_trades, win_streak = get_recent_trades_and_streak()
        stats_summary = get_stats_summary()
        mistakes = get_recent_mistakes()

        type_upper = type_.upper()

        if is_flat_zone("BTCUSDT") and "BOOSTED" not in type_upper and (volume is None or volume < 100):
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

        res = await asyncio.to_thread(
            client.chat.completions.create,
            model="gpt-4-turbo",
            messages=[
                {"role": "system", "content": (
                    "Ти досвідчений скальп-трейдер. "
                    "Вибери лише одне слово з цього списку: LONG, BOOSTED_LONG, SHORT, BOOSTED_SHORT або SKIP. "
                    "Не додавай пояснень. Не пояснюй свій вибір. Відповідай строго лише одним словом.")},
                {"role": "user", "content": prompt}
            ]
        )

        gpt_answer = res.choices[0].message.content.strip()
        send_message(f"📤 GPT: {gpt_answer}")
        return gpt_answer

    except Exception as e:
        send_message(f"❌ GPT error: {e}")
        return "SKIP"
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
        except Exception:
            sheet = sh.add_worksheet(title="Learning Log", rows="1000", cols="10")
            sheet.append_row(["Time", "Type", "Result", "PnL", "GPT Analysis"])

        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        row = [now, trade_type, result, pnl or "", reason]
        sheet.append_row(row)
    except Exception as e:
        send_message(f"❌ Learning Log error: {e}")

        
def has_open_position(side):
    try:
        positions = binance_client.futures_position_information(symbol="BTCUSDT")
        for p in positions:
            qty = float(p["positionAmt"])
            if side == "LONG" and qty > 0:
                return True
            elif side == "SHORT" and qty < 0:
                return True
        return False  # ✅ тільки після перевірки всіх позицій
    except Exception as e:
        send_message(f"❌ Position check error: {e}")
        return False

def get_current_position_qty(side):
    try:
        positions = binance_client.futures_position_information(symbol="BTCUSDT")
        for p in positions:
            amt = float(p["positionAmt"])
            if side == "LONG" and amt > 0:
                return amt
            elif side == "SHORT" and amt < 0:
                return abs(amt)
        return 0
    except Exception as e:
        send_message(f"❌ Position qty error: {e}")
        return 0


# 🔁 Перевірка cooldown між входами
def is_cooldown_passed():
    global last_trade_time
    now = time.time()
    if now - last_trade_time >= COOLDOWN_SECONDS:
        last_trade_time = now
        return True
    return False

# 🧰 Утиліта для скасування старих STOP-ордерів
def cancel_existing_stop_order(side):
    try:
        orders = binance_client.futures_get_open_orders(symbol="BTCUSDT")
        for o in orders:
            if o["type"] == "STOP_MARKET" and o["positionSide"] == side:
                binance_client.futures_cancel_order(symbol="BTCUSDT", orderId=o["orderId"])
    except Exception as e:
        send_message(f"❌ Cancel stop error ({side}): {e}")

def place_long(symbol, usd):
    if has_open_position("SHORT"):
        qty_to_close = get_current_position_qty("SHORT")
        if qty_to_close > 0:
            if not DRY_RUN:
                try:   
                    cancel_existing_stop_order("SHORT")
                    binance_client.futures_create_order(
                        symbol=symbol,
                        side='BUY',
                        type='MARKET',
                        quantity=qty_to_close,
                        reduceOnly=True,
                        positionSide='SHORT'
                    )
                    send_message("🔁 Закрито SHORT перед LONG")
                except Exception as e:
                    send_message(f"⚠️ Не вдалося закрити SHORT перед LONG: {e} — продовжуємо")

                    # 🔁 Повертаємо STOP назад на SHORT
                    try:
                        entry = float(binance_client.futures_mark_price(symbol=symbol)["markPrice"])
                        sl = round(entry * 1.005, 2)
                        cancel_existing_stop_order("SHORT")
                        binance_client.futures_create_order(
                            symbol=symbol,
                            side='BUY',
                            type='STOP_MARKET',
                            stopPrice=sl,
                            closePosition=True,
                            timeInForce="GTC",
                            positionSide='SHORT'
                        )
                        send_message(f"🛡 Повернено SL для SHORT на {sl}")
                    except Exception as sl_e:
                        send_message(f"⚠️ Не вдалося повернути SL для SHORT: {sl_e}")
                    return
        else:
            send_message("⚠️ SHORT позиція вже закрита — не надсилаємо reduceOnly")

    if has_open_position("LONG"):
        send_message("⚠️ Уже відкрита LONG позиція")
        return


    try:
        entry = float(binance_client.futures_mark_price(symbol=symbol)["markPrice"])
        qty = get_quantity(symbol, usd)
        if not qty:
            send_message("❌ Не вдалося розрахувати кількість")
            return

        tp = round(entry * 1.009, 2)
        sl = round(entry * 0.995, 2)

        cancel_existing_stop_order("LONG")

        if DRY_RUN:
            send_message(f"🤖 [DRY_RUN] LONG\n📍 Entry: {entry}\n📦 Qty: {qty}\n🎯 TP: {tp}\n🛡 SL: {sl}")
        else:
            binance_client.futures_create_order(symbol=symbol, side='BUY', type='MARKET', quantity=qty, positionSide='LONG')
            binance_client.futures_create_order(
                symbol=symbol, side='SELL', type='TAKE_PROFIT_MARKET',
                stopPrice=tp, closePosition=True, timeInForce="GTC", positionSide='LONG'
            )
            binance_client.futures_create_order(
                symbol=symbol, side='SELL', type='STOP_MARKET',
                stopPrice=sl, closePosition=True, timeInForce="GTC", positionSide='LONG'
            )
            send_message(f"🟢 LONG OPEN\n📍 Entry: {entry}\n📦 Qty: {qty}\n🎯 TP: {tp}\n🛡 SL: {sl}")

        log_to_sheet("LONG", entry, tp, sl, qty, None, "GPT сигнал")
        update_stats_sheet()

    except Exception as e:
        send_message(f"❌ Binance LONG error: {e}")

def place_short(symbol, usd):
    if has_open_position("LONG"):
        qty_to_close = get_current_position_qty("LONG")
        if qty_to_close > 0:
            if not DRY_RUN:
                try:   
                    cancel_existing_stop_order("LONG")
                    binance_client.futures_create_order(
                        symbol=symbol,
                        side='SELL',
                        type='MARKET',
                        quantity=qty_to_close,
                        reduceOnly=True,
                        positionSide='LONG'
                    )
                    send_message("🔁 Закрито LONG перед SHORT")
                except Exception as e:
                    send_message(f"⚠️ Не вдалося закрити LONG перед SHORT: {e} — продовжуємо")

                    # 🔁 Повертаємо STOP назад на LONG
                    try:
                        entry = float(binance_client.futures_mark_price(symbol=symbol)["markPrice"])
                        sl = round(entry * 0.995, 2)
                        cancel_existing_stop_order("LONG")
                        binance_client.futures_create_order(
                            symbol=symbol,
                            side='SELL',
                            type='STOP_MARKET',
                            stopPrice=sl,
                            closePosition=True,
                            timeInForce="GTC",
                            positionSide='LONG'
                        )
                        send_message(f"🛡 Повернено SL для LONG на {sl}")
                    except Exception as sl_e:
                        send_message(f"⚠️ Не вдалося повернути SL для LONG: {sl_e}")
                    return
        else:
            send_message("⚠️ LONG позиція вже закрита — не надсилаємо reduceOnly")

    if has_open_position("SHORT"):
        send_message("⚠️ Уже відкрита SHORT позиція")
        return


    try:
        entry = float(binance_client.futures_mark_price(symbol=symbol)["markPrice"])
        qty = get_quantity(symbol, usd)
        if not qty:
            send_message("❌ Не вдалося розрахувати кількість")
            return

        tp = round(entry * 0.991, 2)
        sl = round(entry * 1.005, 2)

        cancel_existing_stop_order("SHORT")

        if DRY_RUN:
            send_message(f"🤖 [DRY_RUN] SHORT\n📍 Entry: {entry}\n📦 Qty: {qty}\n🎯 TP: {tp}\n🛡 SL: {sl}")
        else:
            binance_client.futures_create_order(symbol=symbol, side='SELL', type='MARKET', quantity=qty, positionSide='SHORT')
            binance_client.futures_create_order(
                symbol=symbol, side='BUY', type='TAKE_PROFIT_MARKET',
                stopPrice=tp, closePosition=True, timeInForce="GTC", positionSide='SHORT'
            )
            binance_client.futures_create_order(
                symbol=symbol, side='BUY', type='STOP_MARKET',
                stopPrice=sl, closePosition=True, timeInForce="GTC", positionSide='SHORT'
            )
            send_message(f"🔴 SHORT OPEN\n📍 Entry: {entry}\n📦 Qty: {qty}\n🎯 TP: {tp}\n🛡 SL: {sl}")

        log_to_sheet("SHORT", entry, tp, sl, qty, None, "GPT сигнал")
        update_stats_sheet()

    except Exception as e:
        send_message(f"❌ Binance SHORT error: {e}")
        
        # ✅ Перед cluster-аналізом або поруч
async def monitor_market_cache():
    global cached_vwap, cached_volume, cached_oi
    while True:
        try:
            cached_vwap = calculate_vwap("BTCUSDT")
            cached_volume = get_volume("BTCUSDT")
            cached_oi = get_open_interest("BTCUSDT")
        except Exception as e:
            send_message(f"❌ Cache update error: {e}")
        await asyncio.sleep(10)
async def ping_loop(ws):
    while True:
        try:
            await ws.ping()
            print(f"📡 Ping sent: {datetime.utcnow().isoformat()}")
            await asyncio.sleep(20)
        except Exception as e:
            send_message(f"⚠️ Ping loop stopped: {e}")
            break

async def monitor_cluster_trades():
    global cluster_last_reset, cluster_is_processing
    uri = "wss://fstream.binance.com/ws/btcusdt@aggTrade"

    while True:
        try:
            async with websockets.connect(uri) as websocket:
                asyncio.create_task(ping_loop(websocket))

                last_impulse = {"side": None, "volume": 0, "timestamp": 0}
                trade_buffer = []
                buffer_duration = 5  # секунд

                while True:
                    try:
                        msg_raw = await asyncio.wait_for(websocket.recv(), timeout=10)
                        msg = json.loads(msg_raw)
                        await asyncio.sleep(0.01)
                        price = float(msg['p'])
                        qty = float(msg['q'])
                        is_sell = msg['m']
                        timestamp = time.time()

                        trade_buffer.append({
                            "price": price,
                            "qty": qty,
                            "is_sell": is_sell,
                            "timestamp": timestamp
                        })

                        trade_buffer = [t for t in trade_buffer if timestamp - t["timestamp"] <= buffer_duration]

                        bucket = round(price / CLUSTER_BUCKET_SIZE) * CLUSTER_BUCKET_SIZE
                        if is_sell:
                            cluster_data[bucket]['sell'] += qty
                        else:
                            cluster_data[bucket]['buy'] += qty

                        await asyncio.sleep(0)
                        
                        # Примусовий перезапуск WebSocket кожні 10 хв
                        if time.time() - cluster_last_reset > 600:
                           raise Exception("🔁 Manual WS restart to prevent timeout")



                        now = time.time()
                        if now - cluster_last_reset >= CLUSTER_INTERVAL and not cluster_is_processing:
                            cluster_is_processing = True
                            
                            strongest_bucket = max(cluster_data.items(), key=lambda x: x[1]["buy"] + x[1]["sell"])
                            total_buy = strongest_bucket[1]["buy"]
                            total_sell = strongest_bucket[1]["sell"]

                            candles = binance_client.futures_klines(symbol="BTCUSDT", interval="1m", limit=1)
                            last_candle = candles[-1]
                            candle_dict = {
                                "open": last_candle[1],
                                "high": last_candle[2],
                                "low": last_candle[3],
                                "close": last_candle[4],
                                "volume": last_candle[5]
                            }
                            vwap_now = cached_vwap

                            gpt_candle_result = analyze_candle_gpt(
                                candle=candle_dict,
                                vwap=vwap_now,
                                cluster_buy=total_buy,
                                cluster_sell=total_sell
                            )

                            if gpt_candle_result["decision"] == "SKIP":
                                cluster_data.clear()
                                cluster_last_reset = time.time()
                                cluster_is_processing = False
                                continue

                            buy_volume = sum(t["qty"] for t in trade_buffer if not t["is_sell"])
                            sell_volume = sum(t["qty"] for t in trade_buffer if t["is_sell"])
                            buy_ratio = (buy_volume / (buy_volume + sell_volume)) * 100 if (buy_volume + sell_volume) > 0 else 0
                            sell_ratio = 100 - buy_ratio

                            signal = None
                            if buy_ratio >= 90 and total_buy >= 80:
                                signal = "SUPER_BOOSTED_LONG"
                            elif sell_ratio >= 90 and total_sell >= 80:
                                signal = "SUPER_BOOSTED_SHORT"
                            elif total_buy >= 65:
                                signal = "BOOSTED_LONG"
                            elif total_sell >= 65:
                                signal = "BOOSTED_SHORT"

                            if signal is None and (total_buy > 40 or total_sell > 40):
                                send_message(
                                    f"📊 Кластер {strongest_bucket[0]} → Buy: {round(total_buy)}, Sell: {round(total_sell)} | Не BOOSTED"
                                )
                            if total_sell > total_buy and total_sell >= 45:
                                signal = "BOOSTED_SHORT"
                            elif total_buy > total_sell and total_buy >= 45:
                                signal = "BOOSTED_LONG"

                            if (
                                signal is not None and (
                                    (signal.startswith("LONG") and has_open_position("LONG")) or
                                    (signal.startswith("SHORT") and has_open_position("SHORT"))
                                )
                            ):
                                cluster_data.clear()
                                cluster_last_reset = time.time()
                                cluster_is_processing = False
                                continue

                            if (
                                signal is not None and
                                last_impulse["side"] == "BUY" and signal.startswith("SHORT") and
                                last_impulse["volume"] >= 60 and now - last_impulse["timestamp"] < 30
                            ):
                                send_message("⏳ Відхилено SHORT — щойно був великий BUY")
                                signal = None

                            elif (
                                signal is not None and
                                last_impulse["side"] == "SELL" and signal.startswith("LONG") and
                                last_impulse["volume"] >= 60 and now - last_impulse["timestamp"] < 30
                            ):
                                send_message("⏳ Відхилено LONG — щойно був великий SELL")
                                signal = None

                            if signal in ["BOOSTED_LONG", "SUPER_BOOSTED_LONG"]:
                                last_impulse = {"side": "BUY", "volume": total_buy, "timestamp": now}
                            elif signal in ["BOOSTED_SHORT", "SUPER_BOOSTED_SHORT"]:
                                last_impulse = {"side": "SELL", "volume": total_sell, "timestamp": now}

                            if signal:
                                news = get_latest_news()
                                oi = cached_oi
                                volume = cached_volume

                                cluster_direction_info = f"Кластерний напрям: Buy {buy_ratio:.1f}%, Sell {sell_ratio:.1f}%"

                                candles = get_candle_summary("BTCUSDT")
                                walls = get_orderbook_snapshot("BTCUSDT")
                                
                                if not is_cooldown_passed():
                                   send_message("⏳ Пропущено GPT-аналіз — cooldown не минув")
                                   cluster_data.clear()
                                   cluster_last_reset = time.time()
                                   cluster_is_processing = False
                                   continue

                                decision = await ask_gpt_trade_with_all_context(
                                    signal,
                                    f"{cluster_direction_info}\n\nСвічки:\n{candles}\n\nСтіни:\n{walls}\n\n{news}",
                                    oi, 0, volume
                                )

                                send_message(f"💥 {signal} — кластер {strongest_bucket[0]} | Buy: {round(total_buy)}, Sell: {round(total_sell)}")
                                send_message(f"🤖 GPT кластер: {decision} | {cluster_direction_info}")

                                if "SUPER" in signal:
                                    send_message(f"🚀 {signal} кластер: домінація {'BUY' if 'LONG' in signal else 'SELL'} {round(max(buy_ratio, sell_ratio))}%")

                                if decision in ["LONG", "BOOSTED_LONG", "SUPER_BOOSTED_LONG"]:
                                    if is_cooldown_passed():
                                        await asyncio.to_thread(place_long, "BTCUSDT", TRADE_USD_AMOUNT)
                                    else:
                                        send_message("⏳ Пропущено LONG — cooldown не минув")

                                if decision in ["SHORT", "BOOSTED_SHORT", "SUPER_BOOSTED_SHORT"]:
                                    if is_cooldown_passed():
                                        await asyncio.to_thread(place_short, "BTCUSDT", TRADE_USD_AMOUNT)
                                    else:
                                        send_message("⏳ Пропущено SHORT — cooldown не минув")

                           while True:
                              try:
                                 async with websockets.connect(uri) as websocket:
                                     asyncio.create_task(ping_loop(websocket))
                                     ...
                             except Exception as e:
                                 send_message(f"⚠️ Cluster WS reconnecting: {e}")
                                 await asyncio.sleep(5)
                        




            
# 📬 Webhook для TradingView

@app.post("/webhook")
async def webhook(req: Request):
    global last_open_interest
    try:
        data = await req.json()
        signal = data.get("message", "").strip().upper()
        
        if signal == "/debug_activity":
            text = get_gpt_debug_activity_today()
            send_message(text)
            return {"ok": True}

        send_message(f"📩 Отримано сигнал: {signal}")

        if signal not in ["LONG", "SHORT", "BOOSTED_LONG", "BOOSTED_SHORT"]:
            send_message(f"⚠️ Невідомий сигнал: {signal}")
            return {"error": "Invalid signal"}

        oi = cached_oi
        volume = cached_volume
        news = get_latest_news()
        if not oi or not volume:
           send_message("⚠️ Дані кешу ще не прогріті — пропущено webhook.")
           return {"error": "Cache not ready"}


        delta = ((oi - last_open_interest) / last_open_interest) * 100 if last_open_interest and oi else 0
        last_open_interest = oi

        send_message(f"📊 OI: {oi:,.0f} | Volume: {volume} | ΔOI: {delta:.2f}%")

        decision = await ask_gpt_trade_with_all_context(signal, news, oi, delta, volume)
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
        # 🧠 Основний цикл перевірки трейлінг-стопів
async def monitor_trailing_stops():
    while True:
        try:
            for side in ["LONG", "SHORT"]:
                positions = binance_client.futures_position_information(symbol="BTCUSDT")
                pos = next((p for p in positions if
                            ((side == "LONG" and float(p["positionAmt"]) > 0) or
                             (side == "SHORT" and float(p["positionAmt"]) < 0))), None)

                if pos:
                    entry = float(pos["entryPrice"])
                    qty = abs(float(pos["positionAmt"]))
                    mark = float(binance_client.futures_mark_price(symbol="BTCUSDT")["markPrice"])
                    profit_pct = (mark - entry) / entry * 100 if side == "LONG" else (entry - mark) / entry * 100

                    new_sl = None
                    if profit_pct >= 0.8:
                        new_sl = round(entry * (1 + 0.005 if side == "LONG" else 1 - 0.005), 2)
                    elif profit_pct >= 0.5:
                        new_sl = round(entry * (1 + 0.003 if side == "LONG" else 1 - 0.003), 2)
                    elif profit_pct >= 0.3:
                        new_sl = round(entry * (1 - 0.001 if side == "LONG" else 1 + 0.001), 2)

                    if new_sl:
                        if (
                            trailing_stops[side] is None or
                            (side == "LONG" and new_sl > trailing_stops[side]) or
                            (side == "SHORT" and new_sl < trailing_stops[side])
                        ):
                            trailing_stops[side] = new_sl
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

                    if profit_pct >= 0.9 and qty >= 0.0002:
                        qty_close = round(qty * 0.8, 4)
                        qty_remain = round(qty - qty_close, 4)

                        binance_client.futures_create_order(
                            symbol="BTCUSDT",
                            side='SELL' if side == "LONG" else 'BUY',
                            type='MARKET',
                            quantity=qty_close,
                            positionSide=side
                        )

                        breakeven_sl = round(entry * (1 + 0.005 if side == "LONG" else 1 - 0.005), 2)
                        cancel_existing_stop_order(side)
                        binance_client.futures_create_order(
                            symbol="BTCUSDT",
                            side='SELL' if side == "LONG" else 'BUY',
                            type='STOP_MARKET',
                            stopPrice=breakeven_sl,
                            quantity=qty_remain,
                            timeInForce="GTC",
                            positionSide=side
                        )
                        send_message(f"🛡 Стоп на залишок {qty_remain} поставлено на {breakeven_sl}")

        except Exception as e:
            send_message(f"⚠️ Trailing error: {e}")

        await asyncio.sleep(10)

# 🚀 Запуск FastAPI + кластер + трейлінг + автоаналіз

# ✅ Запуск моніторів GPT при старті FastAPI
# 🤖 Автоматичний аналіз без сигналу (щохвилини)
async def monitor_auto_signals():
    global last_open_interest, cached_oi, cached_volume
    while True:
        try:
            oi = cached_oi
            volume = cached_volume
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

            decision = await ask_gpt_trade_with_all_context(signal, news, oi, delta, volume)  
            send_message(f"🤖 GPT (auto): {decision} на базі delta {delta:.2f}%")

            if decision in ["LONG", "BOOSTED_LONG"]:
                await asyncio.to_thread(place_long, "BTCUSDT", TRADE_USD_AMOUNT)
            elif decision in ["SHORT", "BOOSTED_SHORT"]:
                await asyncio.to_thread(place_short, "BTCUSDT", TRADE_USD_AMOUNT)

        except Exception as e:
            send_message(f"❌ Auto-signal error: {e}")

        await asyncio.sleep(60)

@app.on_event("startup")
async def start_all_monitors():
    try:
        asyncio.create_task(monitor_market_cache())
        asyncio.create_task(monitor_cluster_trades())
        asyncio.create_task(monitor_trailing_stops())
        asyncio.create_task(monitor_auto_signals())
        asyncio.create_task(monitor_closures())
        send_message("✅ GPT монітори запущено успішно.")
    except Exception as e:
        send_message(f"❌ Помилка при запуску GPT-моніторів: {e}")
