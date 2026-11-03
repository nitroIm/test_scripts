import os
import asyncio
import json
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.messages import RequestAppWebViewRequest
from telethon.tl.types import InputBotAppShortName
from playwright.async_api import async_playwright

api_id = int(os.environ.get("TG_API_ID"))
api_hash = os.environ.get("TG_API_HASH")
session_str = os.environ.get("TG_SESSION")

async def main():
    print("Подключаемся к Telegram...")
    client = TelegramClient(StringSession(session_str), api_id, api_hash)
    await client.connect()

    if not await client.is_user_authorized():
        print("❌ Сессия не авторизована.")
        return

    try:
        bot_username = "hamsterking_game_bot"
        bot = await client.get_entity(bot_username)
        input_user = await client.get_input_entity(bot)
        app = InputBotAppShortName(bot_id=input_user, short_name="start")
        
        web_view = await client(RequestAppWebViewRequest(
            peer=input_user, app=app, platform="android", write_allowed=True
        ))
        game_url = web_view.url
        print(f"Ссылка от Telegram: {game_url[:80]}...")

        # Извлекаем hash с токеном (tgWebAppData=...)
        if "#tgWebAppData=" in game_url:
            hash_part = game_url.split("#")[1]
            # Формируем ПРЯМУЮ ссылку на игру
            direct_url = f"https://cdn-prod-front.hwgame.cloud/app_2104.html#{hash_part}"
        else:
            print("❌ Токен не найден в ссылке.")
            return

        print(f"Открываем прямой URL: {direct_url[:80]}...")

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"]
            )
            context = await browser.new_context(
                viewport={"width": 390, "height": 844},
                user_agent="Mozilla/5.0 (Linux; Android 13; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Mobile Safari/537.36"
            )
            
            page = await context.new_page()

            # Слушаем WebSockets (там 100% будут данные игры)
            def handle_websocket(ws):
                print(f"\n🌐 WEBSOCKET: {ws.url}")
                ws.on("framereceived", lambda payload: print(f"⬇️ ПОЛУЧЕНО: {str(payload)[:500]}"))
                ws.on("framesent", lambda payload: print(f"⬆️ ОТПРАВЛЕНО: {str(payload)[:500]}"))

            page.on("websocket", handle_websocket)

            print("Загружаем игру...")
            await page.goto(direct_url)
            
            print("Ждем загрузки и обмена данными (40 секунд)...")
            await page.wait_for_timeout(40000)
            
            print(f"URL игры: {page.url}")

            # Вытаскиваем IndexedDB (там Unity хранит сохранения)
            print("\n🔍 Пытаемся вытащить данные из IndexedDB...")
            try:
                dbs = await page.evaluate("indexedDB.databases()")
                print(f"Найдено баз данных: {dbs}")
            except Exception as e:
                print(f"Ошибка IndexedDB: {e}")

            print("\nГотово!")
            await browser.close()
            
    except Exception as e:
        print(f"❌ Ошибка: {e}")
    finally:
        await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())