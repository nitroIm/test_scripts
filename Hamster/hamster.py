# Hamster/hamster.py
import os
import re
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

API_BASE = "https://hk-game-api.hwgame.cloud"
JS_URLS = [
    "https://cdn-prod-front-dist.hwgame.cloud/assets/app_2104.js",
    "https://cdn-prod-front-dist.hwgame.cloud/assets/deps-DN0_KosA.js"
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

def extract_endpoints_from_js():
    found_endpoints = set()
    print("[*] Скачиваем JS файлы для поиска эндпоинтов...")
    
    for url in JS_URLS:
        try:
            print(f"  -> {url.split('/')[-1]}")
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            text = resp.text
            
            # Ищем строки, похожие на API пути: /api/v1/user, /auth/tg, /login и т.д.
            # Паттерн ищет строки в кавычках, начинающиеся с /
            matches = re.findall(r'["\'](/[a-zA-Z0-9_\-/]{3,50})["\']', text)
            
            for m in matches:
                # Фильтруем мусор (картинки, скрипты, css)
                if any(m.endswith(ext) for ext in ['.js', '.css', '.png', '.jpg', '.svg', '.woff2', '.html']):
                    continue
                # Нас интересуют пути с auth, login, user, profile, api
                if any(keyword in m.lower() for keyword in ['auth', 'login', 'user', 'profile', 'api', 'tg', 'telegram']):
                    found_endpoints.add(m)
        except Exception as e:
            print(f"    [!] Ошибка скачивания: {e}")

    return sorted(list(found_endpoints))

def test_endpoint(endpoint, init_data):
    url = API_BASE + endpoint
    print(f"\n[?] Проверяем: {endpoint}")
    
    headers_list = [
        {"Authorization": f"Bearer {init_data}"},
        {"X-Telegram-Init-Data": init_data},
        {"X-Init-Data": init_data},
        {"Content-Type": "application/json"}
    ]
    
    # Тестируем GET
    for headers in headers_list:
        try:
            resp = requests.get(url, headers=headers, timeout=5)
            if resp.status_code not in [404, 405, 403]:
                print(f"  🎯 GET {endpoint} -> {resp.status_code}")
                print(f"     headers: {list(headers.keys())}")
                print(f"     response: {resp.text[:300]}")
                return True
        except Exception:
            pass

    # Тестируем POST (с initData в теле и в заголовках)
    body_variants = [
        {"initData": init_data},
        {"init_data": init_data},
        {"tgWebAppData": init_data},
        {"data": init_data}
    ]
    
    for headers in headers_list:
        if "Content-Type" not in headers:
            headers["Content-Type"] = "application/json"
            
        for body in body_variants:
            try:
                resp = requests.post(url, headers=headers, json=body, timeout=5)
                if resp.status_code not in [404, 405, 403]:
                    print(f"  🎯 POST {endpoint} -> {resp.status_code}")
                    print(f"     headers: {list(headers.keys())}")
                    print(f"     body: {json.dumps(body, ensure_ascii=False)}")
                    print(f"     response: {resp.text[:300]}")
                    return True
            except Exception:
                pass
                
    print(f"  ❌ {endpoint} не отвечает (404/403).")
    return False

async def main():
    print("[*] Получаем initData...")
    init_data = await get_initdata()
    print(f"[+] initData len: {len(init_data)}")

    print("\n[*] Анализируем исходники игры...")
    endpoints = extract_endpoints_from_js()
    
    if not endpoints:
        print("[!] Не удалось найти эндпоинты в JS. Возможно, они обфусцированы.")
        return
        
    print(f"[+] Найдено {len(endpoints)} потенциальных путей:")
    for ep in endpoints:
        print(f"  - {ep}")

    print("\n[*] Начинаем перебор найденных эндпоинтов...")
    for ep in endpoints:
        # Пропускаем заведомо бесполезные пути
        if ep in ["/", "/api", "/assets", "/static"]:
            continue
        if test_endpoint(ep, init_data):
            # Если нашли рабочий эндпоинт, выходим, чтобы не спамить
            print("\n[!] Найден рабочий эндпоинт! Останавливаем перебор.")
            break

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())