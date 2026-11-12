# PROD CONTOUR ONLY
# Python: 3.10

import os
import sys
import json
import logging
import io
import requests
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from datetime import datetime, timezone, timedelta

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

TOKEN = os.environ.get("INVEST_BOT_TOKEN")
CHAT_ID = os.environ.get("INVEST_BOT_CHAT_ID")

NEWS_SCORES_FILE = "t_invest/data/news/t_invest_news_scores.json"
NEWS_COLLECTOR_FILE = "t_invest/data/news/t_invest_news_collector.json"
WHITELIST_FILE = "t_invest/data/scanner/whitelist.json"

KLG_TZ = timezone(timedelta(hours=2))

def send_telegram_photo(photo_buf, caption):
    if not TOKEN or not CHAT_ID: 
        log.error("Нет TG токена или ID")
        return False
    url = f"https://api.telegram.org/bot{TOKEN}/sendPhoto"
    payload = {"chat_id": CHAT_ID, "caption": caption, "parse_mode": "HTML"}
    files = {"photo": ("chart.png", photo_buf, "image/png")}
    try:
        response = requests.post(url, data=payload, files=files, timeout=15)
        return response.json().get("ok", False)
    except Exception as e:
        log.error(f"TG Send Error: {e}")
        return False

def create_news_chart(items):
    plt.style.use('dark_background')
    fig, ax = plt.subplots(figsize=(10, 5), facecolor='#1a1a1a')
    ax.set_facecolor('#1a1a1a')

    labels = [i['ticker'] for i in items]
    scores = [i['score'] for i in items]
    colors = ['#00C853' if s > 0 else '#D50000' for s in scores]

    y_pos = np.arange(len(labels))
    bars = ax.barh(y_pos, scores, color=colors, height=0.6)
    ax.set_yticks(y_pos)
    ax.set_yticklabels(labels, fontsize=14, fontweight='bold')
    ax.invert_yaxis()
    
    ax.axvline(0, color='#555555', linewidth=1, zorder=0)

    for bar in bars:
        width = bar.get_width()
        ha = 'left' if width > 0 else 'right'
        offset = 0.02 if width > 0 else -0.02
        ax.text(width + offset, bar.get_y() + bar.get_height()/2, 
                f'{width:+.2f}', va='center', ha=ha, 
                color='white', fontweight='bold', fontsize=12)

    ax.set_title("Тональность новостей", color='#ffffff', pad=20, fontsize=16, fontweight='bold')
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['bottom'].set_visible(False)
    ax.spines['left'].set_visible(False)
    ax.tick_params(axis='x', colors='#aaaaaa', labelsize=12)

    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=150, facecolor='#1a1a1a', bbox_inches='tight')
    plt.close(fig)
    buf.seek(0)
    return buf

def get_news_title(ticker, news_list):
    # Ищем самые свежие новости по тикеру
    for news in sorted(news_list, key=lambda x: x.get('ts', ''), reverse=True):
        tickers = news.get('tickers', [])
        title = news.get('title', '')
        
        if not title: 
            continue
            
        if ticker == "_MARKET_":
            # Для макро берем новости, где больше 5 тикеров (общерыночные)
            if len(tickers) > 5:
                return title
        else:
            # Для конкретной акции ищем, где она есть в списке
            if ticker in tickers and len(tickers) <= 10:
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
        
        if abs(score) < 0.15: continue # Отсекаем шум

        if ticker == "_MARKET_":
            title = get_news_title("_MARKET_", news_data)
            if title: macro_news.append({"ticker": "Рынок", "score": score, "title": title})
        elif ticker in valid_tickers:
            title = get_news_title(ticker, news_data)
            if title: stock_news.append({"ticker": ticker, "score": score, "title": title})

    # 2. Сортируем и берем топы
    macro_news = sorted(macro_news, key=lambda x: abs(x['score']), reverse=True)[:3]
    stock_news = sorted(stock_news, key=lambda x: abs(x['score']), reverse=True)[:5]

    all_news = macro_news + stock_news

    if not all_news:
        log.info("Нет подходящих новостей с заголовками. Пост не отправлен.")
        sys.exit(0)

    # 3. Формируем текст
    now_klg = datetime.now(KLG_TZ).strftime("%d.%m.%Y %H:%M")
    text = f"⚡️ <b>Главное сейчас | {now_klg}</b>\n\n"

    if macro_news:
        text += "🌍 <b>Макро:</b>\n"
        for n in macro_news:
            emoji = "🟢" if n['score'] > 0 else "🔴"
            text += f"{emoji} {n['title']} ({n['score']:+.2f})\n"
        text += "\n"

    if stock_news:
        text += "🎯 <b>По акциям в фокусе:</b>\n"
        for n in stock_news:
            emoji = "🟢" if n['score'] > 0 else "🔴"
            text += f"{emoji} <b>{n['ticker']}</b> — {n['title']} ({n['score']:+.2f})\n"
        text += "\n"

    text += "⚠️ <i>Не ИИР. Торговля — риск.</i>"

    # 4. Рисуем график и отправляем
    log.info("Генерация графика...")
    chart_buf = create_news_chart(all_news)

    log.info("Отправка в Telegram...")
    if send_telegram_photo(chart_buf, text):
        log.info("Новостной дайджест успешно отправлен.")
    else:
        log.error("Ошибка отправки в Telegram.")
        sys.exit(1)

if __name__ == "__main__":
    main()