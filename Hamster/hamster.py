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

        print("Запускаем Playwright с программной видеокартой...")
        async with async_playwright() as p:
            # Включаем рендеринг графики для headless-режима
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--use-gl=angle", 
                    "--use-angle=swiftshader", 
                    "--enable-unsafe-swiftshader"
                ]
            )
            context = await browser.new_context(
                viewport={"width": 390, "height": 844},
                user_agent="Mozilla/5.0 (Linux; Android 13; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Mobile Safari/537.36"
            )
            page = await context.new_page()

            print("Открываем стартовый экран...")
            await page.goto(game_url)
            
            # Ждем, пока сайт сам перекинет на игру (редирект)
            print("Ждем автоматического перехода в игру...")
            try:
                # Ждем, пока URL не станет hamsterking.games (или пока не пройдет 20 сек)
                await page.wait_for_url("**/hamsterking.games/**", timeout=20000)
                print("✅ Переход выполнен! Ждем загрузки графики (25 секунд)...")
            except:
                print("⚠️ Автоматический переход не сработал. Пробуем нажать кнопку...")
                try:
                    await page.locator('text="PLAY NOW in BROWSER!"').click(timeout=5000)
                    print("Кнопка нажата. Ждем 25 секунд...")
                except:
                    pass
            
            await page.wait_for_timeout(25000)
            
            print("Делаем скриншот игры с включенной графикой...")
            await page.screenshot(path="Hamster/game_screenshot.png")
            print("Готово!")

            await browser.close()
    except Exception as e:
        print(f"❌ Ошибка: {e}")
    finally:
        await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())