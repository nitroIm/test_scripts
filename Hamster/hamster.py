import os
import asyncio
import json
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

        # Вытаскиваем initData
        init_data = urllib.parse.unquote(game_url.split("tgWebAppData=")[1].split("&tgWebAppVersion")[0])
        params = dict(urllib.parse.parse_qsl(init_data))
        
        # Формируем правильный initDataUnsafe
        init_data_unsafe = {
            "query_id": params.get("query_id", ""),
            "user": json.loads(params.get("user", "{}")),
            "auth_date": params.get("auth_date", ""),
            "hash": params.get("hash", "")
        }
        
        direct_url = f"https://cdn-prod-front.hwgame.cloud/app_2104.html#tgWebAppData={urllib.parse.quote(init_data)}"

        print("Запускаем Playwright...")
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=False, # Обязательно False для xvfb
                args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"]
            )
            
            # ИСПРАВЛЕНО: используем extra_http_headers вместо referer
            context = await browser.new_context(
                viewport={"width": 390, "height": 844},
                user_agent="Mozilla/5.0 (Linux; Android 13; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Mobile Safari/537.36",
                extra_http_headers={"Referer": "https://hamsterking.games/"}
            )

            # Внедряем фейковый Telegram
            script = f"""
                window.Telegram = {{
                    WebApp: {{
                        initData: "{init_data}",
                        initDataUnsafe: {json.dumps(init_data_unsafe)},
                        ready: function() {{}},
                        expand: function() {{}},
                        close: function() {{}},
                        platform: "android",
                        version: "9.6"
                    }}
                }};
            """
            await context.add_init_script(script)

            page = await context.new_page()

            # Слушаем WebSockets
            def handle_websocket(ws):
                print(f"\n🌐 WEBSOCKET ПОДКЛЮЧЕН: {ws.url}")
                ws.on("framereceived", lambda payload: print(f"⬇️ ПОЛУЧЕНО: {str(payload)[:300]}"))
                ws.on("framesent", lambda payload: print(f"⬆️ ОТПРАВЛЕНО: {str(payload)[:300]}"))

            page.on("websocket", handle_websocket)

            print("Загружаем игру...")
            await page.goto(direct_url, wait_until="domcontentloaded")
            
            # Ждем 50 секунд, чтобы Unity успел прогрузить все ресурсы и установить соединения
            print("Ждем загрузки игры и данных (50 секунд)...")
            await page.wait_for_timeout(50000)

            print(f"URL игры: {page.url}")
            print("Готово!")
            await browser.close()
            
    except Exception as e:
        print(f"❌ Ошибка: {e}")
    finally:
        await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())