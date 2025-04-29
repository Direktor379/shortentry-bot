# ⚙️ ScalpGPT Pro — повна версія з трейлінгом, кластером, памʼяттю та GPT-аналізом

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
import time
from collections import defaultdict

# 🌍 Завантаження змінних середовища
load_dotenv()
app = FastAPI()

@app.get("/")
async def healthcheck():
    return {"status": "running"}
# 🛠️ CONFIG — централізовані налаштування
CONFIG = {
    "COOLDOWN_SECONDS": 90,
    "TRADE_AMOUNT_USD": float(os.getenv("TRADE_USD_AMOUNT", 300)),
    "SYMBOL": os.getenv("TRADE_SYMBOL", "BTCUSDT"),

    # Кластери
    "CLUSTER_BUCKET_SIZE": 10,
    "CLUSTER_INTERVAL": 10,
    "BOOST_THRESHOLD": 65,
    "SUPER_BOOST_RATIO": 90,
    "SUPER_BOOST_VOLUME": 80,
    "MIN_CLUSTER_ALERT": 40,
    "ALT_BOOST_THRESHOLD": 45,
    "RECENT_IMPULSE_TIMEOUT": 30,
    "IMPULSE_VOLUME_MIN": 60,

    # Трейлінг + тейк-профіт/стоп-лосс
    "TP_SL": {
        "LONG": {"TP": 1.009, "SL": 0.995},
        "SHORT": {"TP": 0.991, "SL": 1.005}
    },
    "TRAILING_LEVELS": {
        "0.3":  -0.001,
        "0.5":   0.003,
        "0.8":   0.005
    },
    "PARTIAL_CLOSE_AT": 0.9,
    "PARTIAL_CLOSE_SIZE": 0.8,
    "BREAKEVEN_SL_OFFSET": 0.005
}
# 🔐 Змінні середовища
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
NEWS_API_KEY = os.getenv("NEWS_API_KEY")
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
BINANCE_SECRET_KEY = os.getenv("BINANCE_SECRET_KEY")
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
DRY_RUN = os.getenv("DRY_RUN", "false").lower() == "true"

# 🔌 Ініціалізація клієнтів
binance_client = Client(api_key=BINANCE_API_KEY, api_secret=BINANCE_SECRET_KEY)
client = OpenAI(api_key=OPENAI_API_KEY)
# 🔍 Перевірка наявності важливих ENV-змінних
def check_env_variables():
    required_vars = [
        "BOT_TOKEN", "CHAT_ID", "OPENAI_API_KEY",
        "BINANCE_API_KEY", "BINANCE_SECRET_KEY", "GOOGLE_SHEET_ID"
    ]
    missing = [var for var in required_vars if not os.getenv(var)]
    if missing:
        raise EnvironmentError(f"❌ Відсутні обовʼязкові змінні середовища: {', '.join(missing)}")

# 🔄 Скидання runtime-змінних (на випадок перезапуску)
def init_runtime_state():
    global last_trade_time, cached_oi, cached_volume, cached_vwap, last_open_interest
    global trailing_stops, cluster_data, cluster_last_reset, cluster_is_processing, last_ws_restart_time
    global open_position_lock

    open_position_lock = asyncio.Lock()
    last_trade_time = 0
    cached_oi = None
    cached_volume = None
    cached_vwap = None
    last_open_interest = None
    trailing_stops = {"LONG": None, "SHORT": None}
    cluster_data = defaultdict(lambda: {"buy": 0, "sell": 0})
    cluster_last_reset = time.time()
    cluster_is_processing = False
    last_ws_restart_time = 0

# 🔖 Глобальні змінні для відстеження стін
last_bid_wall: float = 0.0
last_ask_wall: float = 0.0
fake_wall_detected: bool = False


# 📬 Відправка повідомлення у Telegram
def send_message(text: str):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        data = {"chat_id": CHAT_ID, "text": text}
        requests.post(url, data=data)
    except Exception as e:
        print(f"Telegram error: {e}")

# 📊 Логування угоди в Google Sheets
def log_to_sheet(type_, entry, tp, sl, qty, result=None, comment=""):
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name("/etc/secrets/credentials.json", scope)
        gclient = gspread.authorize(creds)
        sheet = gclient.open_by_key(GOOGLE_SHEET_ID).worksheets()[0]
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        row = [now, type_, entry, tp, sl, qty, result or "", comment]

        # Додаємо retry логіку
        retries = 3
        for attempt in range(retries):
            try:
                sheet.append_row(row, value_input_option='RAW')
                break  # Якщо успішно, виходимо
            except Exception as e:
                if attempt < retries - 1:
                    time.sleep(2)  # Затримка перед наступною спробою
                else:
                    raise e  # Якщо остання спроба - кидаємо помилку

    except Exception as e:
        send_message(f"❌ Sheets error: {e}")


# 📈 Оновлення результату угоди у Google Sheets
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

# 📊 Оновлення вкладки "Stats" у Google Sheets
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

# 📜 Отримання останніх угод
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

# 📈 Отримання статистики по winrate
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

# 🧠 Отримання останніх помилок GPT
def get_recent_mistakes(limit=5):
    try:
        gclient = get_gspread_client()
        sh = gclient.open_by_key(GOOGLE_SHEET_ID)
        try:
            sheet = sh.worksheet("Learning Log")
        except:
            sheet = sh.add_worksheet(title="Learning Log", rows="1000", cols="10")
            sheet.append_row(["Time", "Type", "Result", "PnL", "GPT Analysis"])
            return "❕ Помилки ще не зафіксовані."

        data = sheet.get_all_values()[1:]
        mistakes = [row for row in reversed(data) if len(row) >= 5 and row[2].strip().upper() == "LOSS" and row[4].strip()]
        return "\n".join(f"- {row[4]}" for row in mistakes[:limit]) or "❕ Немає нещодавніх помилок."
    except Exception as e:
        send_message(f"❌ Mistakes fallback error: {e}")
        return "❕ GPT тимчасово без памʼяті."
        # 📊 Отримання Winrate по кожному типу з вкладки Stats
def get_global_stats() -> dict:
    """
    Зчитує Winrate по кожному типу з Google Sheets → вкладка 'Stats'
    Повертає словник {"LONG": 68.0, "SHORT": 43.5, ...}
    """
    try:
        sh = get_gspread_client().open_by_key(GOOGLE_SHEET_ID)
        sheet = sh.worksheet("Stats")
        rows = sheet.get_all_values()[1:]  # пропускаємо заголовок

        result: dict = {}
        for row in rows:
            type_: str = row[0].strip().upper()
            winrate: float = float(row[4]) if row[4] else 0.0
            result[type_] = winrate
        return result
    except Exception as e:
        send_message(f"❌ Не вдалося зчитати Stats: {e}")
        return {}

# 🧠 Запит до GPT на базі повного контексту
async def ask_gpt_trade_with_all_context(type_, news, oi, delta, volume):
    try:
        recent_trades, win_streak = get_recent_trades_and_streak()
        stats_summary = get_stats_summary()
        mistakes = get_recent_mistakes()
        # 📊 Winrate по типах з таблиці Stats
        global_stats = get_global_stats()
        long_wr = global_stats.get("LONG", 0.0)
        short_wr = global_stats.get("SHORT", 0.0)

        # 🧱 Дані по стінах ордербука
        buy_wall = round(current_buy_wall, 1) if current_buy_wall else "немає"
        sell_wall = round(current_sell_wall, 1) if current_sell_wall else "немає"


        type_upper = type_.upper()

        # 📊 Показники дельти обʼєму
        buy_ratio = round(current_buy_ratio, 2) if current_buy_ratio is not None else 50.0
        sell_ratio = round(current_sell_ratio, 2) if current_sell_ratio is not None else 50.0

        # Фільтрація флетових зон без BOOSTED сигналів
        if is_flat_zone("BTCUSDT") and "BOOSTED" not in type_upper and (volume is None or volume < 100):
            return "SKIP"
            # 📋 Автоматичне SKIP при недостатньому перекосі дельти
            if buy_ratio < 62 and sell_ratio < 62:
                send_message(f"⚪ Дельта обʼєму слабка (Buy {buy_ratio}% / Sell {sell_ratio}%) — пропускаємо сигнал.")
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

Стіни у стакані:
Buy wall: {buy_wall}
Sell wall: {sell_wall}

Дельта обʼєму:
Buy Ratio: {buy_ratio}%
Sell Ratio: {sell_ratio}%

Winrate по глобальній статистиці:
LONG: {long_wr}%
SHORT: {short_wr}%


Ціль: досягти 5 перемог поспіль. Прийми зважене рішення.
❗️ Обери одне з:
- LONG / BOOSTED_LONG / SHORT / BOOSTED_SHORT / SKIP
"""

        res = await asyncio.to_thread(
            lambda: client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": (
                        "Ти досвідчений скальп-трейдер. "
                        "Вибери лише одне слово з цього списку: LONG, BOOSTED_LONG, SHORT, BOOSTED_SHORT або SKIP. "
                        "Не додавай пояснень. Відповідай тільки одним словом."
                    )},
                    {"role": "user", "content": prompt}
                ]
            )
        )
        

        gpt_answer = res.choices[0].message.content.strip()
        send_message(f"📤 GPT: {gpt_answer}")
        return gpt_answer

    except Exception as e:
        send_message(f"❌ GPT error: {e}")
        return "SKIP"

# 🧠 Підрахунок останніх угод і серії перемог
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
# 📈 Отримання Open Interest
def get_open_interest(symbol="BTCUSDT"):
    try:
        r = requests.get("https://fapi.binance.com/fapi/v1/openInterest", params={"symbol": symbol})
        return float(r.json()["openInterest"]) if r.ok else None
    except Exception as e:
        send_message(f"❌ OI error: {e}")
        return None
# 📰 Отримання останніх новин з CryptoPanic
def get_latest_news():
    try:
        url = f"https://cryptopanic.com/api/v1/posts/?auth_token={NEWS_API_KEY}&filter=important"
        r = requests.get(url)
        news = r.json()
        return "\n".join([item["title"] for item in news.get("results", [])[:3]])
    except Exception as e:
        send_message(f"❌ News error: {e}")
        return "⚠️ Новини не вдалося завантажити."

# 📊 Отримання обʼєму торгів за хвилину
def get_volume(symbol="BTCUSDT"):
    try:
        data = binance_client.futures_klines(symbol=symbol, interval="1m", limit=1)
        return float(data[-1][7])
    except Exception as e:
        send_message(f"❌ Volume error: {e}")
        return None

# 📏 Розрахунок VWAP з обробкою помилок
def calculate_vwap(symbol="BTCUSDT", interval="1m", limit=20):
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


# 💤 Визначення флет-зони (чи рух занадто слабкий)
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
# 🟢 Безпечне округлення (щоб уникнути краху GPT на None)
def round_safe(value, digits=1):
    try:
        return round(value, digits)
    except:
        return "невідомо"
# ♻️ Фонове оновлення кешу ринку (OI, volume, VWAP)
async def monitor_market_cache():
    global cached_vwap, cached_volume, cached_oi
    while True:
        try:
            new_vwap = calculate_vwap("BTCUSDT")
            new_volume = get_volume("BTCUSDT")
            new_oi = get_open_interest("BTCUSDT")

            # Перевірка на None
            if new_vwap is not None and new_volume is not None and new_oi is not None:
                cached_vwap = new_vwap
                cached_volume = new_volume
                cached_oi = new_oi
            else:
                send_message("⚠️ Попередження: Не вдалося оновити кеш ринку (VWAP, Volume або OI)")

        except Exception as e:
            send_message(f"❌ Cache update error: {e}")

        await asyncio.sleep(10)

        # 🕯️ Отримання короткого опису останніх 5 свічок
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

# 🧠 Аналіз останніх 5 свічок + кластерів + VWAP → GPT рішення
async def analyze_candle_gpt(vwap, cluster_buy, cluster_sell):
    try:
        # 🕯️ Завантаження останніх 5 свічок
        candles_raw = binance_client.futures_klines(symbol="BTCUSDT", interval="1m", limit=5)
        candles = []
        for c in candles_raw:
            candles.append({
                "open": c[1],
                "high": c[2],
                "low": c[3],
                "close": c[4],
                "volume": c[5]
            })

        summaries = []
        for candle in candles:
            open_, high, low, close, volume = map(float, [
                candle["open"], candle["high"], candle["low"], candle["close"], candle["volume"]
            ])
            body = abs(close - open_)
            wick = (high - low) - body
            direction = "🟢" if close > open_ else "🔴"

            if wick > body * 1.5:
                shape = "🐍 хвіст"
            elif body > wick * 2:
                shape = "🚀 імпульс"
            else:
                shape = "💤 звичайна"

            summaries.append(f"{direction} {shape} ({round(open_, 1)} → {round(close, 1)}) обʼєм ${round(volume):,}")

        candles_text = "\n".join(summaries)

        prompt = f"""
Останні 5 свічок BTCUSDT (1м):
{candles_text}

Кластери:
- Buy: ${round(cluster_buy):,}
- Sell: ${round(cluster_sell):,}
VWAP: {round(vwap, 2) if vwap else "невідомо"}

Оціни загальну ситуацію:
- Чи є імпульс або хвиля?
- Чи переважає якийсь напрямок?

Вибери одне:
SKIP — нічого не робити  
NORMAL — можливий вхід, але не дуже сильний  
BOOSTED — потужний імпульс, сильний рух

Відповідь строго у форматі: SKIP / NORMAL / BOOSTED — і коротке пояснення.
"""

        response = await asyncio.to_thread(
            lambda: client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": (
                        "Ти професійний скальпер. "
                        "Вибери тільки одне: SKIP / NORMAL / BOOSTED. Додай дуже коротке пояснення."
                    )},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3
            )
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

# 🧱 Отримання snapshot order book (стіни покупців і продавців)
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
# 📡 Моніторинг кластерів через WebSocket
# 🔁 Перевірка чи пройшов cooldown
def is_cooldown_ready():
    now = time.time()
    return now - last_trade_time >= CONFIG["COOLDOWN_SECONDS"]

# ⏳ Оновлення cooldown таймера
def update_cooldown():
    global last_trade_time
    last_trade_time = time.time()

# 📈 Отримання кількості відкритої позиції
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

# 🧹 Перевірка чи є відкрита позиція
def has_open_position(side):
    try:
        positions = binance_client.futures_position_information(symbol="BTCUSDT")
        for p in positions:
            qty = float(p["positionAmt"])
            if side == "LONG" and qty > 0:
                return True
            elif side == "SHORT" and qty < 0:
                return True
        return False
    except Exception as e:
        send_message(f"❌ Position check error: {e}")
        return False

# 📡 Основний моніторинг кластерних сигналів
async def monitor_cluster_trades():
    global cluster_last_reset, cluster_is_processing, last_ws_error_time, last_skip_message_time

    uri_list = [
        "wss://fstream.binance.com/ws/btcusdt@aggTrade",
        "wss://fstream1.binance.com/ws/btcusdt@aggTrade",
        "wss://fstream2.binance.com/ws/btcusdt@aggTrade"
    ]
    current_uri_index = 0

    reconnect_delay = 5
    error_counter = 0
    last_skip_message_time = 0

    while True:
        try:
            uri = uri_list[current_uri_index]
            async with websockets.connect(uri, ping_interval=None) as websocket:
                send_message(f"✅ Підключено до WebSocket: {uri}")
                reconnect_delay = 5
                error_counter = 0

                last_impulse = {"side": None, "volume": 0, "timestamp": 0}
                trade_buffer = []
                buffer_duration = 5

                while True:
                    msg_raw = await websocket.recv()
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

                    bucket = round(price / CONFIG["CLUSTER_BUCKET_SIZE"]) * CONFIG["CLUSTER_BUCKET_SIZE"]
                    if is_sell:
                        cluster_data[bucket]['sell'] += qty
                    else:
                        cluster_data[bucket]['buy'] += qty

                    now = time.time()

                    if now - cluster_last_reset >= CONFIG["CLUSTER_INTERVAL"] and not cluster_is_processing:
                        cluster_is_processing = True

                        strongest_bucket = max(cluster_data.items(), key=lambda x: x[1]["buy"] + x[1]["sell"])
                        total_buy = strongest_bucket[1]["buy"]
                        total_sell = strongest_bucket[1]["sell"]

                        gpt_candle_result = await analyze_candle_gpt(
                            vwap=cached_vwap,
                            cluster_buy=total_buy,
                            cluster_sell=total_sell
                        )

                        if gpt_candle_result["decision"] == "SKIP":
                            reason = gpt_candle_result.get("reason", "немає пояснення")
                            if now - last_skip_message_time > 300:
                                send_message(f"🚫 SKIP — {reason}")
                                last_skip_message_time = now

                            cluster_data.clear()
                            cluster_last_reset = now
                            cluster_is_processing = False
                            await asyncio.sleep(1)
                            continue

                        buy_volume = sum(t["qty"] for t in trade_buffer if not t["is_sell"])
                        sell_volume = sum(t["qty"] for t in trade_buffer if t["is_sell"])
                        buy_ratio = (buy_volume / (buy_volume + sell_volume)) * 100 if (buy_volume + sell_volume) > 0 else 0
                        sell_ratio = 100 - buy_ratio

                        signal = None
                        if buy_ratio >= CONFIG["SUPER_BOOST_RATIO"] and total_buy >= CONFIG["SUPER_BOOST_VOLUME"]:
                            signal = "SUPER_BOOSTED_LONG"
                        elif sell_ratio >= CONFIG["SUPER_BOOST_RATIO"] and total_sell >= CONFIG["SUPER_BOOST_VOLUME"]:
                            signal = "SUPER_BOOSTED_SHORT"
                        elif total_buy >= CONFIG["BOOST_THRESHOLD"]:
                            signal = "BOOSTED_LONG"
                        elif total_sell >= CONFIG["BOOST_THRESHOLD"]:
                            signal = "BOOSTED_SHORT"

                        if signal is None and (total_buy > CONFIG["MIN_CLUSTER_ALERT"] or total_sell > CONFIG["MIN_CLUSTER_ALERT"]):
                            send_message(f"📊 Кластер {strongest_bucket[0]} → Buy: {round(total_buy)}, Sell: {round(total_sell)} | Не BOOSTED")
                            if total_sell > total_buy and total_sell >= CONFIG["ALT_BOOST_THRESHOLD"]:
                                signal = "BOOSTED_SHORT"
                            elif total_buy > total_sell and total_buy >= CONFIG["ALT_BOOST_THRESHOLD"]:
                                signal = "BOOSTED_LONG"

                        if signal:
                            if last_impulse["side"] == "BUY" and signal.startswith("SHORT") and \
                               last_impulse["volume"] >= CONFIG["IMPULSE_VOLUME_MIN"] and now - last_impulse["timestamp"] < CONFIG["RECENT_IMPULSE_TIMEOUT"]:
                                send_message("⏳ Відхилено SHORT — щойно був великий BUY")
                                signal = None

                            if last_impulse["side"] == "SELL" and signal.startswith("LONG") and \
                               last_impulse["volume"] >= CONFIG["IMPULSE_VOLUME_MIN"] and now - last_impulse["timestamp"] < CONFIG["RECENT_IMPULSE_TIMEOUT"]:
                                send_message("⏳ Відхилено LONG — щойно був великий SELL")
                                signal = None

                            if signal:
                                if signal in ["BOOSTED_LONG", "SUPER_BOOSTED_LONG"]:
                                    last_impulse = {"side": "BUY", "volume": total_buy, "timestamp": now}
                                elif signal in ["BOOSTED_SHORT", "SUPER_BOOSTED_SHORT"]:
                                    last_impulse = {"side": "SELL", "volume": total_sell, "timestamp": now}

                                # 🔥 Фільтрація кластерів по обʼєму
                                if total_buy < 60 and total_sell < 60:
                                    send_message("⚪ Кластер має малий обʼєм — пропущено.")
                                    cluster_data.clear()
                                    cluster_last_reset = time.time()
                                    cluster_is_processing = False
                                    await asyncio.sleep(1)
                                    continue
                                    # 🚫 Якщо виявлено фейкову стіну — SKIP
                                    if fake_wall_detected:
                                        send_message("🚫 Сигнал пропущено через фейкову стіну.")
                                        cluster_data.clear()
                                        cluster_last_reset = time.time()
                                        cluster_is_processing = False
                                        fake_wall_detected = False  # скидаємо прапор
                                        await asyncio.sleep(1)
                                        continue



                                news = get_latest_news()
                                oi = cached_oi
                                volume = cached_volume
                                candles = get_candle_summary("BTCUSDT")
                                walls = get_orderbook_snapshot("BTCUSDT")
                                # 📈 Перевірка, чи є реальний рух після кластера
                                try:
                                    entry_price: float = float(binance_client.futures_mark_price(symbol="BTCUSDT")["markPrice"])
                                    await asyncio.sleep(5)  # даємо ринку 5 сек
                                    exit_price: float = float(binance_client.futures_mark_price(symbol="BTCUSDT")["markPrice"])
                                    price_change: float = (exit_price - entry_price) / entry_price * 100
                                
                                    if signal.startswith("LONG") and price_change < 0.05:
                                        send_message("⚪ LONG кластер без продовження руху — SKIP.")
                                        cluster_data.clear()
                                        cluster_last_reset = time.time()
                                        cluster_is_processing = False
                                        await asyncio.sleep(1)
                                        continue
                                
                                    if signal.startswith("SHORT") and price_change > -0.05:
                                        send_message("⚪ SHORT кластер без продовження руху — SKIP.")
                                        cluster_data.clear()
                                        cluster_last_reset = time.time()
                                        cluster_is_processing = False
                                        await asyncio.sleep(1)
                                        continue
                                
                                except Exception as e:
                                    send_message(f"❌ Помилка при перевірці руху після кластера: {e}")

                                decision = await ask_gpt_trade_with_all_context(
                                    signal,
                                    f"Кластери: Buy {buy_ratio:.1f}%, Sell {sell_ratio:.1f}%\n\nСвічки:\n{candles}\n\nСтіни:\n{walls}\n\n{news}",
                                    oi, 0, volume
                                )

                                send_message(f"💥 {signal} — кластер {strongest_bucket[0]} | Buy: {round(total_buy)}, Sell: {round(total_sell)}")
                                send_message(f"🤖 GPT кластер: {decision}")

                                if decision in ["LONG", "BOOSTED_LONG", "SUPER_BOOSTED_LONG"]:
                                    if not has_open_position("LONG") and is_cooldown_ready():
                                        await place_long("BTCUSDT", CONFIG["TRADE_AMOUNT_USD"])
                                        update_cooldown()
                                elif decision in ["SHORT", "BOOSTED_SHORT", "SUPER_BOOSTED_SHORT"]:
                                    if not has_open_position("SHORT") and is_cooldown_ready():
                                        await place_short("BTCUSDT", CONFIG["TRADE_AMOUNT_USD"])
                                        update_cooldown()

                        cluster_data.clear()
                        cluster_last_reset = now
                        cluster_is_processing = False

        except Exception as e:
            error_counter += 1
            reconnect_delay = min(60, reconnect_delay * 2)
            current_uri_index = (current_uri_index + 1) % len(uri_list)

            if error_counter > 5:
                send_message(f"❌ Занадто багато помилок WebSocket підряд ({error_counter}). Бот призупинено на 5 хвилин.")
                await asyncio.sleep(300)
                error_counter = 0
                reconnect_delay = 5
            else:
                send_message(f"⚠️ WebSocket помилка: {e}. Перемикаємо сервер. Перепідключення через {reconnect_delay} сек...")
                await asyncio.sleep(reconnect_delay)



# 🧰 Скасування існуючого стоп-ордеру для сторони
def cancel_existing_orders(side):
    try:
        orders = binance_client.futures_get_open_orders(symbol=CONFIG["SYMBOL"])
        for o in orders:
            if o["positionSide"] == side and o["type"] in ["STOP_MARKET", "TAKE_PROFIT_MARKET"]:
                binance_client.futures_cancel_order(symbol=CONFIG["SYMBOL"], orderId=o["orderId"])
    except Exception as e:
        send_message(f"❌ Cancel order error ({side}): {e}")

# 🛡️ Професійний моніторинг трейлінг-стопів і часткових закриттів
async def monitor_trailing_stops():
    """
    Контролює перенесення трейлінг-стопів та часткове закриття позицій при досягненні цільових рівнів прибутку.
    Завжди перевіряє і встановлює новий стоп після часткового закриття.
    """
    while True:
        try:
            for side in ["LONG", "SHORT"]:
                positions: list = binance_client.futures_position_information(symbol=CONFIG["SYMBOL"])
                pos = next((p for p in positions if (
                    (side == "LONG" and float(p["positionAmt"]) > 0) or
                    (side == "SHORT" and float(p["positionAmt"]) < 0)
                )), None)

                if not pos:
                    continue  # Якщо позиції немає — переходимо до наступного боку

                entry: float = float(pos["entryPrice"])
                qty: float = abs(float(pos["positionAmt"]))
                mark: float = float(binance_client.futures_mark_price(symbol=CONFIG["SYMBOL"])["markPrice"])

                profit_pct: float = (
                    (mark - entry) / entry * 100 if side == "LONG" else
                    (entry - mark) / entry * 100
                )

                new_sl: float = None

                # 🔥 Логіка трейлінгу
                if profit_pct >= 0.8:
                    new_sl = round(entry * (1 + CONFIG["TRAILING_LEVELS"]["0.8"] if side == "LONG" else 1 - CONFIG["TRAILING_LEVELS"]["0.8"]), 2)
                elif profit_pct >= 0.5:
                    new_sl = round(entry * (1 + CONFIG["TRAILING_LEVELS"]["0.5"] if side == "LONG" else 1 - CONFIG["TRAILING_LEVELS"]["0.5"]), 2)
                elif profit_pct >= 0.3:
                    new_sl = round(entry * (1 + CONFIG["TRAILING_LEVELS"]["0.3"] if side == "LONG" else 1 - CONFIG["TRAILING_LEVELS"]["0.3"]), 2)

                if new_sl:
                    if (
                        trailing_stops[side] is None or
                        (side == "LONG" and new_sl > trailing_stops[side]) or
                        (side == "SHORT" and new_sl < trailing_stops[side])
                    ):
                        trailing_stops[side] = new_sl
                        cancel_existing_orders(side)
                        binance_client.futures_create_order(
                            symbol=CONFIG["SYMBOL"],
                            side='SELL' if side == "LONG" else 'BUY',
                            type='STOP_MARKET',
                            stopPrice=new_sl,
                            closePosition=True,
                            timeInForce="GTC",
                            positionSide=side
                        )
                        send_message(f"🛡️ Оновлено трейлінг-стоп: {new_sl}")

                # 🔥 Часткове закриття при досягненні цілі
                if profit_pct >= CONFIG["PARTIAL_CLOSE_AT"] and qty >= 0.0002:
                    qty_close: float = round(qty * CONFIG["PARTIAL_CLOSE_SIZE"], 4)
                    qty_remain: float = round(qty - qty_close, 4)

                    # Закриваємо частину позиції
                    binance_client.futures_create_order(
                        symbol=CONFIG["SYMBOL"],
                        side='SELL' if side == "LONG" else 'BUY',
                        type='MARKET',
                        quantity=qty_close,
                        positionSide=side
                    )
                    send_message(f"💰 Часткове закриття: закрито {qty_close}, залишено {qty_remain}")

                    # Оновлюємо стоп на залишок
                    if qty_remain > 0:
                        breakeven_sl: float = round(
                            entry * (1 + CONFIG["BREAKEVEN_SL_OFFSET"] if side == "LONG" else 1 - CONFIG["BREAKEVEN_SL_OFFSET"]),
                            2
                        )
                        cancel_existing_orders(side)
                        binance_client.futures_create_order(
                            symbol=CONFIG["SYMBOL"],
                            side='SELL' if side == "LONG" else 'BUY',
                            type='STOP_MARKET',
                            stopPrice=breakeven_sl,
                            quantity=qty_remain,
                            timeInForce="GTC",
                            positionSide=side
                        )
                        send_message(f"🛡️ Новий стоп на залишок {qty_remain}: {breakeven_sl}")

        except Exception as e:
            send_message(f"⚠️ Trailing monitor error: {e}")

        await asyncio.sleep(10)

# 📈 Відкриття LONG угоди (з перевіркою і безпечною взаємодією)
async def place_long(symbol: str, usd: float):
    """
    Відкриття LONG-позиції. Попередньо закриває SHORT-позицію безпечним методом safe_close_position().
    """
    async with open_position_lock:
        # Спочатку закриваємо SHORT, якщо відкритий
        if has_open_position("SHORT"):
            await safe_close_position("SHORT")

        # Перевірка: якщо SHORT ще відкритий — не відкривати LONG
        if has_open_position("SHORT"):
            send_message("❗ SHORT ще відкритий — НЕ відкриваємо LONG!")
            return

        # Перевірка: якщо вже відкритий LONG — не відкривати ще один
        if has_open_position("LONG"):
            send_message("⚠️ Уже відкрита LONG позиція")
            return

        try:
            # Отримуємо поточну ціну для розрахунку кількості
            entry: float = float(binance_client.futures_mark_price(symbol=symbol)["markPrice"])
            qty: float = round(usd / entry, 3)
            if not qty:
                send_message("❌ Не вдалося розрахувати кількість для LONG")
                return

            tp: float = round(entry * CONFIG["TP_SL"]["LONG"]["TP"], 2)
            sl: float = round(entry * CONFIG["TP_SL"]["LONG"]["SL"], 2)

            # Перед відкриттям нової позиції очищаємо старі ордери
            cancel_existing_orders("LONG")

            if DRY_RUN:
                send_message(f"🤖 [DRY_RUN] LONG\n📍 Entry: {entry}\n📦 Qty: {qty}\n🎯 TP: {tp}\n🛡️ SL: {sl}")
            else:
                # Відкриття LONG через MARKET
                binance_client.futures_create_order(
                    symbol=symbol,
                    side='BUY',
                    type='MARKET',
                    quantity=qty,
                    positionSide='LONG'
                )
                # Створення тейк-профіту
                binance_client.futures_create_order(
                    symbol=symbol,
                    side='SELL',
                    type='TAKE_PROFIT_MARKET',
                    stopPrice=tp,
                    closePosition=True,
                    timeInForce="GTC",
                    positionSide='LONG'
                )
                # Створення стоп-лоссу
                binance_client.futures_create_order(
                    symbol=symbol,
                    side='SELL',
                    type='STOP_MARKET',
                    stopPrice=sl,
                    closePosition=True,
                    timeInForce="GTC",
                    positionSide='LONG'
                )
                send_message(f"🟢 LONG OPEN\n📍 Entry: {entry}\n📦 Qty: {qty}\n🎯 TP: {tp}\n🛡️ SL: {sl}")
                log_to_sheet(
                    type_="LONG",
                    entry=entry,
                    tp=tp,
                    sl=sl,
                    qty=qty,
                    result=None,
                    comment="GPT сигнал"
                )


        except Exception as e:
            send_message(f"❌ Binance LONG open error: {e}")


# 📉 Відкриття SHORT угоди (з перевіркою і безпечною взаємодією)
async def place_short(symbol: str, usd: float):
    """
    Відкриття SHORT-позиції. Попередньо закриває LONG-позицію безпечним методом safe_close_position().
    """
    async with open_position_lock:
        # Спочатку закриваємо LONG, якщо відкритий
        if has_open_position("LONG"):
            await safe_close_position("LONG")

        # Перевірка: якщо LONG ще відкритий — не відкривати SHORT
        if has_open_position("LONG"):
            send_message("❗ LONG ще відкритий — НЕ відкриваємо SHORT!")
            return

        # Перевірка: якщо вже відкритий SHORT — не відкривати ще один
        if has_open_position("SHORT"):
            send_message("⚠️ Уже відкрита SHORT позиція")
            return

        try:
            # Отримуємо поточну ціну для розрахунку кількості
            entry: float = float(binance_client.futures_mark_price(symbol=symbol)["markPrice"])
            qty: float = round(usd / entry, 3)
            if not qty:
                send_message("❌ Не вдалося розрахувати кількість для SHORT")
                return

            tp: float = round(entry * CONFIG["TP_SL"]["SHORT"]["TP"], 2)
            sl: float = round(entry * CONFIG["TP_SL"]["SHORT"]["SL"], 2)

            # Перед відкриттям нової позиції очищаємо старі ордери
            cancel_existing_orders("SHORT")

            if DRY_RUN:
                send_message(f"🤖 [DRY_RUN] SHORT\n📍 Entry: {entry}\n📦 Qty: {qty}\n🎯 TP: {tp}\n🛡️ SL: {sl}")
            else:
                # Відкриття SHORT через MARKET
                binance_client.futures_create_order(
                    symbol=symbol,
                    side='SELL',
                    type='MARKET',
                    quantity=qty,
                    positionSide='SHORT'
                )
                # Створення тейк-профіту
                binance_client.futures_create_order(
                    symbol=symbol,
                    side='BUY',
                    type='TAKE_PROFIT_MARKET',
                    stopPrice=tp,
                    closePosition=True,
                    timeInForce="GTC",
                    positionSide='SHORT'
                )
                # Створення стоп-лоссу
                binance_client.futures_create_order(
                    symbol=symbol,
                    side='BUY',
                    type='STOP_MARKET',
                    stopPrice=sl,
                    closePosition=True,
                    timeInForce="GTC",
                    positionSide='SHORT'
                )
                send_message(f"🔴 SHORT OPEN\n📍 Entry: {entry}\n📦 Qty: {qty}\n🎯 TP: {tp}\n🛡️ SL: {sl}")
                log_to_sheet(
                    type_="SHORT",
                    entry=entry,
                    tp=tp,
                    sl=sl,
                    qty=qty,
                    result=None,
                    comment="GPT сигнал"
                )


        except Exception as e:
            send_message(f"❌ Binance SHORT open error: {e}")


            
# 📒 Підключення до Google Sheets
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
     # 🛡️ Безпечне закриття відкритої позиції через MARKET
async def safe_close_position(side: str):
    """
    Закриття відкритої позиції через MARKET.
    Якщо помилка через reduceOnly — повторна спроба без reduceOnly.
    """
    try:
        qty_to_close: float = get_current_position_qty(side)
        if qty_to_close > 0:
            try:
                binance_client.futures_create_order(
                    symbol=CONFIG["SYMBOL"],
                    side='SELL' if side == "LONG" else 'BUY',
                    type='MARKET',
                    quantity=qty_to_close,
                    reduceOnly=True,
                    positionSide=side
                )
                send_message(f"🔻 Закрито {side} через reduceOnly: {qty_to_close}")
                await asyncio.sleep(1)
            except Exception as e:
                error_text = str(e)
                send_message(f"⚠️ Не вдалося закрити {side} через reduceOnly: {error_text}")
                if "reduceonly" in error_text.lower():
                    send_message(f"⛔ Пробую закрити {side} через чистий MARKET без reduceOnly...")
                    try:
                        binance_client.futures_create_order(
                            symbol=CONFIG["SYMBOL"],
                            side='SELL' if side == "LONG" else 'BUY',
                            type='MARKET',
                            quantity=qty_to_close,
                            positionSide=side
                        )
                        send_message(f"✅ Успішно закрито {side} через чистий MARKET!")
                        await asyncio.sleep(1)
                    except Exception as e_inner:
                        send_message(f"❌ Повторна помилка закриття {side}: {e_inner}")
    except Exception as e:
        send_message(f"❌ Safe close error ({side}): {e}")

# 🧠 Обробка сигналу: переворот лише при SUPER_BOOSTED
async def handle_signal(signal: str):
    """
    Приймає рішення про відкриття/переворот на основі сигналу.
    Переворот лише при SUPER_BOOSTED.
    """
    try:
        side_now: str = None
        if has_open_position("LONG"):
            side_now = "LONG"
        elif has_open_position("SHORT"):
            side_now = "SHORT"

        # Визначаємо напрямок і тип сигналу
        signal_direction: str = None
        super_boosted: bool = False

        if signal.startswith("SUPER_BOOSTED_LONG"):
            signal_direction = "LONG"
            super_boosted = True
        elif signal.startswith("SUPER_BOOSTED_SHORT"):
            signal_direction = "SHORT"
            super_boosted = True
        elif signal.startswith("BOOSTED_LONG") or signal.startswith("LONG"):
            signal_direction = "LONG"
        elif signal.startswith("BOOSTED_SHORT") or signal.startswith("SHORT"):
            signal_direction = "SHORT"

        # Якщо позиція ще не відкрита — відкриваємо
        if side_now is None:
            if signal_direction == "LONG":
                await place_long(CONFIG["SYMBOL"], CONFIG["TRADE_AMOUNT_USD"])
                update_cooldown()
            elif signal_direction == "SHORT":
                await place_short(CONFIG["SYMBOL"], CONFIG["TRADE_AMOUNT_USD"])
                update_cooldown()
            return

        # Якщо напрямок змінився і це SUPER BOOSTED → переворот
        if side_now != signal_direction and super_boosted:
            send_message(f"🔄 Супер сигнал! Переворот {side_now} → {signal_direction}")
            await close_all_positions_and_orders()
            await asyncio.sleep(0.5)
            if signal_direction == "LONG":
                await place_long(CONFIG["SYMBOL"], CONFIG["TRADE_AMOUNT_USD"])
                update_cooldown()
            elif signal_direction == "SHORT":
                await place_short(CONFIG["SYMBOL"], CONFIG["TRADE_AMOUNT_USD"])
                update_cooldown()
        else:
            send_message(f"⚡ Тримаємо позицію ({side_now}), сигнал: {signal}")

    except Exception as e:
        send_message(f"❌ Handle signal error: {e}")

# 🧹 Повне закриття всіх позицій і відкритих ордерів
async def close_all_positions_and_orders():
    """
    Закриває всі відкриті позиції (LONG/SHORT) через MARKET,
    а також скасовує всі відкриті стопи і тейки.
    """
    try:
        qty_long: float = get_current_position_qty("LONG")
        qty_short: float = get_current_position_qty("SHORT")

        # Закриваємо LONG
        if qty_long > 0:
            try:
                binance_client.futures_create_order(
                    symbol=CONFIG["SYMBOL"],
                    side='SELL',
                    type='MARKET',
                    quantity=qty_long,
                    reduceOnly=True,
                    positionSide='LONG'
                )
                send_message(f"🔻 Закрито LONG позицію: {qty_long}")
                await asyncio.sleep(0.5)
            except Exception as e:
                send_message(f"❌ Помилка закриття LONG: {e}")

        # Закриваємо SHORT
        if qty_short > 0:
            try:
                binance_client.futures_create_order(
                    symbol=CONFIG["SYMBOL"],
                    side='BUY',
                    type='MARKET',
                    quantity=qty_short,
                    reduceOnly=True,
                    positionSide='SHORT'
                )
                send_message(f"🔺 Закрито SHORT позицію: {qty_short}")
                await asyncio.sleep(0.5)
            except Exception as e:
                send_message(f"❌ Помилка закриття SHORT: {e}")

        # Видаляємо стопи та тейки
        try:
            open_orders: list = binance_client.futures_get_open_orders(symbol=CONFIG["SYMBOL"])
            for order in open_orders:
                binance_client.futures_cancel_order(
                    symbol=CONFIG["SYMBOL"],
                    orderId=order["orderId"]
                )
            send_message("🧹 Видалено всі відкриті стопи та тейки.")
        except Exception as e:
            send_message(f"❌ Помилка скасування ордерів: {e}")

    except Exception as e:
        send_message(f"❌ Close all positions error: {e}")


        # Після закриття всіх позицій — прибираємо всі відкриті ордери
        try:
            open_orders: list = binance_client.futures_get_open_orders(symbol=CONFIG["SYMBOL"])
            for order in open_orders:
                binance_client.futures_cancel_order(
                    symbol=CONFIG["SYMBOL"],
                    orderId=order["orderId"]
                )
            send_message("🧹 Видалено всі відкриті стопи та тейки.")
        except Exception as e:
            send_message(f"❌ Помилка скасування ордерів: {e}")

    except Exception as e:
        send_message(f"❌ Close all positions error: {e}")

# 📡 Моніторинг змін у стакані ордерів Binance
async def monitor_orderbook(symbol: str = "BTCUSDT"):
    """
    Підключення до WebSocket потоку depth20@100ms для моніторингу заявок на покупку та продаж.
    Зберігає інформацію про великі buy/sell стіни для подальшого використання в GPT аналізі.
    """
    global current_buy_wall, current_sell_wall
    current_buy_wall = None  # тип: Optional[float]
    current_sell_wall = None  # тип: Optional[float]
    # 🔍 Перевірка на зникнення стін
if last_bid_wall > 0 and current_buy_wall < last_bid_wall * 0.3:
    fake_wall_detected = True
    send_message("⚠️ Виявлена фейкова Buy стіна. Активовано SKIP.")

if last_ask_wall > 0 and current_sell_wall < last_ask_wall * 0.3:
    fake_wall_detected = True
    send_message("⚠️ Виявлена фейкова Sell стіна. Активовано SKIP.")

# Оновлення стін для наступної перевірки
last_bid_wall = current_buy_wall
last_ask_wall = current_sell_wall

    

    uri = f"wss://fstream.binance.com/ws/{symbol.lower()}@depth20@100ms"

    while True:
        try:
            async with websockets.connect(uri, ping_interval=None) as websocket:
                send_message(f"✅ Підключено до Orderbook WebSocket: {symbol}")

                while True:
                    try:
                        msg = await websocket.recv()
                        data = json.loads(msg)

                        bids = data.get("b", [])  # список [price, quantity]
                        asks = data.get("a", [])

                        # Знаходимо найбільшу заявку на купівлю
                        max_bid_qty = max([float(qty) for price, qty in bids if float(qty) > 0], default=0)
                        # Знаходимо найбільшу заявку на продаж
                        max_ask_qty = max([float(qty) for price, qty in asks if float(qty) > 0], default=0)

                        # Оновлюємо глобальні змінні
                        current_buy_wall = max_bid_qty
                        current_sell_wall = max_ask_qty

                    except Exception as inner_error:
                        send_message(f"⚠️ Orderbook inside error: {inner_error}")
                        await asyncio.sleep(1)
                        break  # Перезапуск підключення

        except Exception as outer_error:
            send_message(f"❌ Orderbook connection error: {outer_error}")
            await asyncio.sleep(5)  # Перезапуск через 5 секунд

# 🧠 Моніторинг закриття позицій + запис результатів у Google Sheets
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

                    # 🧠 Логування помилки у GPT памʼять при LOSS
                    if result == "LOSS":
                        reason = explain_trade_outcome(side, result, pnl)
                        update_stats_sheet()
                        log_learning_entry(side, result, reason, pnl)
                        send_message(f"🧠 GPT пояснення збитку:\n{reason}")
                    
                    else:
                        update_stats_sheet()


                    # 🧹 Обмеження розміру закритих позицій
                    if len(closed_positions_handled) > 100:
                        closed_positions_handled.clear()

        except Exception as e:
            send_message(f"⚠️ Closure check error: {e}")

        await asyncio.sleep(60)
# 🧠 Пояснення результату угоди через GPT (чому WIN або чому LOSS)
def explain_trade_outcome(trade_type, result, pnl):
    try:
        prompt = f"""
Тип угоди: {trade_type}
Результат: {result}
PnL: {pnl}

Поясни коротко (1 реченням), чому результат був таким. Якщо була помилка — вкажи її.
"""
        res = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": (
                    "Ти трейдинг-аналітик. Поясни коротко, чому угода завершилась так. "
                    "Відповідай однією фразою без зайвих деталей."
                )},
                {"role": "user", "content": prompt}
            ]
        )

        return res.choices[0].message.content.strip()
    except Exception as e:
        send_message(f"❌ GPT (explain_trade) error: {e}")
        return "Не вдалося отримати пояснення від GPT."

# 📚 Логування результату та пояснення у "Learning Log" Google Sheets
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
# 🚀 Запуск усіх моніторів при старті FastAPI
@app.on_event("startup")
async def start_all_monitors():
    try:
        check_env_variables()  # 🔐 Перевірка наявності важливих ENV
        init_runtime_state()   # ♻️ Скидання кешу і стану при перезапуску

        asyncio.create_task(monitor_market_cache())        # 📡 Кешування OI/Volume/VWAP
        asyncio.create_task(monitor_cluster_trades())      # 🧠 Кластерний моніторинг та GPT-аналіз
        asyncio.create_task(monitor_trailing_stops())      # 🛡️ Трейлінг-стопи
        asyncio.create_task(monitor_closures())            # 📈 Моніторинг закриття угод і логування
        asyncio.create_task(monitor_orderbook(CONFIG["SYMBOL"]))
        asyncio.create_task(monitor_delta_volume(CONFIG["SYMBOL"]))



        send_message("✅ Бот ScalpGPT успішно стартував і монітори запущено.")
    except Exception as e:
        send_message(f"❌ Помилка при старті бота: {e}")
        
# 📊 Моніторинг дельти обʼєму та підрахунок Buy/Sell Ratio у реальному часі
async def monitor_delta_volume(symbol: str = "BTCUSDT"):
    """
    Підключення до WebSocket потоку aggTrade для підрахунку Buy Volume, Sell Volume, Delta і Buy/Sell Ratio.
    Оновлення кожні 3 секунди.
    """
    global current_buy_volume, current_sell_volume, current_buy_ratio, current_sell_ratio

    # 🛠️ Ініціалізація змінних без типізації тут
    current_buy_volume = 0.0
    current_sell_volume = 0.0
    current_buy_ratio = 50.0  # Стартові значення в центрі
    current_sell_ratio = 50.0


    uri: str = f"wss://fstream.binance.com/ws/{symbol.lower()}@aggTrade"

    while True:
        try:
            async with websockets.connect(uri, ping_interval=None) as websocket:
                send_message(f"✅ Підключено до Delta Volume WebSocket: {symbol}")

                buy_volume_batch: float = 0.0
                sell_volume_batch: float = 0.0
                last_update_time: float = time.time()

                while True:
                    try:
                        msg_raw = await websocket.recv()
                        msg = json.loads(msg_raw)

                        price: float = float(msg['p'])
                        qty: float = float(msg['q'])
                        is_sell: bool = msg['m']

                        if is_sell:
                            sell_volume_batch += price * qty
                        else:
                            buy_volume_batch += price * qty

                        now: float = time.time()

                        # Оновлюємо дані кожні 3 секунди
                        if now - last_update_time >= 3:
                            total_volume: float = buy_volume_batch + sell_volume_batch

                            if total_volume > 0:
                                current_buy_ratio = round((buy_volume_batch / total_volume) * 100, 2)
                                current_sell_ratio = 100.0 - current_buy_ratio
                            else:
                                current_buy_ratio = 50.0
                                current_sell_ratio = 50.0

                            # Зберігаємо фактичні об'єми
                            current_buy_volume = buy_volume_batch
                            current_sell_volume = sell_volume_batch

                            # Лог в консоль для дебагу
                            print(f"📈 Delta Update: Buy {current_buy_ratio}% | Sell {current_sell_ratio}% | BuyVolume ${round(buy_volume_batch)} | SellVolume ${round(sell_volume_batch)}")

                            # Скидаємо батч для наступної порції
                            buy_volume_batch = 0.0
                            sell_volume_batch = 0.0
                            last_update_time = now

                    except Exception as inner_error:
                        send_message(f"⚠️ Delta volume internal error: {inner_error}")
                        await asyncio.sleep(1)
                        break  # Перезапуск WebSocket

        except Exception as outer_error:
            send_message(f"❌ Delta volume connection error: {outer_error}")
            await asyncio.sleep(5)  # Перезапуск WebSocket

# 📬 Webhook приймає сигнали з TradingView або Postman
@app.post("/webhook")
async def webhook(req: Request):
    try:
        data = await req.json()
        signal = data.get("message", "").strip().upper()
        send_message(f"📩 Отримано сигнал: {signal}")

        if signal not in ["LONG", "SHORT", "BOOSTED_LONG", "BOOSTED_SHORT"]:
            send_message(f"⚠️ Невідомий сигнал: {signal}")
            return {"error": "Invalid signal"}

        # Беремо дані з кешу
        oi = cached_oi
        volume = cached_volume

        # 🔥 Безпечне отримання новин
        try:
            news = get_latest_news()
        except Exception as news_error:
            send_message(f"❌ News fallback error: {news_error}")
            news = "⚠️ Новини тимчасово недоступні."

        if oi is None or volume is None:
            send_message("⚠️ Дані кешу ще не прогріті — пропущено webhook.")
            return {"error": "Cache not ready"}

        global last_open_interest
        delta = ((oi - last_open_interest) / last_open_interest) * 100 if last_open_interest and oi else 0
        last_open_interest = oi

        send_message(f"📊 OI: {oi:,.0f} | Volume: {volume} | ΔOI: {delta:.2f}%")

        decision = await ask_gpt_trade_with_all_context(signal, news, oi, delta, volume)
        send_message(f"🤖 GPT вирішив: {decision}")

        await handle_signal(decision)

        return {"ok": True}

    except Exception as e:
        send_message(f"❌ Webhook error: {e}")
        return {"error": str(e)}
