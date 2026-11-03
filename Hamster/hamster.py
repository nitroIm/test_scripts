# Hamster/hamster.py
import os
import re
import requests
import urllib.parse
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.messages import RequestAppWebViewRequest
from telethon.tl.types import InputBotAppShortName

api_id = int(os.environ["TG_API_ID"])
api_hash = os.environ["TG_API_HASH"]
session_str = os.environ["TG_SESSION"]

# Скачиваем карту маршрутов и главные JS-файлы
TARGET_FILES = [
    "https://prod-route.hwgame.cloud/routes.json",
    "https://cdn-prod-front-dist.hwgame.cloud/assets/app_2104.js",
    "https://cdn-prod-front-dist.hwgame.cloud/assets/deps-DN0_KosA.js",
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

def analyze_files():
    headers = {"User-Agent": "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36"}
    
    for url in TARGET_FILES:
        print(f"\n==========================================")
        print(f"[*] Скачиваем: {url.split('/')[-1]}")
        print(f"==========================================")
        try:
            r = requests.get(url, headers=headers, timeout=15)
            if r.status_code != 200:
                print(f"[!] Ошибка HTTP {r.status_code}")
                continue
            text = r.text
            print(f"[+] Размер: {len(text)} символов")

            # Если это routes.json - просто выводим его
            if url.endswith(".json"):
                print("\n=== СОДЕРЖИМОЕ routes.json ===")
                print(text)
                continue

            # Ищем строки с ключевыми словами API
            lines = re.findall(r'["\']([^"\']{4,100})["\']', text)
            keywords = ["auth", "login", "token", "hwgame", "telegram", "user", "mini"]
            found = set()
            
            for line in lines:
                if any(kw in line.lower() for kw in keywords):
                    # Отсеиваем мусор (длинные строки с пробелами и CSS-классы)
                    if " " not in line and not line.startswith("#"):
                        found.add(line)
            
            print(f"\n[+] Найдено {len(found)} подозрительных строк:")
            for line in sorted(found):
                print(f"  -> {line}")
                
        except Exception as e:
            print(f"[!] Ошибка: {e}")

async def main():
    print("[*] Получаем initData...")
    init_data = await get_initdata()
    print(f"[+] initData len: {len(init_data)}")
    
    print("\n[*] Анализируем файлы...")
    analyze_files()
    print("\n[!] Анализ завершен.")

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())