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

API_BASE = "https://hk-game-api.hwgame.cloud"

# Возможные эндпоинты
ENDPOINTS = [
    "/", "/user", "/profile", "/me", "/auth", "/login", "/init",
    "/api/user", "/api/profile", "/api/auth", "/api/login", "/api/v1/user",
    "/v1/user", "/v1/profile", "/game/user", "/player", "/player/info"
]

# Заголовки для авторизации (пробуем разные)
def get_headers(init_data):
    return [
        {"Authorization": f"Bearer {init_data}"},
        {"X-Telegram-Init-Data": init_data},
        {"X-Init-Data": init_data},
        {"init-data": init_data},
        {"Authorization": init_data},
    ]

async def main():
    client = TelegramClient(StringSession(session_str), api_id, api_hash)
    await client.connect()

    if not await client.is_user_authorized():
        print("❌ Сессия не авторизована.")
        return

    try:
        bot = await client.get_entity("hamsterking_game_bot")
        input_user = await client.get_input_entity(bot)
        app = InputBotAppShortName(bot_id=input_user, short_name="start")
        
        web_view = await client(RequestAppWebViewRequest(
            peer=input_user, app=app, platform="android", write_allowed=True
        ))
        game_url = web_view.url

        init_data = urllib.parse.unquote(game_url.split("tgWebAppData=")[1].split("&tgWebAppVersion")[0])
        print(f"✅ Токен получен. Длина: {len(init_data)}")
        print(f"API база: {API_BASE}")

        headers_list = get_headers(init_data)

        async with aiohttp.ClientSession() as session:
            for endpoint in ENDPOINTS:
                url = API_BASE + endpoint
                for method in ["GET", "POST"]:
                    for headers in headers_list:
                        try:
                            if method == "GET":
                                async with session.get(url, headers=headers, timeout=10) as resp:
                                    status = resp.status
                                    if status == 200:
                                        text = await resp.text()
                                        print(f"\n🎯 GET {url} -> 200")
                                        print(f"Заголовки: {list(headers.keys())}")
                                        print(f"Данные: {text[:500]}")
                                        return
                                    elif status not in [404, 401, 403, 405]:
                                        print(f"⚠️ GET {url} -> {status}")
                            else:
                                async with session.post(url, headers=headers, json={}, timeout=10) as resp:
                                    status = resp.status
                                    if status == 200:
                                        text = await resp.text()
                                        print(f"\n🎯 POST {url} -> 200")
                                        print(f"Заголовки: {list(headers.keys())}")
                                        print(f"Данные: {text[:500]}")
                                        return
                                    elif status not in [404, 401, 403, 405]:
                                        print(f"⚠️ POST {url} -> {status}")
                        except Exception as e:
                            pass

            print("\n❌ Не удалось найти рабочий эндпоинт. Выводим все ответы для анализа...")
            
            # Последний шанс — стучимся в корень с разными заголовками и смотрим ответ
            for headers in headers_list:
                try:
                    async with session.get(API_BASE + "/", headers=headers, timeout=10) as resp:
                        print(f"\nGET / с {list(headers.keys())} -> {resp.status}")
                        print(await resp.text())
                except:
                    pass

    except Exception as e:
        print(f"❌ Ошибка: {e}")
    finally:
        await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())