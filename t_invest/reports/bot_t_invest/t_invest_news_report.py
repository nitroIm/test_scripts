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
# ИСПРАВЛЕНИЕ: Теперь читаем переменную канала
CHAT_ID = os.environ.get("TG_T_INVEST_CHANNEL") 

NEWS_SCORES_FILE = "t_invest/data/news/t_invest_news_scores.json"
NEWS_COLLECTOR_FILE = "t_invest/data/news/t_invest_news_collector.json"
WHITELIST_FILE = "t_invest/data/scanner/whitelist.json"

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

def get_score_text(score):
    if score >= 0.7: return "🟢 Сильный позитив"
    if score > 0: return "🟢 Позитив"
    if score <= -0.7: return "🔴 Сильный негатив"
    return "🔴 Негатив"

def is_trash(title):
    title_lower = title.lower()
    return any(word in title_lower for word in STOP_WORDS)

def get_news_title(ticker, news_list):
    sorted_news = sorted(news_list, key=lambda x: x.get('ts', ''), reverse=True)
    
    for news in sorted_news:
        tickers = news.get('tickers', [])
        title = news.get('title', '')
        
        if not title or is_trash(title): continue
        if len(tickers) > 5: continue 

        if ticker == "_MARKET_":
            if len(tickers) > 5 and not is_trash(title):
                return title
        else:
            if ticker in tickers and len(tickers) <= 3:
                return title
    return ""

def main():
    if not os.path.exists(NEWS_SCORES_FILE) or not os.path.exists(NEWS_COLLECTOR_FILE) or not os.path.exists(WHITELIST_FILE):
        log.error("Один из файлов не найден")
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

    for ticker, info in scores_data.items():
        if not isinstance(info, dict): continue
        score = info.get("score", 0.0)
        
        if abs(score) < 0.15: continue 

        if ticker == "_MARKET_":
            title = get_news_title("_MARKET_", news_data)
            if title: macro_news.append({"ticker": "Рынок", "score": score, "title": title})
        elif ticker in valid_tickers:
            title = get_news_title(ticker, news_data)
            if title: stock_news.append({"ticker": ticker, "score": score, "title": title})

    macro_news = sorted(macro_news, key=lambda x: abs(x['score']), reverse=True)[:2]
    stock_news = sorted(stock_news, key=lambda x: abs(x['score']), reverse=True)[:5]

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
            score_label = get_score_text(n['score'])
            text += f"• <b>{n['ticker']}</b> — {n['title']}\n<i>{score_label}</i>\n"
        text += "\n"

    text += "⚠️ <i>Не ИИР. Торговля — риск.</i>"

    if send_telegram_message(text):
        log.info("Новостной дайджест успешно отправлен в канал.")
    else:
        log.error("Ошибка отправки в Telegram.")
        sys.exit(1)

if __name__ == "__main__":
    main()