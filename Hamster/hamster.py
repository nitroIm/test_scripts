# Hamster/hamster.py
import os
import re
import urllib.parse
import requests
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.messages import RequestAppWebViewRequest
from telethon.tl.types import InputBotAppShortName
from bs4 import BeautifulSoup

api_id = int(os.environ["TG_API_ID"])
api_hash = os.environ["TG_API_HASH"]
session_str = os.environ["TG_SESSION"]

BASE_HTML = "https://cdn-prod-front.hwgame.cloud/app_2104.html"

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

def analyze_all_js():
    print("[*] Скачиваем HTML игры...")
    headers = {"User-Agent": "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36"}
    resp = requests.get(BASE_HTML, headers=headers, timeout=15)
    resp.raise_for_status()
    
    soup = BeautifulSoup(resp.text, 'html.parser')
    scripts = soup.find_all('script')
    
    js_urls = set()
    for s in scripts:
        src = s.get('src')
        if src:
            if src.startswith('http'):
                js_urls.add(src)
            elif src.startswith('/'):
                js_urls.add("https://cdn-prod-front.hwgame.cloud" + src)
            else:
                js_urls.add("https://cdn-prod-front.hwgame.cloud/" + src)
                
    # Добавляем те, что видели в логах
    js_urls.add("https://cdn-prod-front-dist.hwgame.cloud/assets/app_2104.js")
    js_urls.add("https://cdn-prod-front-dist.hwgame.cloud/assets/deps-DN0_KosA.js")
    js_urls.add("https://cdn-prod-front.hwgame.cloud/assets/telegram-web-app.8.0-hotfix.js")

    print(f"[*] Найдено {len(js_urls)} JS файлов. Начинаем анализ...")
    
    found_endpoints = set()
    
    for url in js_urls:
        filename = url.split('/')[-1]
        try:
            r = requests.get(url, headers=headers, timeout=10)
            if r.status_code != 200:
                continue
            text = r.text
            
            # Ищем все URL-ы, начинающиеся с http или /
            # Паттерн ищет строки в кавычках, где есть http или слэш
            matches = re.findall(r'["\'](https?://[^"\']+|/[a-zA-Z0-9_\-/]+)["\']', text)
            
            for m in matches:
                # Отфильтровываем картинки, шрифты и прочий мусор
                if any(m.endswith(ext) for ext in ['.png', '.jpg', '.svg', '.woff2', '.css', '.js']):
                    continue
                # Оставляем только то, что похоже на API
                if any(kw in m.lower() for kw in ['auth', 'login', 'api', 'tg', 'telegram', 'user']):
                    found_endpoints.add((filename, m))
                    
        except Exception as e:
            print(f"  [!] Ошибка {filename}: {e}")

    print("\n=== НАЙДЕННЫЕ ПУТИ В JS ===")
    for fname, ep in sorted(found_endpoints):
        print(f"  [{fname}] {ep}")

    print("\n[*] Пробуем постучаться в найденные эндпоинты на hk-game-api...")
    test_endpoints = set()
    for fname, ep in found_endpoints:
        if ep.startswith('http'):
            if 'hwgame' in ep:
                test_endpoints.add(ep)
        else:
            test_endpoints.add("https://hk-game-api.hwgame.cloud" + ep)

    for url in test_endpoints:
        try:
            r = requests.get(url, headers=headers, timeout=5)
            if r.status_code != 404:
                print(f"  🎯 GET {url} -> {r.status_code}")
                print(f"     {r.text[:200]}")
        except Exception:
            pass

async def main():
    print("[*] Получаем initData...")
    init_data = await get_initdata()
    print(f"[+] initData len: {len(init_data)}")
    analyze_all_js()
    print("\n[!] Готово.")

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())