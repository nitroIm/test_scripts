# Hamster/hamster.py
import os
import asyncio
import json
import urllib.parse
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.messages import RequestAppWebViewRequest
from telethon.tl.types import InputBotAppShortName
from playwright.async_api import async_playwright

api_id = int(os.environ["TG_API_ID"])
api_hash = os.environ["TG_API_HASH"]
session_str = os.environ["TG_SESSION"]

LOG_REQUESTS = []
LOG_RESPONSES = []
LOG_WS = []

async def get_game_url_and_initdata():
    client = TelegramClient(StringSession(session_str), api_id, api_hash)
    await client.connect()
    bot = await client.get_entity("hamsterking_game_bot")
    input_user = await client.get_input_entity(bot)
    app = InputBotAppShortName(bot_id=input_user, short_name="start")
    web_view = await client(RequestAppWebViewRequest(
        peer=input_user, app=app, platform="android", write_allowed=True
    ))
    game_url = web_view.url
    init_data = urllib.parse.unquote(
        game_url.split("tgWebAppData=")[1].split("&tgWebAppVersion")[0]
    )
    await client.disconnect()
    return game_url, init_data

async def intercept(game_url: str, init_data: str):
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,  # Запускаем под xvfb для обхода детекта headless
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--enable-unsafe-swiftshader",
                "--use-gl=swiftshader",
                "--disable-gpu",
            ],
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Linux; Android 13; SM-S918B) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36"
            ),
            viewport={"width": 412, "height": 915},
            is_mobile=True,
            has_touch=True,
            locale="ru-RU",
        )
        page = await context.new_page()

        # Максимальная маскировка для обхода детекта Telegram.WebApp
        await page.add_init_script(f"""
            (() => {{
                Object.defineProperty(navigator, 'webdriver', {{ get: () => undefined }});
                const originalUserAgentData = navigator.userAgentData;
                if (originalUserAgentData) {{
                    Object.defineProperty(navigator, 'userAgentData', {{
                        get: () => ({{
                            brands: [
                                {{ brand: "Google Chrome", version: "124" }},
                                {{ brand: "Chromium", version: "124" }},
                                {{ brand: "Not-A.Brand", version: "99" }}
                            ],
                            mobile: true,
                            platform: "Android"
                        }})
                    }});
                }}
                const initData = `{init_data}`;
                const params = new URLSearchParams(initData);
                const userStr = params.get('user');
                let user = {{}};
                try {{ user = userStr ? JSON.parse(decodeURIComponent(userStr)) : {{}}; }} catch(e) {{}}
                window.Telegram = {{
                    WebApp: {{
                        initData: initData,
                        initDataUnsafe: {{
                            query_id: params.get('query_id') || '',
                            user: user,
                            auth_date: params.get('auth_date') || '',
                            hash: params.get('hash') || '',
                            platform: "android",
                        }},
                        platform: "android",
                        version: "9.6",
                        colorScheme: "dark",
                        themeParams: {{}},
                        isExpanded: true,
                        viewportHeight: 915,
                        viewportStableHeight: 915,
                        ready: () => {{ console.log('[TG] ready()'); }},
                        expand: () => {{ console.log('[TG] expand()'); }},
                        close: () => {{}},
                        sendData: (d) => console.log('[sendData]', d),
                        openLink: (u) => console.log('[openLink]', u),
                        openTelegramLink: (u) => console.log('[openTelegramLink]', u),
                        showAlert: (m) => console.log('[showAlert]', m),
                        showConfirm: (m, cb) => cb && cb(true),
                        onEvent: () => {{}},
                        offEvent: () => {{}},
                        isVersionAtLeast: (v) => true,
                        HapticFeedback: {{
                            impactOccurred: () => {{}},
                            notificationOccurred: () => {{}},
                            selectionChanged: () => {{}},
                        }},
                        MainButton: {{
                            text: "", isVisible: false, show: () => {{}}, hide: () => {{}},
                            onClick: () => {{}}, offClick: () => {{}}, setText: () => {{}},
                        }},
                        BackButton: {{
                            isVisible: false, show: () => {{}}, hide: () => {{}},
                            onClick: () => {{}}, offClick: () => {{}},
                        }},
                    }}
                }};
                window.TelegramWebviewProxy = {{
                    postEvent: (type, data) => console.log('[TelegramWebviewProxy]', type, data)
                }};
                window.TelegramGameProxy = {{
                    receiveEvent: (data) => console.log('[TelegramGameProxy]', data)
                }};
                window.TelegramGameProxy_receiveEvent = (data) => {{
                    console.log('[TelegramGameProxy_receiveEvent]', data);
                }};
            }})();
        """)

        def on_request(req):
            try:
                entry = {
                    "method": req.method,
                    "url": req.url,
                    "resource_type": req.resource_type,
                }
                if req.post_data:
                    entry["post_data"] = req.post_data
                LOG_REQUESTS.append(entry)
            except Exception:
                pass

        async def on_response(resp):
            try:
                url = resp.url
                # Сохраняем ответы от API hwgame (кроме статики)
                if "hwgame" in url and "cdn-prod" not in url:
                    text = ""
                    try:
                        text = await resp.text()
                    except Exception:
                        pass
                    LOG_RESPONSES.append({
                        "url": url,
                        "status": resp.status,
                        "headers": dict(resp.headers),
                        "body": text
                    })
                    print(f"[RESPONSE] {resp.status} {url}")
                    print(f"  body[:500]: {text[:500]}")
            except Exception:
                pass

        def on_ws(ws):
            ws_entry = {"url": ws.url, "frames": []}
            LOG_WS.append(ws_entry)
            ws.on("framesent", lambda p: ws_entry["frames"].append({"dir": "sent", "payload": str(p)[:2000]}))
            ws.on("framereceived", lambda p: ws_entry["frames"].append({"dir": "recv", "payload": str(p)[:2000]}))
            print(f"[WS] Подключение: {ws.url}")

        page.on("request", on_request)
        page.on("response", lambda r: asyncio.create_task(on_response(r)))
        page.on("websocket", on_ws)

        def on_console(m):
            if m.type in ("error", "warning"):
                print(f"[console] {m.type}: {m.text[:300]}")

        page.on("console", on_console)

        print(f"[*] Переход на: {game_url[:150]}...")
        try:
            await page.goto(game_url, wait_until="load", timeout=60000)
        except Exception as e:
            print(f"[!] Ошибка перехода: {e}")

        # Ждем загрузки Unity и инициализации
        await asyncio.sleep(30)

        # Эмулируем тап, чтобы разбудить игру
        print("[*] Эмуляция тапа...")
        try:
            await page.mouse.click(200, 400)
            await asyncio.sleep(5)
            await page.mouse.click(200, 400)
        except Exception:
            pass

        # Ждем еще немного для WebSocket
        await asyncio.sleep(20)

        print(f"[*] Финальный URL: {page.url}")
        await browser.close()

    # Сохраняем логи в файлы
    with open("requests.log", "w", encoding="utf-8") as f:
        json.dump(LOG_REQUESTS, f, ensure_ascii=False, indent=2)
    with open("responses.log", "w", encoding="utf-8") as f:
        json.dump(LOG_RESPONSES, f, ensure_ascii=False, indent=2)
    with open("ws.log", "w", encoding="utf-8") as f:
        json.dump(LOG_WS, f, ensure_ascii=False, indent=2)

    print(f"\n[+] Всего запросов: {len(LOG_REQUESTS)}")
    print(f"[+] Всего ответов: {len(LOG_RESPONSES)}")
    print(f"[+] Всего WebSocket: {len(LOG_WS)}")

async def main():
    game_url, init_data = await get_game_url_and_initdata()
    print(f"[+] initData len: {len(init_data)}")
    await intercept(game_url, init_data)

if __name__ == "__main__":
    asyncio.run(main())