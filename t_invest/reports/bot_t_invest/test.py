import os
import sys
import requests
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("INVEST_BOT_TOKEN", "").strip()
CHANNEL_ID = os.getenv("TG_T_INVEST_CHANNEL", "").strip()

def main():
    if not BOT_TOKEN or not CHANNEL_ID:
        logger.error("Отсутствуют переменные окружения: INVEST_BOT_TOKEN или TG_T_INVEST_CHANNEL")
        sys.exit(1)

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    text = "Добрый день! 🖐\nТест связи из GitHub Actions прошел успешно. Бот готов к работе."
    
    payload = {
        "chat_id": CHANNEL_ID,
        "text": text
    }

    try:
        response = requests.post(url, json=payload, timeout=10)
        data = response.json()
        
        if data.get("ok"):
            logger.info("Сообщение успешно отправлено в Telegram!")
        else:
            logger.error(f"Ошибка API Telegram: {data}")
            sys.exit(1)
    except Exception as e:
        logger.error(f"Сбой при отправке: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()