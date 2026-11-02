import os
import asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession

api_id = int(os.environ.get("TG_API_ID"))
api_hash = os.environ.get("TG_API_HASH")
phone = os.environ.get("MY_PHONE")

# Эти переменные появятся на втором шаге
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
        print("✅ КОД ОТПРАВЛЕН В TELEGRAM! (Проверь чат 'Telegram' или СМС)")
        print("\n⚠️ СКОПИРУЙ ЭТИ ДВЕ СТРОКИ И ДОБАВЬ В СЕКРЕТЫ GITHUB:")
        print(f"1. Имя: TG_HASH, Секрет: {sent_code.phone_code_hash}")
        print(f"2. Имя: TEMP_SESSION, Секрет: {client.session.save()}")
        print("3. Имя: TG_CODE, Секрет: (вставь код, который пришел в Telegram)")
        print("\nПосле добавления этих трех секретов, запусти Action заново!")
        print("="*50 + "\n")
        await client.disconnect()
        return

    # ШАГ 2: Входим с кодом и генерируем финальную сессию
    print("Пробуем войти по коду...")
    client = TelegramClient(StringSession(temp_session), api_id, api_hash)
    await client.connect()
    try:
        await client.sign_in(phone, code, phone_code_hash=hash_str)
        
        print("\n" + "="*50)
        print("🎉 УСПЕХ! Ты авторизован!")
        print("\n⚠️ СКОПИРУЙ ЭТУ ФИНАЛЬНУЮ СТРОКУ В СЕКРЕТ GITHUB:")
        print("Имя: TG_SESSION")
        print(f"Секрет: {client.session.save()}")
        print("\n(Секреты TG_CODE, TG_HASH и TEMP_SESSION теперь можно удалить, они больше не нужны)")
        print("="*50 + "\n")
    except Exception as e:
        print(f"Ошибка входа: {e}")
    finally:
        await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())