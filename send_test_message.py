import requests

TOKEN = "8030743406:AAEt9TpVL1vQ9PQ_2yjzrI3zQIJRdOugedk"
CHAT_ID = "5606817883"
TEXT = "Бот працює! 🎉"

url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
data = {
    "chat_id": CHAT_ID,
    "text": TEXT
}

response = requests.post(url, data=data)
print(response.json())
