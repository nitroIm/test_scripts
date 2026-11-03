# Hamster/hamster.py
import os
import re
import urllib.parse
import requests
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.messages import RequestAppWebViewRequest
from telethon.tl.types import InputBotAppShortName

api_id = int(os.environ["TG_API_ID"])
api_hash = os.environ["TG_API_HASH"]
session_str = os.environ["TG_SESSION"]

JS_URLS = [
    "https://cdn-prod-front-dist.hwgame.cloud/assets/app_2104.js",
    "https://cdn-prod-front-dist.hwgame.cloud/assets/deps-DN0_KosA.js"
]

# Ключевые слова, вокруг которых мы будем искать контекст
KEYWORDS = ["auth", "login", "tgWebAppData", "hk-game-api", "telegram"]

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

def analyze_js():
    print("[*] Скачиваем JS файлы и ищем контекст...")
    
    for url in JS_URLS:
        filename = url.split('/')[-1]
        try:
            print(f"\n==========================================")
            print(f"[*] Анализ файла: {filename}")
            print(f"==========================================")
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
            text = resp.text
            
            for kw in KEYWORDS:
                # Ищем все вхождения ключевого слова (регистронезависимо)
                matches = [m.start() for m in re.finditer(kw, text, re.IGNORECASE)]
                if not matches:
                    continue
                
                print(f"\n[+] Найдено {len(matches)} вхождений слова '{kw}':")
                # Берем первые 5 вхождений для анализа, чтобы не заспамить лог
                for i, pos in enumerate(matches[:5]):
                    start = max(0, pos - 100)
                    end = min(len(text), pos + 150)
                    snippet = text[start:end]
                    
                    # Чистим переносы строк для красивого вывода
                    snippet = snippet.replace('\n', ' ')
                    
                    print(f"\n  --- Вхождение #{i+1} ---")
                    print(f"  ...{snippet}...")
                    
        except Exception as e:
            print(f"[!] Ошибка обработки {url}: {e}")

async def main():
    print("[*] Получаем initData...")
    init_data = await get_initdata()
    print(f"[+] initData len: {len(init_data)}")
    print(f"[+] initData head: {init_data[:50]}...")

    print("\n[*] Запускаем анализ JS...")
    analyze_js()
    print("\n[!] Анализ завершен. Ждем лог.")

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())