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
DEBUG_MODE = os.getenv('DEBUG_MODE', 'True') == 'True'  # 🔧 Увімкнено режим логування (без реальних угод)
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
TRADE_USD_AMOUNT = float(os.getenv("TRADE_USD_AMOUNT", 1000))

# 🔌 Clients
binance_client = Client(api_key=BINANCE_API_KEY, api_secret=BINANCE_SECRET_KEY)
client = OpenAI(api_key=OPENAI_API_KEY)
last_open_interest = None

# 📬 Telegram
def send_message(text: str):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": text}
try:
    pass
except:
    pass
    requests.post(url, data=data)

except Exception as e:
        print(f"Telegram error: {e}")

# 📊 Google Sheets
def log_to_sheet(type_, entry, tp, sl, qty, result=None, comment=""):
    pass
try:
    pass
except:
    pass
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
    pass
try:
    pass
except:
    pass
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
    pass
try:
    pass
except:
    pass
        url = f"https://cryptopanic.com/api/v1/posts/?auth_token={NEWS_API_KEY}&filter=important"
        r = requests.get(url)
        news = r.json()
        return "\n".join([item["title"] for item in news.get("results", [])[:3]])
except:
        return "⚠️ Новини не вдалося завантажити."

def get_open_interest(symbol="BTCUSDT"):
    pass
try:
    pass
except:
    pass
        r = requests.get("https://fapi.binance.com/fapi/v1/openInterest", params={"symbol": symbol})
        return float(r.json()["openInterest"]) if r.ok else None
except:
        return None

def get_volume(symbol="BTCUSDT"):
    pass
try:
    pass
except:
    pass
        data = binance_client.futures_klines(symbol=symbol, interval="1m", limit=1)
        return float(data[-1][7])
except:
        return None

def get_quantity(symbol: str, usd: float):
    pass
try:
    pass
except:
    pass
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

# 📏 VWAP обрахунок
def calculate_vwap(symbol="BTCUSDT", interval="1m", limit=10):
    pass
try:
    pass
except:
    pass
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

# 📉 Флет-фільтр
def is_flat_zone(symbol="BTCUSDT"):
    pass
try:
    pass
except:
    pass
        price = float(binance_client.futures_mark_price(symbol=symbol)["markPrice"])
        vwap = calculate_vwap(symbol)
        if not vwap:
            return False
        return abs(price - vwap) / price < 0.005
except:
        return False


def get_last_trades(limit=10):
    pass
try:
    pass
except:
    pass
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name("/etc/secrets/credentials.json", scope)
        gclient = gspread.authorize(creds)
        sh = gclient.open_by_key(GOOGLE_SHEET_ID)
        sheet = sh.worksheets()[0]
        data = sheet.get_all_values()[1:]  # без заголовка
        data.reverse()
        gpt_logs = [row for row in data if row[1] in ["LONG", "SHORT", "BOOSTED_LONG", "BOOSTED_SHORT"] and row[6]]
        recent = gpt_logs[:limit]
        result = [f"{i+1}. {row[1]} → {row[6]}" for i, row in enumerate(recent)]
        return "\n".join(result)
except:
        return ""

def update_stats_sheet():
    pass
try:
    pass
except:
    pass
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name("/etc/secrets/credentials.json", scope)
        gclient = gspread.authorize(creds)
        sh = gclient.open_by_key(GOOGLE_SHEET_ID)

        data = sh.worksheets()[0].get_all_values()
        header = data[0]
        rows = data[1:]

        stats = {}
        for row in rows:
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
    pass
except:
    pass
            stat_sheet = sh.worksheet("Stats")
            stat_sheet.clear()
except:
            stat_sheet = sh.add_worksheet(title="Stats", rows="20", cols="5")

        stat_sheet.update("A1", stat_rows)

except Exception as e:
        send_message(f"❌ Stats error: {e}")

# 🤖 GPT

def get_last_trades(limit=10):
    pass
try:
    pass
except:
    pass
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
    pass
try:
    pass
except:
    pass
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

def ask_gpt_trade_with_all_context(type_, news, oi, delta, volume):
    recent_trades = get_last_trades()
    stats_summary = get_stats_summary()

    # 🧠 Адаптивний флет-фільтр: блокує тільки якщо немає BOOSTED і обʼєм малий
    if is_flat_zone("BTCUSDT") and "BOOSTED" not in type_ and volume < 300:
        return "SKIP"


    recent_trades = get_last_trades()
    prompt = f"""
GPT минулі сигнали:
{recent_trades}

Winrate по типах:
{stats_summary}

\nGPT минулі сигнали:\n{recent_trades}\n\n
Останні новини:
{news}

Open Interest: {oi:,.0f}
Зміна OI: {delta:.2f}%
Обʼєм за 1хв: {volume}

Сигнал: {type_.upper()}

Якщо сигнал має префікс BOOSTED_, це означає, що зафіксована агресивна торгівля або великий імпульс. ТИ МАЄШ ПІДТВЕРДИТИ ЙОГО, крім ситуацій із критичними новинами або дуже слабким обсягом.

Чи підтверджуєш цей сигнал?
- LONG / BOOSTED_LONG / SHORT / BOOSTED_SHORT / SKIP
"""

try:
    pass
except:
    pass
        res = client.chat.completions.create(
            model="gpt-4-turbo",
            messages=[
                {"role": "system", "content": "Ти трейдинг-аналітик. Відповідай лише одним зі слів: LONG, BOOSTED_LONG, SHORT, BOOSTED_SHORT, SKIP."},
                {"role": "user", "content": prompt}
            ]
        )
        return res.choices[0].message.content.strip()
except:
        return "SKIP"
# 📈 Торгівля

def place_long(symbol, usd):
    if has_open_position("LONG"):
        send_message("⚠️ Уже відкрита LONG позиція")
        return
try:
    pass
except:
    pass
except:
    pass
        entry = float(binance_client.futures_mark_price(symbol=symbol)["markPrice"])
        qty = get_quantity(symbol, usd)
        if not qty:
            send_message("❌ Обсяг не визначено.")
            return
        tp = round(entry * 1.015, 2)
        sl = round(entry * 0.992, 2)
        binance_client.futures_create_order(symbol=symbol, side='BUY', type='MARKET', quantity=qty, positionSide='LONG')
    else:
        send_message('🧪 DEBUG: Спроба відкриття ордера — пропущено')
        binance_client.futures_create_order(symbol=symbol, side='SELL', type='TAKE_PROFIT_MARKET',
                                            stopPrice=tp, closePosition=True, timeInForce="GTC", positionSide='LONG')
    else:
        send_message('🧪 DEBUG: Спроба відкриття ордера — пропущено')
        binance_client.futures_create_order(symbol=symbol, side='SELL', type='STOP_MARKET',
                                            stopPrice=sl, closePosition=True, timeInForce="GTC", positionSide='LONG')
    else:
        send_message('🧪 DEBUG: Спроба відкриття ордера — пропущено')
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
    pass
except:
    pass
except:
    pass
        entry = float(binance_client.futures_mark_price(symbol=symbol)["markPrice"])
        qty = get_quantity(symbol, usd)
        if not qty:
            send_message("❌ Обсяг не визначено.")
            return
        tp = round(entry * 0.99, 2)
        sl = round(entry * 1.008, 2)
        binance_client.futures_create_order(symbol=symbol, side='SELL', type='MARKET', quantity=qty, positionSide='SHORT')
    else:
        send_message('🧪 DEBUG: Спроба відкриття ордера — пропущено')
        binance_client.futures_create_order(symbol=symbol, side='BUY', type='TAKE_PROFIT_MARKET',
                                            stopPrice=tp, closePosition=True, timeInForce="GTC", positionSide='SHORT')
    else:
        send_message('🧪 DEBUG: Спроба відкриття ордера — пропущено')
        binance_client.futures_create_order(symbol=symbol, side='BUY', type='STOP_MARKET',
                                            stopPrice=sl, closePosition=True, timeInForce="GTC", positionSide='SHORT')
    else:
        send_message('🧪 DEBUG: Спроба відкриття ордера — пропущено')
        send_message(f"🔴 SHORT OPEN {entry}\n📦 Qty: {qty}\n🎯 TP: {tp}\n🛡 SL: {sl}")
        log_to_sheet("SHORT", entry, tp, sl, qty, None, "GPT сигнал")
        update_stats_sheet()
    except Exception as e:
        send_message(f"❌ Binance SHORT error: {e}")

# 📬 Webhook
@app.post("/webhook")
async def webhook(req: Request):
    global last_open_interest
try:
    pass
except:
    pass
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
        log_gpt_decision(signal, decision)
        log_to_sheet("GPT_DECISION", "", "", "", "", "", f"{signal} → {decision}")
        if decision in ["LONG", "BOOSTED_LONG"]:
            place_long("BTCUSDT", TRADE_USD_AMOUNT)
        elif decision in ["SHORT", "BOOSTED_SHORT"]:
            place_short("BTCUSDT", TRADE_USD_AMOUNT)
        return {"ok": True}
except Exception as e:
        send_message(f"❌ Webhook error: {e}")
        return {"error": str(e)}
# 🐋 Whale Detector
agg_trades = []

async def monitor_agg_trades():
    uri = "wss://fstream.binance.com/ws/btcusdt@aggTrade"
    async with websockets.connect(uri) as websocket:
        while True:
try:
    pass
except:
    pass
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
                        decision = ask_gpt_trade_with_all_context(signal, news, oi, delta, volume)
                        send_message(f"🤖 GPT вирішив: {decision}")
        log_gpt_decision(signal, decision)
                        log_to_sheet("GPT_DECISION", "", "", "", "", "", f"{signal} → {decision}")
                        if decision in ["BOOSTED_LONG", "LONG"]:
                            place_long("BTCUSDT", TRADE_USD_AMOUNT)
                        elif decision in ["BOOSTED_SHORT", "SHORT"]:
                            place_short("BTCUSDT", TRADE_USD_AMOUNT)
except Exception as e:
                send_message(f"⚠️ WebSocket error: {e}")
                await asyncio.sleep(5)

# 💰 Моніторинг закриття угод
async def monitor_closures():
    while True:
        for side in ["LONG", "SHORT"]:
try:
    pass
except:
    pass
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

# 🔁 Трейлінг-стоп
trailing_stops = {"LONG": None, "SHORT": None}

async def monitor_trailing_stops():
    while True:
try:
    pass
except:
    pass
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
# 🤖 Автоаналіз щохвилини
async def monitor_auto_signals():
    global last_open_interest
    while True:
try:
    pass
except:
    pass
            news = get_latest_news()
            oi = get_open_interest("BTCUSDT")
            volume = get_volume("BTCUSDT")
            if not oi or not volume:
                await asyncio.sleep(60)
                continue

            delta = ((oi - last_open_interest) / last_open_interest) * 100 if last_open_interest else 0
            last_open_interest = oi

            signal = "LONG" if delta > 0.2 else "SHORT" if delta < -0.2 else None

            if not signal:
                await asyncio.sleep(60)
                continue

            decision = ask_gpt_trade_with_all_context(signal, news, oi, delta, volume)

            if decision == "SKIP":
                await asyncio.sleep(60)
                continue

            send_message(f"🤖 GPT (автоаналіз): {decision}")
            log_to_sheet("GPT_DECISION", "", "", "", "", "", f"AUTO {signal} → {decision}")

            if decision in ["LONG", "BOOSTED_LONG"]:
                place_long("BTCUSDT", TRADE_USD_AMOUNT)
            elif decision in ["SHORT", "BOOSTED_SHORT"]:
                place_short("BTCUSDT", TRADE_USD_AMOUNT)

except Exception as e:
            send_message(f"❌ Auto signal error: {e}")
        await asyncio.sleep(60)

# 🚀 Запуск
if __name__ == "__main__":
    import uvicorn
    import threading

    def start_ws():
        asyncio.run(monitor_agg_trades())

    def start_closures():
        asyncio.run(monitor_closures())

    def start_trailing():
        asyncio.run(monitor_trailing_stops())

    def start_auto_signals():
        asyncio.run(monitor_auto_signals())
    # Запускаємо всі потоки одночасно
    threading.Thread(target=start_ws).start()
    threading.Thread(target=start_closures).start()
    threading.Thread(target=start_trailing).start()
    threading.Thread(target=start_auto_signals).start()

    # Запускаємо FastAPI
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)

















# 📈 Перевірка відкритої позиції
def has_open_position(side):
    pass
try:
    pass
except:
    pass
        positions = binance_client.futures_position_information(symbol="BTCUSDT")
        pos = next((p for p in positions if p["positionSide"] == side), None)
        return pos and float(pos["positionAmt"]) != 0
except:
        return False



























































































# 📚 Самонавчання GPT + кластерний аналіз до входу + серії перемог
def get_recent_trades_and_streak(limit=10):
    pass
try:
    pass
except:
    pass
except:
    pass
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
    pass
try:
    pass
except:
    pass
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

def get_cluster_snapshot(limit=10):
    pass
try:
    pass
except:
    pass
        sorted_clusters = sorted(cluster_data.items(), key=lambda x: x[0], reverse=True)[-limit:]
        return "\n".join(
            f"{int(price)}$: BUY {data['buy']:.2f} | SELL {data['sell']:.2f}"
            for price, data in sorted_clusters
        )
except:
        return ""

def ask_gpt_trade_with_all_context(type_, news, oi, delta, volume):
    recent_trades, win_streak = get_recent_trades_and_streak()
    stats_summary = get_stats_summary()
    clusters = get_cluster_snapshot()

    prompt = f"""
GPT минулі сигнали:
{recent_trades}


Winrate по типах:
{stats_summary}

Серія перемог: {win_streak}/5

Сигнал: {type_.upper()}
Обʼєм: {volume}, Open Interest: {oi}, Зміна OI: {delta:.2f}%
Останні новини:
{news}

Кластери:
{clusters}

Ціль: досягти 5 win-підряд. Прийми зважене рішення. Вибери одне: LONG, SHORT, BOOSTED_LONG, BOOSTED_SHORT, SKIP.
"""
try:
    pass
except:
    pass
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

# 📘 Learning Log + пояснення GPT
def log_learning_entry(trade_type, result, reason, pnl=None):
    pass
try:
    pass
except:
    pass
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name("/etc/secrets/credentials.json", scope)
        gclient = gspread.authorize(creds)
        sh = gclient.open_by_key(GOOGLE_SHEET_ID)

try:
    pass
except:
    pass
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
    pass
try:
    pass
except:
    pass
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

# 🔁 Перезапис update_result_in_sheet
def update_result_in_sheet(type_, result, pnl=None):
    pass
try:
    pass
except:
    pass
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

# 📊 Daily Report
def generate_daily_report():
    pass
try:
    pass
except:
    pass
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name("/etc/secrets/credentials.json", scope)
        gclient = gspread.authorize(creds)
        sh = gclient.open_by_key(GOOGLE_SHEET_ID)
        sheet = sh.worksheets()[0]
        data = sheet.get_all_values()[1:]
        today = datetime.utcnow().strftime("%Y-%m-%d")
        today_trades = [row for row in data if today in row[0]]
        total = len(today_trades)
        wins = sum(1 for r in today_trades if r[6].strip().upper() == "WIN")
        losses = total - wins
        winrate = round(wins / total * 100, 2) if total > 0 else 0
        pnl_total = 0.0
        for row in today_trades:
            pnl = row[7].replace("USDT", "").replace("+", "").strip()
try:
    pass
except:
    pass
                pnl_total += float(pnl) if "WIN" in row[6] else -float(pnl)
except:
                continue
        best_signals = {}
        for row in today_trades:
            sig = row[1]
            res = row[6].strip().upper()
            if sig not in best_signals:
                best_signals[sig] = {"WIN": 0, "LOSS": 0}
            best_signals[sig][res] += 1
        top_performers = sorted(best_signals.items(), key=lambda x: x[1]["WIN"], reverse=True)
        top_summary = ", ".join([f"{k} ({v['WIN']}/{v['WIN']+v['LOSS']})" for k, v in top_performers[:3]])
        report_text = f"""
📊 GPT Daily Report — {today}
Угод: {total}
Winrate: {winrate}%
PnL: {pnl_total:.2f} USDT
Топ сигнали: {top_summary}
"""
try:
    pass
except:
    pass
            sheet_daily = sh.worksheet("Daily Report")
except:
            sheet_daily = sh.add_worksheet(title="Daily Report", rows="100", cols="5")
            sheet_daily.append_row(["Date", "Total", "Winrate %", "PnL USDT", "Top Signals"])
        sheet_daily.append_row([today, total, winrate, f"{pnl_total:.2f}", top_summary])
        send_message(report_text)
except Exception as e:
        send_message(f"❌ Daily report error: {e}")




# 🔁 Адаптивний трейлінг зі стопами під контролем GPT
async def adaptive_trailing_monitor():
    while True:
try:
    pass
except:
    pass
            positions = binance_client.futures_position_information(symbol="BTCUSDT")
            for side in ["LONG", "SHORT"]:
                pos = next((p for p in positions if p["positionSide"] == side), None)
                if pos and float(pos["positionAmt"]) != 0:
                    entry = float(pos["entryPrice"])
                    mark = float(binance_client.futures_mark_price(symbol="BTCUSDT")["markPrice"])
                    profit_pct = (mark - entry) / entry * 100 if side == "LONG" else (entry - mark) / entry * 100

                    sorted_clusters = sorted(cluster_data.items(), key=lambda x: x[0], reverse=True)
                    summary = "\n".join(
                        f"{int(price)}$: BUY {data['buy']:.2f} | SELL {data['sell']:.2f}"
                        for price, data in sorted_clusters
                    )
                    prompt = f"""
Позиція: {side}
Entry: {entry}
Mark: {mark}
Профіт: {profit_pct:.2f}%
Кластери:
{summary}

Що зробити зі стопом?
- MOVE_STOP_TO_X (вкажи ціну)
- KEEP_STOP
- CLOSE_POSITION
"""
                    res = client.chat.completions.create(
                        model="gpt-4-turbo",
                        messages=[
                            {"role": "system", "content": "Ти трейдинг-помічник. Вибери: MOVE_STOP_TO_X, KEEP_STOP, або CLOSE_POSITION."},
                            {"role": "user", "content": prompt}
                        ]
                    )
                    decision = res.choices[0].message.content.strip()
                    send_message(f"🤖 GPT Stop: {decision}")
except Exception as e:
            send_message(f"❌ Adaptive trailing error: {e}")
        await asyncio.sleep(15)



# 🕛 Автозапуск щоденного GPT-звіту о 23:59
async def auto_daily_report():
    while True:
        now = datetime.utcnow()
        if now.hour == 23 and now.minute == 59:
            generate_daily_report()
            await asyncio.sleep(60)
        await asyncio.sleep(30)


@app.on_event("startup")
async def start_all():
    threading.Thread(target=lambda: asyncio.run(monitor_cluster_trades())).start()
    threading.Thread(target=lambda: asyncio.run(adaptive_trailing_monitor())).start()
    threading.Thread(target=lambda: asyncio.run(auto_daily_report())).start()


# 🧠 Збереження останнього стопу для перевірки дублів
last_stop_price = {"LONG": None, "SHORT": None}


# 📍 Перенесення стопу на Binance (MARKET STOP)
def move_stop_to(symbol, side, new_stop_price):
    if DEBUG_MODE:
        send_message('🧪 DEBUG: move_stop_to — пропущено')
        return
try:
    pass
except:
    pass
except:
    pass
        pos = next((p for p in binance_client.futures_position_information(symbol=symbol)
                    if p["positionSide"] == side), None)
        if not pos or float(pos["positionAmt"]) == 0:
            return

        direction = "SELL" if side == "LONG" else "BUY"
        opposite = "BUY" if direction == "SELL" else "SELL"

        # Уникнути дублю
        if last_stop_price[side] == new_stop_price:
            send_message(f"⏸ Стоп вже виставлений на {new_stop_price}, пропускаємо")
            return

        # Видалити існуючі стопи
        open_orders = binance_client.futures_get_open_orders(symbol=symbol) if not DEBUG_MODE else []
        for order in open_orders:
            if order["positionSide"] == side and order["type"] in ["STOP_MARKET", "TAKE_PROFIT_MARKET"]:
        binance_client.futures_cancel_order(symbol=symbol, orderId=order["orderId"])
    else:
        send_message('🧪 DEBUG: Скасування ордера — пропущено')

        # Виставити новий стоп
        binance_client.futures_create_order(
            symbol=symbol,
            side=opposite,
            type='STOP_MARKET',
            stopPrice=new_stop_price,
            closePosition=True,
            timeInForce='GTC',
            positionSide=side
        )
    else:
        send_message('🧪 DEBUG: Спроба відкриття ордера — пропущено')
        last_stop_price[side] = new_stop_price
        send_message(f"🛑 Новий стоп ({side}) на {new_stop_price}")
    except Exception as e:
        send_message(f"❌ move_stop_to помилка: {e}")


async def adaptive_trailing_monitor():
    while True:
try:
    pass
except:
    pass
            positions = binance_client.futures_position_information(symbol="BTCUSDT")
            for side in ["LONG", "SHORT"]:
                pos = next((p for p in positions if p["positionSide"] == side), None)
                if pos and float(pos["positionAmt"]) != 0:
                    entry = float(pos["entryPrice"])
                    mark = float(binance_client.futures_mark_price(symbol="BTCUSDT")["markPrice"])
                    profit_pct = (mark - entry) / entry * 100 if side == "LONG" else (entry - mark) / entry * 100

                    sorted_clusters = sorted(cluster_data.items(), key=lambda x: x[0], reverse=True)
                    summary = "\n".join(
                        f"{int(price)}$: BUY {data['buy']:.2f} | SELL {data['sell']:.2f}"
                        for price, data in sorted_clusters
                    )
                    prompt = f"""
Позиція: {side}
Entry: {entry}
Mark: {mark}
Профіт: {profit_pct:.2f}%
Кластери:
{summary}

Що зробити зі стопом?
- MOVE_STOP_TO_X (вкажи ціну)
- KEEP_STOP
- CLOSE_POSITION
"""
                    res = client.chat.completions.create(
                        model="gpt-4-turbo",
                        messages=[
                            {"role": "system", "content": "Ти трейдинг-помічник. Вибери: MOVE_STOP_TO_X, KEEP_STOP або CLOSE_POSITION."},
                            {"role": "user", "content": prompt}
                        ]
                    )
                    decision = res.choices[0].message.content.strip()
                    send_message(f"🤖 GPT Stop Decision: {decision}")

                    if decision.startswith("MOVE_STOP_TO_"):
                        price_str = decision.split("_")[-1]
try:
    pass
except:
    pass
                            new_price = float(price_str)
                            move_stop_to("BTCUSDT", side, new_price)
except:
                            send_message("❗ Не вдалося розпізнати новий STOP")
                    elif decision == "CLOSE_POSITION":
        binance_client.futures_create_order(
                            symbol="BTCUSDT",
                            side="SELL" if side == "LONG" else "BUY",
                            type="MARKET",
                            quantity=abs(float(pos["positionAmt"])
    else:
        send_message('🧪 DEBUG: Спроба відкриття ордера — пропущено')),
                            positionSide=side
                        )
                        send_message(f"❌ Закрили позицію {side} по рішенню GPT")

except Exception as e:
            send_message(f"❌ adaptive_trailing_monitor error: {e}")
        await asyncio.sleep(15)

def log_gpt_decision(raw_signal, gpt_decision):
    pass
try:
    pass
except:
    pass
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name("/etc/secrets/credentials.json", scope)
        gclient = gspread.authorize(creds)
        sheet = gclient.open_by_key(GOOGLE_SHEET_ID).worksheets()[0]
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        row = [now, "GPT_DECISION", "", "", "", "", "", f"{raw_signal} → {gpt_decision}"]
        sheet.append_row(row)
except:
        pass
