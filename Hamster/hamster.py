# Hamster/hamster.py
import os
import json
import urllib.parse
import requests
import hashlib
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.messages import RequestAppWebViewRequest
from telethon.tl.types import InputBotAppShortName

api_id = int(os.environ["TG_API_ID"])
api_hash = os.environ["TG_API_HASH"]
session_str = os.environ["TG_SESSION"]

BASE_API = "https://hk-game-api.hwgame.cloud"

# Эндпоинты, которые могут использоваться для входа
ENDPOINTS = [
    "/auth/auth-by-telegram-webapp",
    "/auth/me-telegram",
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

def generate_fingerprint():
    """
    Генерирует псевдо-fingerprint, имитируя поведение браузера.
    В реальности это хеш от комбинации User-Agent, разрешения экрана и т.д.
    Для теста используем простой хеш.
    """
    # Простой хеш от строки (для демонстрации)
    # В реальной игре fingerprint может быть сложнее.
    raw = "Mozilla/5.0 (Linux; Android 13; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36|412x915|24"
    return hashlib.sha256(raw.encode()).hexdigest()

def try_auth(init_data):
    print(f"[*] initData length: {len(init_data)}")
    fingerprint = generate_fingerprint()
    print(f"[*] Сгенерирован fingerprint: {fingerprint[:16]}...")

    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Linux; Android 13; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36",
        "Accept": "application/json",
        "Origin": "https://hamsterking.games",
        "Referer": "https://hamsterking.games/"
    }

    for endpoint in ENDPOINTS:
        url = BASE_API + endpoint
        print(f"\n[?] Проверяем: {url}")

        # Варианты тела запроса с fingerprint
        bodies = [
            {"initData": init_data, "fingerprint": fingerprint},
            {"initData": init_data, "fingerprint": fingerprint, "hash": fingerprint},
            {"initData": init_data, "fingerprint": fingerprint, "user": json.loads(urllib.parse.unquote(init_data.split('user=')[1].split('&')[0]))},
        ]

        for body in bodies:
            try:
                resp = requests.post(url, json=body, headers=headers, timeout=10)
                print(f"  -> POST {endpoint} с fingerprint -> {resp.status_code}")
                if resp.status_code == 200:
                    print(f"  🎯 УСПЕХ! Ответ: {resp.text[:500]}")
                    return resp
                elif resp.status_code not in (404, 405):
                    print(f"     Ответ сервера: {resp.text[:200]}")
            except Exception as e:
                print(f"  [!] Ошибка: {e}")

    return None

async def main():
    print("[*] Получаем initData...")
    init_data = await get_initdata()
    print(f"[+] initData len: {len(init_data)}")
    print(f"[+] initData head: {init_data[:80]}...\n")

    result = try_auth(init_data)

    if result:
        print("\n[!!!] УСПЕХ! Сервер принял аутентификацию.")
        print(f"Статус: {result.status_code}")
        print(f"Тело ответа: {result.text[:1000]}")
    else:
        print("\n[!] Ни один эндпоинт с fingerprint не сработал.")
        print("[!] Возможно, игра использует другой метод или требует реальный отпечаток браузера.")

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())