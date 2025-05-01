
import os
import time
import asyncio
import aiohttp
import requests
from dotenv import load_dotenv
from binance.client import Client
import openai

# ⬇️ Завантаження змінних середовища
load_dotenv()

BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
BINANCE_SECRET_KEY = os.getenv("BINANCE_SECRET_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

openai.api_key = OPENAI_API_KEY
binance_client = Client(BINANCE_API_KEY, BINANCE_SECRET_KEY)

def send_telegram(text):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        data = {{"chat_id": CHAT_ID, "text": text}}
        requests.post(url, data=data)
    except Exception as e:
        print(f"Telegram error: {e}")

WATCHLIST = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT", "LINAUSDT", "MATICUSDT", "ADAUSDT", "AVAXUSDT",
    "DOTUSDT", "TRXUSDT", "LINKUSDT", "ATOMUSDT", "SANDUSDT", "APEUSDT", "INJUSDT", "RNDRUSDT", "1000SATSUSDT", "IDUSDT",
    "GALAUSDT", "CVCUSDT", "RLCUSDT", "BLZUSDT", "OPUSDT", "ARKMUSDT", "DYDXUSDT", "PEOPLEUSDT", "ENSUSDT", "AGIXUSDT",
    "TLMUSDT", "LITUSDT", "COTIUSDT", "LQTYUSDT", "STMXUSDT", "ANKRUSDT", "CHRUSDT", "CFXUSDT", "SXPUSDT", "NKNUSDT"
]

SPREAD_THRESHOLD = 0.3  # %
open_positions = {{}}

async def fetch_price(session, url):
    try:
        async with session.get(url) as resp:
            return await resp.json()
    except Exception as e:
        print(f"❌ fetch_price error: {e}")
        return None

async def monitor_spreads():
    while True:
        async with aiohttp.ClientSession() as session:
            for symbol in WATCHLIST:
                try:
                    spot_url = f"https://api.binance.com/api/v3/ticker/price?symbol={{symbol}}"
                    futures_url = f"https://fapi.binance.com/fapi/v1/ticker/price?symbol={{symbol}}"

                    spot_data = await fetch_price(session, spot_url)
                    fut_data = await fetch_price(session, futures_url)

                    if not spot_data or not fut_data:
                        continue

                    spot_price = float(spot_data["price"])
                    fut_price = float(fut_data["price"])
                    spread = (fut_price - spot_price) / spot_price * 100

                    print(f"{symbol} | Spot: {spot_price} | Fut: {fut_price} | Spread: {spread:.3f}%")

                    if open_positions:
                        continue

                    if spread >= SPREAD_THRESHOLD:
                        send_telegram(f"📊 {symbol} → Спред: {spread:.3f}% | Спот: {spot_price} | Фʼючерс: {fut_price}")
                        await analyze_with_gpt(symbol, spot_price, fut_price, spread)

                    await asyncio.sleep(0.2)
                except Exception as e:
                    print(f"❌ Error in monitor loop for {symbol}: {e}")
        await asyncio.sleep(5)

async def analyze_with_gpt(symbol, spot_price, fut_price, spread):
    try:
        prompt = (
            f"Монета: {symbol}\n"
            f"Ціна спот: {spot_price}\n"
            f"Ціна фʼючерс: {fut_price}\n"
            f"Спред: {spread:.3f}%\n\n"
            f"Чи варто відкривати арбітражну позицію (купити на споті, продати на фʼючерсі)?\n"
            f"Відповідай одним словом: ВХІД або СКИП"
        )

        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {{"role": "system", "content": "Ти досвідчений трейдер-арбітражник. Відповідай лише 'ВХІД' або 'СКИП'."}},
                {{"role": "user", "content": prompt}}
            ]
        )

        decision = response.choices[0].message.content.strip().upper()
        send_telegram(f"🤖 GPT по {symbol}: {decision}")

        if decision == "ВХІД":
            await open_position(symbol, spot_price, fut_price)

    except Exception as e:
        print(f"❌ GPT analyze error for {symbol}: {e}")

async def open_position(symbol, spot_price, fut_price):
    try:
        if open_positions:
            print(f"⚠️ Вже є позиція — {symbol} пропущено")
            return

        usdt_amount = 100
        qty = round(usdt_amount / spot_price, 2)

        binance_client.order_market_buy(symbol=symbol, quantity=qty)
        binance_client.futures_create_order(symbol=symbol, side='SELL', type='MARKET', quantity=qty)

        open_positions[symbol] = {{
            "spot_entry": spot_price,
            "futures_entry": fut_price,
            "qty": qty,
            "timestamp": time.time()
        }}

        print(f"✅ ВІДКРИТО {symbol} | К-сть: {qty} | Спот: {spot_price} | Фʼючерс: {fut_price}")
        send_telegram(f"✅ ВІДКРИТО {symbol} | К-сть: {qty} | Спот: {spot_price} | Фʼючерс: {fut_price}")

    except Exception as e:
        print(f"❌ open_position error: {e}")

async def monitor_open_position():
    while True:
        await asyncio.sleep(5)
        if not open_positions:
            continue

        symbol = list(open_positions.keys())[0]
        pos = open_positions[symbol]
        qty = pos["qty"]

        try:
            spot_price = float(binance_client.get_symbol_ticker(symbol=symbol)["price"])
            fut_price = float(binance_client.futures_symbol_ticker(symbol=symbol)["price"])
            spread_now = (fut_price - spot_price) / spot_price * 100

            print(f"🔄 [{symbol}] Поточний спред: {spread_now:.3f}%")

            if spread_now <= 0.1:
                binance_client.order_market_sell(symbol=symbol, quantity=qty)
                binance_client.futures_create_order(symbol=symbol, side='BUY', type='MARKET', quantity=qty)
                print(f"✅ ЗАКРИТО {symbol} | Поточний спред: {spread_now:.3f}%")
                send_telegram(f"✅ ЗАКРИТО {symbol} | Поточний спред: {spread_now:.3f}%")
                open_positions.clear()

        except Exception as e:
            print(f"❌ monitor_open_position error: {e}")

async def main():
    task1 = asyncio.create_task(monitor_spreads())
    task2 = asyncio.create_task(monitor_open_position())
    await asyncio.gather(task1, task2)

if __name__ == "__main__":
    try:
        print("🚀 Хедж-бот запущено!")
        asyncio.run(main())
    except KeyboardInterrupt:
        print("🛑 Бот зупинено вручну.")
