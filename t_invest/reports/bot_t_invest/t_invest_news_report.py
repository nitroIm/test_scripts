# PROD CONTOUR ONLY
# Python: 3.10

import os
import sys
import json
import logging
import requests
from datetime import datetime, timezone, timedelta

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

TOKEN = os.environ.get("INVEST_BOT_TOKEN")
CHAT_ID = os.environ.get("INVEST_BOT_CHAT_ID")

NEWS_SCORES_FILE = "t_invest/data/news/t_invest_news_scores.json"
NEWS_COLLECTOR_FILE = "t_invest/data/news/t_invest_news_collector.json"
WHITELIST_FILE = "t_invest/data/scanner/whitelist.json"

KLG_TZ = timezone(timedelta(hours=2))

def send_telegram_message(text):
    if not TOKEN or not CHAT_ID: 
        log.error("Нет TG токена или ID")
        return False
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
    try:
        response = requests.post(url, json=payload, timeout=15)
        return response.json().get("ok", False)
    except Exception as e:
        log.error(f"TG Send Error: {e}")
        return False

def get_score_text(score):
    if score >= 0.7: return "🔴 Сильный позитив"
    if score > 0: return "🟢 Позитив"
    if score <= -0.7: return "🔴 Сильный негатив"
    return "🔴 Негатив"

def get_news_title(ticker, news_list):
    # Сортируем новости от новых к старым
    sorted_news = sorted(news_list, key=lambda x: x.get('ts', ''), reverse=True)
    
    for news in sorted_news:
        tickers = news.get('tickers', [])
        title = news.get('title', '')
        
        if not title: continue
        if len(tickers) > 5: continue # Пропускаем общие обзоры рынка

        if ticker == "_MARKET_":
            # Для макро берем как раз обзоры рынка
            if len(tickers) > 5:
                return title
        else:
            # Для акции ищем новость, где есть этот тикер и мало других
            if ticker in tickers and len(tickers) <= 3:
                return title
    return ""

def main():
    if not os.path.exists(NEWS_SCORES_FILE) or not os.path.exists(NEWS_COLLECTOR_FILE) or not os.path.exists(WHITELIST_FILE):
        log.error("Один из файлов (scores, collector, whitelist) не найден")
        sys.exit(1)

    with open(NEWS_SCORES_FILE, "r", encoding="utf-8") as f:
        scores_data = json.load(f)
    with open(NEWS_COLLECTOR_FILE, "r", encoding="utf-8") as f:
        news_data = json.load(f)
    with open(WHITELIST_FILE, "r", encoding="utf-8") as f:
        wl_data = json.load(f)

    valid_tickers = {s["ticker"] for s in wl_data.get("data", [])}

    macro_news = []
    stock_news = []

    # 1. Разбираем скоры
    for ticker, info in scores_data.items():
        if not isinstance(info, dict): continue
        score = info.get("score", 0.0)
        
        # Отсекаем нейтральный шум
        if abs(score) < 0.15: continue

        if ticker == "_MARKET_":
            title = get_news_title("_MARKET_", news_data)
            if title: macro_news.append({"ticker": "Рынок", "score": score, "title": title})
        elif ticker in valid_tickers:
            title = get_news_title(ticker, news_data)
            if title: stock_news.append({"ticker": ticker, "score": score, "title": title})

    # 2. Сортируем и берем топы
    macro_news = sorted(macro_news, key=lambda x: abs(x['score']), reverse=True)[:2]
    stock_news = sorted(stock_news, key=lambda x: abs(x['score']), reverse=True)[:5]

    if not macro_news and not stock_news:
        log.info("Нет подходящих новостей. Пост не отправлен.")
        sys.exit(0)

    # 3. Формируем текст
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
            score_label = get_score_text(n['score'])
            text += f"• <b>{n['ticker']}</b> — {n['title']}\n<i>{score_label}</i>\n"
        text += "\n"

    text += "⚠️ <i>Не ИИР. Торговля — риск.</i>"

    # 4. Отправляем
    log.info("Отправка в Telegram...")
    if send_telegram_message(text):
        log.info("Новостной дайджест успешно отправлен.")
    else:
        log.error("Ошибка отправки в Telegram.")
        sys.exit(1)

if __name__ == "__main__":
    main()