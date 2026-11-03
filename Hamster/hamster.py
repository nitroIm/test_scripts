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

# Все известные эндпоинты авторизации из Telegram Mini Apps
ENDPOINTS = [
    "/auth",
    "/auth/telegram",
    "/auth/auth-by-telegram-webapp",
    "/auth/me-telegram",
    "/api/auth",
    "/api/auth/telegram",
    "/api/v1/auth",
    "/api/v1/auth/telegram",
    "/login",
    "/login/telegram",
    "/telegram/login",
    "/user/auth",
    "/user/login",
]

# Все варианты полей, куда игра может ждать initData
BODY_FIELDS = ["initData", "init_data", "initDataRaw", "tgWebAppData", "data", "query"]

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

def try_auth(init_data):
    print(f"[*] initData length: {len(init_data)}")
    print("[*] Начинаем полный перебор комбинаций...\n")

    # Заголовки
    headers_list = [
        {"Content-Type": "application/json"},
        {"Content-Type": "application/json", "X-Telegram-Init-Data": init_data},
        {"Content-Type": "application/json", "Authorization": f"Bearer {init_data}"},
        {"Content-Type": "application/x-www-form-urlencoded"},
    ]

    for endpoint in ENDPOINTS:
        url = BASE_API + endpoint
        print(f"[?] Проверяем: {url}")

        # 1. POST с JSON и разными полями
        for field in BODY_FIELDS:
            body = {field: init_data}
            for headers in headers_list:
                if "x-www-form-urlencoded" in headers.get("Content-Type", ""):
                    continue
                try:
                    resp = requests.post(url, json=body, headers=headers, timeout=5)
                    if resp.status_code not in (404, 405):
                        print(f"  🎯 POST {endpoint} -> {resp.status_code}")
                        print(f"     Headers: {list(headers.keys())}")
                        print(f"     Body field: {field}")
                        print(f"     Response: {resp.text[:300]}")
                        if resp.status_code == 200:
                            return resp
                except Exception:
                    pass

        # 2. POST с form-data
        for field in BODY_FIELDS:
            data = {field: init_data}
            headers = {"Content-Type": "application/x-www-form-urlencoded"}
            try:
                resp = requests.post(url, data=data, headers=headers, timeout=5)
                if resp.status_code not in (404, 405):
                    print(f"  🎯 POST (form) {endpoint} -> {resp.status_code}")
                    print(f"     Body field: {field}")
                    print(f"     Response: {resp.text[:300]}")
                    if resp.status_code == 200:
                        return resp
            except Exception:
                pass

        # 3. GET с заголовками
        for headers in headers_list:
            if "x-www-form-urlencoded" in headers.get("Content-Type", ""):
                continue
            try:
                resp = requests.get(url, headers=headers, timeout=5)
                if resp.status_code not in (404, 405):
                    print(f"  🎯 GET {endpoint} -> {resp.status_code}")
                    print(f"     Headers: {list(headers.keys())}")
                    print(f"     Response: {resp.text[:300]}")
                    if resp.status_code == 200:
                        return resp
            except Exception:
                pass

        print(f"  ❌ {endpoint} — все варианты дали 404/405.\n")

    return None

async def main():
    print("[*] Получаем initData...")
    init_data = await get_initdata()
    print(f"[+] initData len: {len(init_data)}")
    print(f"[+] initData head: {init_data[:80]}...\n")

    result = try_auth(init_data)

    if result:
        print("\n[!!!] УСПЕХ! Сервер ответил.")
        print(f"Статус: {result.status_code}")
        print(f"Тело ответа: {result.text[:1000]}")
    else:
        print("\n[!] Ни одна комбинация не сработала.")
        print("[!] Возможно, игра использует WebSocket или требует fingerprint.")

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())