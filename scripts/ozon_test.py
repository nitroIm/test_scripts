import os
import requests

CLIENT_ID = os.environ.get("OZON_CLIENT_ID")
API_KEY = os.environ.get("OZON_API_KEY")

url = "https://api-seller.ozon.ru/v3/product/list"
headers = {
    "Client-Id": CLIENT_ID,
    "Api-Key": API_KEY,
    "Content-Type": "application/json"
}
payload = {
    "filter": {},
    "last_id": "",
    "limit": 10
}

print("Отправляем запрос в Ozon...")
resp = requests.post(url, headers=headers, json=payload, timeout=30)

print("Статус ответа:", resp.status_code)
print("Данные от Ozon:", resp.json())