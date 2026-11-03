import os
import asyncio
import json
import urllib.parse
import aiohttp
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.messages import RequestAppWebViewRequest
from telethon.tl.types import InputBotAppShortName

api_id = int(os.environ.get("TG_API_ID"))
api_hash = os.environ.get("TG_API_HASH")
session_str = os.environ.get("TG_SESSION")

BOTS_TO_CHECK = ["hamster_kombat_bot", "hamsterking_game_bot"]

# Расширенный список доменов и путей
DOMAINS = [
    "https://api.hamsterkombat.io",
    "https://api.hamsterkombatgame.io",
    "https://api.hamsterverse.io",
    "https://api.hamsterking.io",
    "https://api.hamsterkombat.com",
]

PATHS = [
    "/clicker/sync",
    "/clicker/sync/",
    "/api/v1/clicker/sync",
    "/v1/clicker/sync",
    "/api/clicker/sync",
    "/clicker/sync-state",
    "/clicker/config",
    "/clicker/upgrades-for-buy",
]

METHODS = ["GET", "POST", "OPTIONS"]

# Разные наборы заголовков
HEADERS_SETS = {
    "base": {
        "User-Agent": "Mozilla/5.0 (Linux; Android 13; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Mobile Safari/537.36",
        "Origin": "https://hamsterkombatgame.io",
        "Referer": "https://hamsterkombatgame.io/",
    },
    "with_sec_ch_ua": {
        "User-Agent": "Mozilla/5.0 (Linux; Android 13; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Mobile Safari/537.36",
        "Origin": "https://hamsterkombatgame.io",
        "Referer": "https://hamsterkombatgame.io/",
        "sec-ch-ua": '"Chromium";v="114", "Google Chrome";v="114", "Not=A?Brand";v="99"',
        "sec-ch-ua-mobile": "?1",
        "sec-ch-ua-platform": '"Android"',
    },
    "minimal": {
        "User-Agent": "Mozilla/5.0 (Linux; Android 13; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Mobile Safari/537.36",
    }
}

async def get_init_data(client, bot_username):
    try:
        bot = await client.get_entity(bot_username)
        input_user = await client.get_input_entity(bot)
        app = InputBotAppShortName(bot_id=input_user, short_name="start")
        
        web_view = await client(RequestAppWebViewRequest(
            peer=input_user,
            app=app,
            platform="android",
            write_allowed=True
        ))
        
        url = web_view.url
        if "tgWebAppData=" in url:
            init_data = url.split("tgWebAppData=")[1].split("&tgWebAppVersion")[0]
            return urllib.parse.unquote(init_data)
        return None
    except Exception as e:
        print(f"⚠️ Не удалось получить данные для {bot_username}: {e}")
        return None

async def try_request(session, method, url, headers, json_data=None):
    try:
        if method == "GET":
            async with session.get(url, headers=headers, timeout=5) as resp:
                return resp.status, await resp.text()
        elif method == "POST":
            async with session.post(url, headers=headers, json=json_data or {}, timeout=5) as resp:
                return resp.status, await resp.text()
        elif method == "OPTIONS":
            async with session.options(url, headers=headers, timeout=5) as resp:
                return resp.status, await resp.text()
    except Exception as e:
        return None, str(e)
    return None, "Unknown method"

async def main():
    print("Подключаемся к Telegram...")
    client = TelegramClient(StringSession(session_str), api_id, api_hash)
    await client.connect()

    if not await client.is_user_authorized():
        print("❌ Сессия не авторизована.")
        return

    for bot_name in BOTS_TO_CHECK:
        print(f"\n🔍 Проверяем бота: @{bot_name}...")
        init_data = await get_init_data(client, bot_name)
        
        if not init_data:
            print(f"❌ Токен для @{bot_name} не получен.")
            continue

        print(f"✅ Получен токен для @{bot_name}! Ищем рабочий API...")
        
        async with aiohttp.ClientSession() as session:
            for domain in DOMAINS:
                for path in PATHS:
                    url = domain + path
                    for method in METHODS:
                        for header_name, header_data in HEADERS_SETS.items():
                            headers = {
                                "Authorization": f"Bearer {init_data}",
                                "Content-Type": "application/json",
                                **header_data
                            }
                            
                            status, text = await try_request(session, method, url, headers)
                            
                            if status is not None:
                                print(f"🔍 {method} {url} [{header_name}] -> {status}")
                                if status == 200:
                                    print(f"🎯 НАЙДЕН РАБОЧИЙ API: {method} {url}")
                                    print(f"Headers: {header_name}")
                                    try:
                                        data = json.loads(text)
                                        print(json.dumps(data, indent=2)[:1000])
                                    except:
                                        print(f"Response: {text[:500]}")
                                    return # Выходим, если нашли рабочий
                                elif status == 405:
                                    print(f"⚠️ {url} ответил 405 (Метод не разрешен).")
                                elif status == 404:
                                    pass # Просто идем дальше
                                else:
                                    print(f"⚠️ {url} ответил {status}: {text[:100]}")
                            else:
                                # Если ошибка соединения, просто пропускаем
                                pass
        print(f"❌ Не удалось найти рабочий API для @{bot_name}.")

    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())