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

        print("Запускаем Playwright...")
        async with async_playwright() as p:
            # Запускаем с флагами для рендеринга графики
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--use-gl=angle", 
                    "--use-angle=swiftshader", 
                    "--enable-unsafe-swiftshader",
                    "--disable-web-security"
                ]
            )
            context = await browser.new_context(
                viewport={"width": 390, "height": 844},
                user_agent="Mozilla/5.0 (Linux; Android 13; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Mobile Safari/537.36"
            )
            
            # Подделываем видеокарту, чтобы игра думала, что мы на телефоне
            await context.add_init_script("""
                const getParameter = WebGLRenderingContext.prototype.getParameter;
                WebGLRenderingContext.prototype.getParameter = function(parameter) {
                    if (parameter === 37445) return 'Qualcomm';
                    if (parameter === 37446) return 'Adreno (TM) 660';
                    return getParameter.apply(this, arguments);
                };
            """)

            page = await context.new_page()
            intercepted_data = []

            # 1. Слушаем WebSockets (там летят данные игры)
            def handle_websocket(ws):
                print(f"\n🌐 WEBSOCKET ПОДКЛЮЧЕН: {ws.url}")
                ws.on("framesent", lambda payload: print(f"⬆️ ОТПРАВЛЕНО: {str(payload)[:500]}"))
                ws.on("framereceived", lambda payload: print(f"⬇️ ПОЛУЧЕНО: {str(payload)[:500]}"))

            page.on("websocket", handle_websocket)

            # 2. Слушаем HTTP-запросы (JSON)
            async def handle_response(response):
                try:
                    if response.request.resource_type in ["xhr", "fetch"]:
                        text = await response.text()
                        if len(text) > 50:
                            intercepted_data.append({"url": response.url, "data": text})
                            if "balance" in text.lower() or "user" in text.lower():
                                print(f"\n🎯 HTTP ЗАПРОС: {response.url}")
                                print(f"Данные: {text[:500]}...")
                except:
                    pass

            page.on("response", handle_response)

            print("Открываем игру...")
            await page.goto(game_url)
            
            print("Ждем загрузки (40 секунд)...")
            await page.wait_for_timeout(40000)
            
            print(f"URL после загрузки: {page.url}")

            # Сохраняем скриншот и HTML на всякий случай
            await page.screenshot(path="Hamster/game_screenshot.png")
            with open("Hamster/page_debug.html", "w", encoding="utf-8") as f:
                f.write(await page.content())
                
            with open("Hamster/network_log.json", "w", encoding="utf-8") as f:
                json.dump(intercepted_data, f, indent=2, ensure_ascii=False)

            print("Готово!")
            await browser.close()
            
    except Exception as e:
        print(f"❌ Ошибка: {e}")
    finally:
        await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())