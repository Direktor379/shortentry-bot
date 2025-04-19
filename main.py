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

# 📏 VWAP обрахунок
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

# 📉 Флет-фільтр
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
        data = sheet.get_all_values()[1:]  # без заголовка
        data.reverse()
        gpt_logs = [row for row in data if row[1] in ["LONG", "SHORT", "BOOSTED_LONG", "BOOSTED_SHORT"] and row[6]]
        recent = gpt_logs[:limit]
        result = [f"{i+1}. {row[1]} → {row[6]}" for i, row in enumerate(recent)]
        return "\n".join(result)
    except:
        return ""

def update_stats_sheet():
    try:
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
            stat_sheet = sh.worksheet("Stats")
            stat_sheet.clear()
        except:
            stat_sheet = sh.add_worksheet(title="Stats", rows="20", cols="5")

        stat_sheet.update("A1", stat_rows)

    except Exception as e:
        send_message(f"❌ Stats error: {e}")

# 🤖 GPT

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
    try:
        positions = binance_client.futures_position_information(symbol="BTCUSDT")
        pos = next((p for p in positions if p["positionSide"] == side), None)
        return pos and float(pos["positionAmt"]) != 0
    except:
        return False















