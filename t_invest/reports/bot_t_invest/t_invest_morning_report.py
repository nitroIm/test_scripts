# PROD CONTOUR ONLY
# Python: 3.10

import os
import sys
import json
import logging
import io
import math
import requests
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from datetime import datetime, timezone, timedelta

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

# ================= НАСТРОЙКИ =================
WHITELIST_PATH = "t_invest/data/scanner/whitelist.json"
BEST_PARAMS_PATH = "t_invest/data/model/best_params.json"
NEWS_SCORES_PATH = "t_invest/data/news/t_invest_news_scores.json"

BOT_TOKEN = os.getenv("INVEST_BOT_TOKEN", "").strip()
CHANNEL_ID = os.getenv("TG_T_INVEST_CHANNEL", "").strip()

MSK = timezone(timedelta(hours=3))

def load_json(path):
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log.warning(f"Ошибка чтения {path}: {e}")
        return None

def format_money(val):
    if val >= 1_000_000_000:
        return f"{val / 1_000_000_000:.1f} млрд ₽"
    elif val >= 1_000_000:
        return f"{val / 1_000_000:.0f} млн ₽"
    return f"{val} ₽"

def get_sentiment_text(ticker, news_data):
    """Возвращает текстовое описание сентимента и эмодзи"""
    if not news_data or ticker not in news_data:
        return "нейтр. ⚪️"
    
    score = 0.0
    if isinstance(news_data, dict):
        if "data" in news_data and isinstance(news_data["data"], dict) and ticker in news_data["data"]:
            score = news_data["data"][ticker]
        elif ticker in news_data:
            score = news_data[ticker]
    
    try:
        score = float(score)
    except (ValueError, TypeError):
        return "нейтр. ⚪️"

    if score > 0.15:
        return f"позит. 🟢 ({score:+.2f})"
    elif score < -0.15:
        return f"негатив 🔴 ({score:+.2f})"
    else:
        return f"нейтр. ⚪️ ({score:+.2f})"

def create_bubble_chart(top_stocks):
    """Рисует график с пузырями и возвращает BytesIO"""
    plt.style.use('dark_background')
    
    fig, ax = plt.subplots(figsize=(10, 5), facecolor='#1a1a1a')
    ax.set_facecolor('#1a1a1a')

    turnovers = [s['avg_daily_turnover_rub'] for s in top_stocks]
    max_turnover = max(turnovers) if turnovers else 1
    min_turnover = min(turnovers) if turnovers else 1

    for i, stock in enumerate(top_stocks):
        ticker = stock['ticker']
        turnover = stock['avg_daily_turnover_rub']
        trend = stock.get('trend', 'SIDEWAYS')
        vol = stock.get('avg_daily_range_pct', 0)

        if trend == "UP":
            color = '#00C853'
        elif trend == "DOWN":
            color = '#D50000'
        else:
            color = '#FFD600'

        if max_turnover > min_turnover:
            norm = (math.log(turnover + 1) - math.log(min_turnover + 1)) / (math.log(max_turnover + 1) - math.log(min_turnover + 1))
        else:
            norm = 0.5
            
        size = 3000 + norm * 5000

        ax.scatter(i, 0, s=size, color=color, alpha=0.85, edgecolors='#ffffff', linewidth=2, zorder=1)
        ax.text(i, 0, f"${ticker}", ha='center', va='center', fontweight='bold', fontsize=12, color='black', zorder=2)
        ax.text(i, -0.55, f"{vol:.1f}%", ha='center', va='center', fontsize=12, color='#aaaaaa', zorder=2)

    ax.set_title("Волатильность и объем (размер = оборот)", color='#ffffff', pad=20, fontsize=14)
    
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_xlim(-0.7, len(top_stocks) - 0.3)
    ax.set_ylim(-1.0, 0.8)
    
    for spine in ax.spines.values():
        spine.set_visible(False)

    plt.subplots_adjust(left=0.05, right=0.95, top=0.85, bottom=0.15)
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=150, facecolor='#1a1a1a')
    plt.close(fig)
    buf.seek(0)
    return buf

def main():
    if not BOT_TOKEN or not CHANNEL_ID:
        log.error("Отсутствуют переменные окружения: INVEST_BOT_TOKEN или TG_T_INVEST_CHANNEL")
        sys.exit(1)

    whitelist_data = load_json(WHITELIST_PATH)
    best_params = load_json(BEST_PARAMS_PATH)
    news_data = load_json(NEWS_SCORES_PATH)

    if not whitelist_data or not best_params:
        log.error("Не удалось загрузить данные сканера или обучения.")
        sys.exit(1)

    all_stocks = whitelist_data.get("data", [])
    total_found = len(all_stocks)
    
    long_tickers = best_params.get("long_tickers", [])
    top_stocks = [s for s in all_stocks if s["ticker"] in long_tickers]
    
    if not top_stocks:
        log.error("Не найдены данные по выбранным тикерам.")
        sys.exit(1)

    try:
        intraday_model = best_params["intraday"]["long"].get("source", "ML")
        swing_model = best_params["swing"]["long"].get("source", "ML")
    except (KeyError, TypeError):
        intraday_model = "ML"
        swing_model = "ML"

    text = (
        f"☀️ <b>Цели на сегодня</b>\n\n"
        f"Сканер проанализировал рынок и выделил <b>{total_found}</b> ликвидных бумаг. "
        f"Для торговли алгоритм выбрал <b>{len(top_stocks)}</b> целей. Работаем только в Лонг.\n\n"
        f"<b>В фокусе:</b>\n"
    )

    for i, stock in enumerate(top_stocks, 1):
        sent_text = get_sentiment_text(stock['ticker'], news_data)
        text += (
            f"{i}. <b>${stock['ticker']}</b> — Волатильность {stock['avg_daily_range_pct']:.1f}% | "
            f"Оборот {format_money(stock['avg_daily_turnover_rub'])}\n"
            f"📰 Фон: {sent_text}\n"
        )

    text += (
        f"\n🤖 <b>Обучение завершено:</b> Модели {intraday_model} (Intraday) и {swing_model} (Swing).\n\n"
        f"⚠️ <i>Не ИИР. Торговля — риск.</i>"
    )

    log.info("Генерация графика...")
    photo_buf = create_bubble_chart(top_stocks)

    log.info("Отправка в Telegram...")
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    
    payload = {
        "chat_id": CHANNEL_ID,
        "caption": text,
        "parse_mode": "HTML"
    }
    
    files = {
        "photo": ("chart.png", photo_buf, "image/png")
    }

    try:
        response = requests.post(url, data=payload, files=files, timeout=20)
        data = response.json()
        if data.get("ok"):
            log.info("Утренний отчет успешно отправлен.")
        else:
            log.error(f"Ошибка Telegram API: {data}")
            sys.exit(1)
    except Exception as e:
        log.error(f"Сбой сети: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()