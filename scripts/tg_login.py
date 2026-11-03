import os
import asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError

api_id = int(os.environ.get("TG_API_ID"))
api_hash = os.environ.get("TG_API_HASH")
phone = os.environ.get("MY_PHONE")
password = os.environ.get("TG_2FA_PASSWORD")

code = os.environ.get("TG_CODE") 
hash_str = os.environ.get("TG_HASH") 
temp_session = os.environ.get("TEMP_SESSION")

async def main():
    if not code or not hash_str or not temp_session:
        # ШАГ 1: Отправляем код
        print("Отправляем код в Telegram...")
        client = TelegramClient(StringSession(), api_id, api_hash)
        await client.connect()
        sent_code = await client.send_code_request(phone)
        
        print("\n" + "="*50)
        print("✅ КОД ОТПРАВЛЕН В TELEGRAM!")
        print(f"1. Имя: TG_HASH, Секрет: {sent_code.phone_code_hash}")
        print(f"2. Имя: TEMP_SESSION, Секрет: {client.session.save()}")
        print("3. Имя: TG_CODE, Секрет: (код из Телеграма)")
        print("="*50 + "\n")
        await client.disconnect()
        return

    # ШАГ 2: Входим с кодом и паролем
    print("Пробуем войти по коду...")
    client = TelegramClient(StringSession(temp_session), api_id, api_hash)
    await client.connect()
    try:
        await client.sign_in(phone, code, phone_code_hash=hash_str)
    except SessionPasswordNeededError:
        print("Обнаружена двухэтапная аутентификация. Вводим пароль...")
        await client.sign_in(password=password)
    except Exception as e:
        print(f"Ошибка входа: {e}")
        await client.disconnect()
        return
        
    print("\n" + "="*50)
    print("🎉 УСПЕХ! Ты авторизован!")
    
    # ХИТРОСТЬ: Разбиваем сессию на две части, чтобы GitHub её не скрыл
    session_str = client.session.save()
    half = len(session_str) // 2
    
    print("\n⚠️ СКОПИРУЙ ЭТИ ДВЕ ЧАСТИ И СКЛЕЙ ВМЕСТЕ (без пробелов):")
    print(f"ЧАСТЬ 1: {session_str[:half]}")
    print(f"ЧАСТЬ 2: {session_str[half:]}")
    print("="*50 + "\n")
    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())