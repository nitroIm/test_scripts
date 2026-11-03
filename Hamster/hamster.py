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
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
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

        # Подсовываем Telegram.WebApp ДО загрузки скриптов игры
        await page.add_init_script(f"""
            (() => {{
                const initData = `{init_data}`;
                const params = new URLSearchParams(initData);
                const userStr = params.get('user');
                let user = {{}};
                try {{ user = userStr ? JSON.parse(decodeURIComponent(userStr)) : {{}}; }} catch(e) {{}}
                const wa = {{
                    initData: initData,
                    initDataUnsafe: {{
                        query_id: params.get('query_id') || '',
                        user: user,
                        auth_date: params.get('auth_date') || '',
                        hash: params.get('hash') || '',
                        platform: "android",
                    }},
                    platform: "android",
                    version: "7.0",
                    colorScheme: "dark",
                    themeParams: {{}},
                    isExpanded: true,
                    viewportHeight: 915,
                    viewportStableHeight: 915,
                    headerColor: "#000000",
                    backgroundColor: "#000000",
                    ready: () => {{}},
                    expand: () => {{}},
                    close: () => {{}},
                    sendData: (d) => console.log('[sendData]', d),
                    openLink: (u) => console.log('[openLink]', u),
                    openTelegramLink: (u) => console.log('[openTelegramLink]', u),
                    showAlert: (m) => console.log('[showAlert]', m),
                    showConfirm: (m, cb) => cb && cb(true),
                    onEvent: () => {{}},
                    offEvent: () => {{}},
                    HapticFeedback: {{
                        impactOccurred: () => {{}},
                        notificationOccurred: () => {{}},
                        selectionChanged: () => {{}},
                    }},
                    MainButton: {{
                        text: "",
                        isVisible: false,
                        show: () => {{}},
                        hide: () => {{}},
                        onClick: () => {{}},
                        offClick: () => {{}},
                        setText: () => {{}},
                    }},
                    BackButton: {{
                        isVisible: false,
                        show: () => {{}},
                        hide: () => {{}},
                        onClick: () => {{}},
                        offClick: () => {{}},
                    }},
                }};
                window.Telegram = {{ WebApp: wa }};
                window.TelegramWebviewProxy = {{
                    postEvent: (type, data) => {{
                        console.log('[TelegramWebviewProxy]', type, data);
                    }}
                }};
                window.TelegramGameProxy = {{
                    receiveEvent: (data) => {{
                        console.log('[TelegramGameProxy]', data);
                    }}
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
                    "headers": dict(req.headers),
                }
                if req.post_data:
                    entry["post_data"] = req.post_data
                LOG_REQUESTS.append(entry)
            except Exception as e:
                print(f"[req-err] {e}")

        def on_ws(ws):
            ws_entry = {"url": ws.url, "frames": []}
            LOG_WS.append(ws_entry)
            ws.on("framesent", lambda p: ws_entry["frames"].append(
                {"dir": "sent", "payload": str(p)[:2000]}
            ))
            ws.on("framereceived", lambda p: ws_entry["frames"].append(
                {"dir": "recv", "payload": str(p)[:2000]}
            ))

        page.on("request", on_request)
        page.on("websocket", on_ws)
        page.on("console", lambda m: print(f"[console] {m.type}: {m.text[:300]}") if m.type in ("error", "warning") else None)

        print(f"[*] goto: {game_url[:200]}")
        try:
            await page.goto(game_url, wait_until="domcontentloaded", timeout=60000)
        except Exception as e:
            print(f"[!] goto failed: {e}")
        # даём игре время на инициализацию + WS
        await asyncio.sleep(30)

        print(f"[*] final_url: {page.url}")
        try:
            title = await page.title()
            print(f"[*] title: {title}")
        except Exception:
            pass

        await browser.close()

    # Сохраняем логи
    with open("requests.log", "w", encoding="utf-8") as f:
        json.dump(LOG_REQUESTS, f, ensure_ascii=False, indent=2)
    with open("ws.log", "w", encoding="utf-8") as f:
        json.dump(LOG_WS, f, ensure_ascii=False, indent=2)

    print(f"[+] total requests: {len(LOG_REQUESTS)}")
    print(f"[+] total websockets: {len(LOG_WS)}")

    print("\n=== Интересные HTTP запросы (hwgame / api / game) ===")
    for r in LOG_REQUESTS:
        u = r["url"]
        if "hwgame" in u or "/api" in u or "game" in u.lower():
            hdrs = r.get("headers", {})
            auth_keys = [k for k in hdrs.keys() if any(
                x in k.lower() for x in ("auth", "init", "token", "tg")
            )]
            print(f"  {r['method']} {u}")
            if auth_keys:
                print(f"      auth headers: {auth_keys}")
            if r.get("post_data"):
                print(f"      body[:200]: {r['post_data'][:200]}")

    print("\n=== WebSockets ===")
    for w in LOG_WS:
        print(f"  WS: {w['url']}")
        for fr in w["frames"][:4]:
            print(f"      {fr['dir']}: {fr['payload'][:300]}")


async def main():
    game_url, init_data = await get_game_url_and_initdata()
    print(f"[+] initData len: {len(init_data)}")
    print(f"[+] initData head: {init_data[:120]}...")
    await intercept(game_url, init_data)


if __name__ == "__main__":
    asyncio.run(main())