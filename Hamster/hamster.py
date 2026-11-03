# Hamster/hamster.py
import os
import json
import urllib.parse
import requests
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.messages import RequestAppWebViewRequest
from telethon.tl.types import InputBotAppShortName

api_id = int(os.environ["TG_API_ID"])
api_hash = os.environ["TG_API_HASH"]
session_str = os.environ["TG_SESSION"]

BASE_API = "https://hk-game-api.hwgame.cloud"

# Список самых вероятных эндпоинтов авторизации в играх Telegram Mini Apps
ENDPOINTS = [
    "/auth",
    "/login",
    "/auth/login",
    "/api/auth",
    "/api/v1/auth",
    "/user/auth",
    "/telegram/auth",
    "/auth/telegram",
    "/user/login",
    "/me"
]

async def get_initdata():
    client = TelegramClient(StringSession(session_str), api_id, api_hash)
    await client.connect()
    bot = await client.get_entity("hamsterking_game_bot")
    input_user = await client.get_input_entity(bot)
    app = InputBotAppShortName(bot_id=input_user, short_name="start")
    web_view = await client(RequestAppWebViewRequest(
        peer=input_user, app=app, platform="android", write_allowed=True
    ))
    game_url = web_view.url
    init_data = urllib.parse.unquote(
        game_url.split("tgWebAppData=")[1].split("&tgWebAppVersion")[0]
    )
    await client.disconnect()
    return init_data

def test_auth(init_data):
    print("[*] Начинаем тестирование эндпоинтов авторизации...")
    
    # Варианты заголовков
    headers_list = [
        {
            "Content-Type": "application/json", 
            "Authorization": f"Bearer {init_data}"
        },
        {
            "Content-Type": "application/json", 
            "X-Telegram-Init-Data": init_data
        },
        {
            "Content-Type": "application/json", 
            "X-Init-Data": init_data
        },
        {
            "Content-Type": "application/x-www-form-urlencoded"
        }
    ]

    # Варианты тела запроса
    bodies = [
        {"initData": init_data},
        {"init_data": init_data},
        {"tgWebAppData": init_data},
        f"initData={urllib.parse.quote(init_data)}", # Для form-data
        f"init_data={urllib.parse.quote(init_data)}"
    ]

    for endpoint in ENDPOINTS:
        url = BASE_API + endpoint
        print(f"\n[?] Проверяем: {url}")
        
        for headers in headers_list:
            for body in bodies:
                try:
                    # Если передаем строку, используем data=, иначе json=
                    if isinstance(body, str):
                        resp = requests.post(url, headers=headers, data=body, timeout=5)
                    else:
                        resp = requests.post(url, headers=headers, json=body, timeout=5)
                    
                    # 404 значит, что такого пути нет. Нас интересуют 200, 400, 401, 403, 422
                    if resp.status_code != 404:
                        print(f"  🎯 НАЙДЕН ОТВЕТ! Код: {resp.status_code}")
                        print(f"     Headers: {list(headers.keys())}")
                        print(f"     Body: {str(body)[:100]}")
                        print(f"     Response: {resp.text[:300]}")
                        
                        # Если 200 OK, значит мы авторизовались
                        if resp.status_code == 200:
                            print("\n[!!!] УСПЕХ! Мы получили токен или данные пользователя.")
                            return True
                except Exception:
                    pass
        print(f"  ❌ Все варианты для {endpoint} дали 404.")

    return False

async def main():
    print("[*] Получаем initData...")
    init_data = await get_initdata()
    print(f"[+] initData len: {len(init_data)}")
    
    success = test_auth(init_data)
    
    if not success:
        print("\n[!] Не удалось найти эндпоинт. Возможно, игра использует WebSocket для авторизации.")
        print("[!] Тогда нам нужно вернуться к перехвату WebSocket.")

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())