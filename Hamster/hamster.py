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

# Список возможных новых адресов API для проверки
POSSIBLE_API_URLS = [
    "https://api.hamsterkombatgame.io/clicker/sync",
    "https://api.hamsterkombat.io/clicker/sync",
    "https://api.hamsterverse.io/clicker/sync",
    "https://api.hamsterkombatgame.io/hamsterverse/clicker/sync",
    "https://api.hamsterking.io/clicker/sync"
]

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
        
        headers = {
            "Authorization": f"Bearer {init_data}",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Linux; Android 13; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Mobile Safari/537.36"
        }
        
        found_working_url = False
        async with aiohttp.ClientSession() as session:
            for url in POSSIBLE_API_URLS:
                try:
                    async with session.post(url, headers=headers, json={}, timeout=5) as resp:
                        if resp.status == 200:
                            print(f"🎯 НАЙДЕН РАБОЧИЙ API: {url}")
                            data = await resp.json()
                            balance = data.get("clickerUser", {}).get("balanceCoins", "Н/Д")
                            print(f"💰 Баланс: {balance}")
                            found_working_url = True
                            break # Если нашли рабочий, дальше не проверяем
                        elif resp.status == 404:
                            pass # Просто идем к следующему
                        else:
                            print(f"⚠️ {url} ответил кодом {resp.status}")
                except Exception:
                    pass
            
            if not found_working_url:
                print(f"❌ Не удалось найти рабочий API для @{bot_name}. Все адреса вернули ошибку.")

    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())