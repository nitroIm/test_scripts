# PROD CONTOUR ONLY
# Python: 3.10
#
# ИЗМЕНЕНИЯ v1.1:
#   - Исправлено имя файла словаря: sentiment_dictionary.json
#     (совпадает с реальным файлом в t_invest/data/news/).
#   - Отбор новостей по собственному словарю: слова, бустеры, глушители.
#   - Ярлыков ("Сильный позитив") в посте больше нет.
#   - Файл t_invest_news_scores.json не читается и не нужен.

import os
import sys
import json
import logging
import requests
from datetime import datetime, timezone, timedelta

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

TOKEN = os.environ.get("INVEST_BOT_TOKEN")
CHAT_ID = os.environ.get("TG_T_INVEST_CHANNEL")

SENTIMENT_DICT_FILE = "t_invest/data/news/sentiment_dictionary.json"
NEWS_COLLECTOR_FILE = "t_invest/data/news/t_invest_news_collector.json"
WHITELIST_FILE = "t_invest/data/scanner/whitelist.json"

# Сколько "баллов" словаря нужно, чтобы новость попала в пост.
# 1.0 = одна сильная новость или пара средних. Хотите реже — поднимите до 1.5.
SCORE_THRESHOLD = 1.0

MAX_STOCK_NEWS = 5
MAX_MACRO_NEWS = 2

KLG_TZ = timezone(timedelta(hours=2))

STOP_WORDS = ["итоги торгов", "анонс", "обзор", "краткий обзор", "лидеры роста", "лидеры падения"]


def send_telegram_message(text):
    if not TOKEN or not CHAT_ID:
        log.error(f"Нет TG токена или ID (TOKEN: {bool(TOKEN)}, CHAT_ID: {bool(CHAT_ID)})")
        return False
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
    try:
        response = requests.post(url, json=payload, timeout=15)
        res_data = response.json()
        if not res_data.get("ok"):
            log.error(f"Ошибка API Telegram: {res_data}")
        return res_data.get("ok", False)
    except Exception as e:
        log.error(f"TG Send Error: {e}")
        return False


def is_trash(title):
    title_lower = title.lower()
    return any(word in title_lower for word in STOP_WORDS)


def load_dictionary():
    with open(SENTIMENT_DICT_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def score_text(text, sentiment):
    """Считает балл новости по словарю: слова + бустеры + глушители."""
    text_lower = text.lower()
    matched = 0
    multiplier = 1.0

    for word, weight in sentiment.get("words", {}).items():
        if word.lower() in text_lower:
            matched += weight

    for word, factor in sentiment.get("boosters", {}).items():
        if word.lower() in text_lower:
            multiplier *= factor

    for word, factor in sentiment.get("dampeners", {}).items():
        if word.lower() in text_lower:
            multiplier *= factor

    return matched * multiplier


def get_news_title(ticker, news_list):
    sorted_news = sorted(news_list, key=lambda x: x.get('ts', ''), reverse=True)

    for news in sorted_news:
        tickers = news.get('tickers', [])
        title = news.get('title', '')

        if not title or is_trash(title):
            continue

        if ticker == "_MARKET_":
            if len(tickers) > 5:
                return title
        else:
            if ticker in tickers and len(tickers) <= 3:
                return title
    return ""


def main():
    for path in (SENTIMENT_DICT_FILE, NEWS_COLLECTOR_FILE, WHITELIST_FILE):
        if not os.path.exists(path):
            log.error(f"Файл не найден: {path}")
            sys.exit(1)

    sentiment = load_dictionary()

    with open(NEWS_COLLECTOR_FILE, "r", encoding="utf-8") as f:
        news_data = json.load(f)
    with open(WHITELIST_FILE, "r", encoding="utf-8") as f:
        wl_data = json.load(f)

    valid_tickers = {s["ticker"] for s in wl_data.get("data", [])}

    macro_news = []
    best_by_ticker = {}

    for news in news_data:
        tickers = news.get('tickers', [])
        title = news.get('title', '')

        if not title or is_trash(title):
            continue

        score = score_text(title, sentiment)
        if abs(score) < SCORE_THRESHOLD:
            continue

        if len(tickers) > 5:
            macro_news.append({"ticker": "Рынок", "score": score, "title": title})
            continue

        for ticker in tickers:
            if ticker not in valid_tickers:
                continue
            if ticker not in best_by_ticker or abs(score) > abs(best_by_ticker[ticker]["score"]):
                best_by_ticker[ticker] = {"ticker": ticker, "score": score, "title": title}

    stock_news = sorted(best_by_ticker.values(), key=lambda x: abs(x['score']), reverse=True)
    macro_news = sorted(macro_news, key=lambda x: abs(x['score']), reverse=True)

    stock_news = stock_news[:MAX_STOCK_NEWS]
    macro_news = macro_news[:MAX_MACRO_NEWS]

    if not macro_news and not stock_news:
        log.info("Нет подходящих новостей. Пост не отправлен.")
        sys.exit(0)

    now_klg = datetime.now(KLG_TZ).strftime("%d.%m.%Y %H:%M")
    text = f"⚡️ <b>Главное сейчас | {now_klg}</b>\n\n"

    if macro_news:
        text += "🌍 <b>Общий фон:</b>\n"
        for n in macro_news:
            text += f"• {n['title']}\n"
        text += "\n"

    if stock_news:
        text += "🎯 <b>По акциям:</b>\n"
        for n in stock_news:
            text += f"• <b>{n['ticker']}</b> — {n['title']}\n"
        text += "\n"

    text += "⚠️ <i>Не ИИР. Торговля — риск.</i>"

    if send_telegram_message(text):
        log.info("Новостной дайджест успешно отправлен в канал.")
    else:
        log.error("Ошибка отправки в Telegram.")
        sys.exit(1)


if __name__ == "__main__":
    main()
