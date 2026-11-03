import os
import asyncio
import json
import urllib.parse
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.messages import RequestAppWebViewRequest
from telethon.tl.types import InputBotAppShortName

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

    print("✅ Авторизован. Открываем Hamster Kombat...")
    try:
        bot = await client.get_entity("hamster_kombat_bot")
        # ВАЖНО: получаем именно InputUser, а не просто id
        input_user = await client.get_input_entity(bot)

        # Передаём input_user в bot_id
        app = InputBotAppShortName(bot_id=input_user, short_name="start")

        web_view = await client(RequestAppWebViewRequest(
            peer=input_user,  # можно использовать input_user
            app=app,
            platform="android",
            write_allowed=True
        ))

        url = web_view.url

        if "tgWebAppData=" in url:
            init_data = url.split("tgWebAppData=")[1].split("&tgWebAppVersion")[0]
            decoded_data = urllib.parse.unquote(init_data)

            print("\n" + "="*50)
            print("🎉 РАЗВЕДКА УСПЕШНА! Данные получены.")

            try:
                params = dict(urllib.parse.parse_qsl(decoded_data))
                if 'user' in params:
                    user_info = json.loads(params['user'])
                    print(f"👤 Игрок: {user_info.get('first_name')} (@{user_info.get('username')})")
                    print(f"🆔 ID: {user_info.get('id')}")
            except Exception as e:
                print(f"Не удалось распарсить данные: {e}")

            print("\n⚠️ ТОКЕН ПОЛУЧЕН (нужен для тапов):")
            print(f"INIT_DATA: {init_data[:50]}...")
            print("="*50 + "\n")

        else:
            print("❌ Не удалось найти tgWebAppData в ссылке.")

    except Exception as e:
        print(f"❌ Ошибка при заходе: {e}")
    finally:
        await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())