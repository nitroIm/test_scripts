import os
import asyncio
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

        print("Запускаем Playwright...")
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                viewport={"width": 390, "height": 844},
                user_agent="Mozilla/5.0 (Linux; Android 13; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Mobile Safari/537.36"
            )
            page = await context.new_page()

            print("Открываем стартовый экран...")
            await page.goto(game_url)
            await page.wait_for_timeout(5000) 

            print("Ищем кнопку и кликаем...")
            try:
                # Ждем, пока откроется НОВАЯ вкладка после клика
                async with context.expect_page(timeout=15000) as new_page_info:
                    await page.locator('text="PLAY NOW in BROWSER!"').click(timeout=10000)
                
                # Переключаемся на новую вкладку
                new_page = await new_page_info.value
                print("✅ Открылась новая вкладка! Ждем загрузки игры (25 секунд)...")
                await new_page.wait_for_timeout(25000)
                
                print("Делаем скриншот новой вкладки...")
                await new_page.screenshot(path="Hamster/game_screenshot.png")
                
            except Exception as e:
                print(f"⚠️ Новая вкладка не открылась или кнопка не найдена: {e}")
                print("Делаем скриншот текущей страницы...")
                await page.screenshot(path="Hamster/game_screenshot.png")

            print("Готово!")
            await browser.close()
    except Exception as e:
        print(f"❌ Ошибка: {e}")
    finally:
        await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())