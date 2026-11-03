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

        print("Запускаем Playwright и слушаем сетевые запросы...")
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                viewport={"width": 390, "height": 844},
                user_agent="Mozilla/5.0 (Linux; Android 13; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Mobile Safari/537.36"
            )
            page = await context.new_page()

            # Функция, которая будет ловить все ответы от сервера
            async def handle_response(response):
                # Нас интересуют только JSON файлы и запросы к API
                if response.request.resource_type in ["xhr", "fetch"]:
                    try:
                        text = await response.text()
                        # Если ответ похож на данные игры (там есть баланс или здания)
                        if "balance" in text.lower() or "coins" in text.lower() or "upgrade" in text.lower() or "user" in text.lower():
                            print(f"\n🎯 ПЕРЕХВАЧЕН ЗАПРОС: {response.url}")
                            print(f"Данные: {text[:1000]}...") # Выводим первые 1000 символов
                            print("-" * 50)
                    except:
                        pass

            # Привязываем слушатель к странице
            page.on("response", handle_response)

            print("Открываем стартовый экран...")
            await page.goto(game_url)
            await page.wait_for_timeout(5000) 

            print("Ищем кнопку и кликаем...")
            try:
                async with context.expect_page(timeout=15000) as new_page_info:
                    await page.locator('text="PLAY NOW in BROWSER!"').click(timeout=10000)
                
                new_page = await new_page_info.value
                # Привязываем слушатель и к новой вкладке
                new_page.on("response", handle_response)
                
                print("✅ Открылась новая вкладка! Ждем 40 секунд, пока игра загрузит данные...")
                await new_page.wait_for_timeout(40000)
                
                print("Игра загрузилась. Проверяем, что мы перехватили выше в логах.")
                    
            except Exception as e:
                print(f"⚠️ Ошибка: {e}")

            print("Готово!")
            await browser.close()
    except Exception as e:
        print(f"❌ Ошибка: {e}")
    finally:
        await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())