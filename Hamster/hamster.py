import os
import asyncio
import urllib.parse
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.messages import RequestAppWebViewRequest
from telethon.tl.types import InputBotAppShortName
from playwright.async_api import async_playwright

api_id = int(os.environ.get("TG_API_ID"))
api_hash = os.environ.get("TG_API_HASH")
session_str = os.environ.get("TG_SESSION")

async def main():
    print("Подключаемся к Telegram через Telethon...")
    client = TelegramClient(StringSession(session_str), api_id, api_hash)
    await client.connect()

    if not await client.is_user_authorized():
        print("❌ Сессия не авторизована.")
        return

    try:
        bot_username = "hamsterking_game_bot"
        print(f"Ищем бота @{bot_username}...")
        bot = await client.get_entity(bot_username)
        input_user = await client.get_input_entity(bot)
        
        app = InputBotAppShortName(bot_id=input_user, short_name="start")
        web_view = await client(RequestAppWebViewRequest(
            peer=input_user,
            app=app,
            platform="android",
            write_allowed=True
        ))
        
        game_url = web_view.url
        print(f"✅ Получена ссылка на игру: {game_url[:60]}...")

        print("Запускаем Playwright...")
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                viewport={"width": 390, "height": 844},
                user_agent="Mozilla/5.0 (Linux; Android 13; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Mobile Safari/537.36"
            )
            page = await context.new_page()

            print("Открываем игру напрямую...")
            await page.goto(game_url)
            
            print("Ждем загрузки игры (15 секунд)...")
            await page.wait_for_timeout(15000) 

            print("Делаем скриншот игры...")
            await page.screenshot(path="Hamster/game_screenshot.png")
            print("Готово!")
            
            await browser.close()
    except Exception as e:
        print(f"❌ Ошибка: {e}")
    finally:
        await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())