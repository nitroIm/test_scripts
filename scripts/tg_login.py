import os
import asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession

api_id = int(os.environ.get("TG_API_ID"))
api_hash = os.environ.get("TG_API_HASH")
session_str = os.environ.get("TG_SESSION")

async def main():
    if not session_str:
        print("❌ Ошибка: секрет TG_SESSION не найден или пустой!")
        return

    print("Пробуем подключиться с сохраненной сессией...")
    client = TelegramClient(StringSession(session_str), api_id, api_hash)
    
    try:
        await client.connect()
        if await client.is_user_authorized():
            me = await client.get_me()
            print("\n" + "="*50)
            print("✅ СЕССИЯ РАБОЧАЯ! УСПЕХ!")
            print(f"Бот успешно зашел на аккаунт: {me.first_name}")
            print(f"Юзернейм: @{me.username}")
            print("="*50 + "\n")
        else:
            print("❌ Сессия не авторизована (ключ недействителен).")
    except Exception as e:
        print(f"❌ Ошибка подключения: {e}")
    finally:
        await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())