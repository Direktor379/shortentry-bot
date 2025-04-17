import requests

TOKEN = "8030743406:AAEt9TpVL1vQ9PQ_2yjzrI3zQIJRdOugedk"
url = f"https://api.telegram.org/bot{TOKEN}/getUpdates"

response = requests.get(url)
print(response.json())

