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

        init_data = urllib.parse.unquote(game_url.split("tgWebAppData=")[1].split("&tgWebAppVersion")[0])
        params = dict(urllib.parse.parse_qsl(init_data))
        
        init_data_unsafe = {
            "query_id": params.get("query_id", ""),
            "user": json.loads(params.get("user", "{}")),
            "auth_date": params.get("auth_date", ""),
            "hash": params.get("hash", "")
        }
        
        direct_url = f"https://cdn-prod-front.hwgame.cloud/app_2104.html#tgWebAppData={urllib.parse.quote(init_data)}"

        print("Запускаем Playwright с максимальным перехватом...")
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=False,
                args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"]
            )
            context = await browser.new_context(
                viewport={"width": 390, "height": 844},
                user_agent="Mozilla/5.0 (Linux; Android 13; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Mobile Safari/537.36"
            )

            # 1. Подделываем Telegram.WebApp (чтобы игра не выкидывала)
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

            # 2. Перехватываем ВСЕ запросы и ответы (XHR/Fetch)
            intercepted = []

            async def handle_response(response):
                try:
                    req = response.request
                    if req.resource_type in ["xhr", "fetch"] or "api" in req.url.lower():
                        text = await response.text()
                        if len(text) > 20:
                            entry = {"url": req.url, "status": response.status, "data": text}
                            intercepted.append(entry)
                            print(f"\n🎯 HTTP: {req.url}")
                            print(f"📦 Статус: {response.status}")
                            print(f"📄 Данные: {text[:400]}...")
                except:
                    pass

            page.on("response", handle_response)

            # 3. Перехватываем WebSocket
            def handle_websocket(ws):
                print(f"\n🌐 WEBSOCKET: {ws.url}")
                ws.on("framereceived", lambda payload: print(f"⬇️ ПОЛУЧЕНО: {str(payload)[:400]}"))
                ws.on("framesent", lambda payload: print(f"⬆️ ОТПРАВЛЕНО: {str(payload)[:400]}"))

            page.on("websocket", handle_websocket)

            print("Загружаем игру...")
            await page.goto(direct_url, wait_until="domcontentloaded")
            
            # 4. Ждем 50 секунд, чтобы всё прогрузилось и установило соединения
            print("Ждем загрузки (50 секунд)...")
            await page.wait_for_timeout(50000)

            print(f"\nURL игры: {page.url}")

            # 5. Сохраняем ВСЁ в файлы для анализа
            print("\n💾 Сохраняем отладочные файлы...")
            await page.screenshot(path="Hamster/game_screenshot.png")
            
            html = await page.content()
            with open("Hamster/page_debug.html", "w", encoding="utf-8") as f:
                f.write(html)
                
            with open("Hamster/network_log.json", "w", encoding="utf-8") as f:
                json.dump(intercepted, f, indent=2, ensure_ascii=False)

            print(f"✅ Сохранено {len(intercepted)} HTTP-запросов.")
            print("Готово!")
            await browser.close()
            
    except Exception as e:
        print(f"❌ Ошибка: {e}")
    finally:
        await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())