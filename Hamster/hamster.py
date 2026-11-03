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

# Список ботов для проверки
BOTS_TO_CHECK = [
    "hamster_kombat_bot",       # Основной бот (для GameDev Heroes)
    "hamsterking_game_bot",     # Бот для Hamster King (возможное имя)
    "hamster_king_bot"          # Альтернативное имя
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

    # Проходим по всем ботам из списка
    for bot_name in BOTS_TO_CHECK:
        print(f"\n🔍 Проверяем бота: @{bot_name}...")
        init_data = await get_init_data(client, bot_name)
        
        if init_data:
            print(f"✅ Получен токен для @{bot_name}!")
            
            # Пробуем синхронизироваться с API Hamster Kombat
            # (В HamsterVerse API часто общий, но пути могут отличаться)
            headers = {
                "Authorization": f"Bearer {init_data}",
                "Content-Type": "application/json"
            }
            
            async with aiohttp.ClientSession() as session:
                # Пробуем эндпоинт Hamster King (предположительный)
                # Если он не работает, мы увидим ошибку и сможем поискать другой путь
                url = "https://api.hamsterkombatgame.io/clicker/sync"
                if "king" in bot_name:
                     # Для Hamster King может быть другой эндпоинт, но начнем с базового
                     pass 
                
                async with session.post(url, headers=headers, json={}) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        balance = data.get("clickerUser", {}).get("balanceCoins", 0)
                        print(f"💰 Баланс: {balance}")
                    else:
                        print(f"❌ Ошибка API (Код {resp.status}): {await resp.text()}")
        else:
            print(f"❌ Токен для @{bot_name} не получен.")

    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())