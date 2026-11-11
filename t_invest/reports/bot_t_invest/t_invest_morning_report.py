# PROD CONTOUR ONLY
# Python: 3.10

import os
import sys
import json
import logging
import io
import requests
import matplotlib
matplotlib.use('Agg') # Для работы без графического интерфейса в GitHub Actions
import matplotlib.pyplot as plt
from datetime import datetime, timezone, timedelta

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

# ================= НАСТРОЙКИ =================
WHITELIST_PATH = "t_invest/data/scanner/whitelist.json"
BEST_PARAMS_PATH = "t_invest/data/model/best_params.json"

BOT_TOKEN = os.getenv("INVEST_BOT_TOKEN", "").strip()
CHANNEL_ID = os.getenv("TG_T_INVEST_CHANNEL", "").strip()

MSK = timezone(timedelta(hours=3))

def load_json(path):
    if not os.path.exists(path):
        log.error(f"Файл не найден: {path}")
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def format_money(val):
    if val >= 1_000_000_000:
        return f"{val / 1_000_000_000:.1f} млрд ₽"
    elif val >= 1_000_000:
        return f"{val / 1_000_000:.0f} млн ₽"
    return f"{val} ₽"

def create_bubble_chart(top_stocks):
    """Рисует график с пузырями и возвращает BytesIO"""
    plt.style.use('dark_background')
    fig, ax = plt.subplots(figsize=(8, 5), facecolor='#1e1e1e')
    ax.set_facecolor('#1e1e1e')

    x_positions = range(len(top_stocks))
    
    for i, stock in enumerate(top_stocks):
        ticker = stock['ticker']
        turnover = stock['avg_daily_turnover_rub']
        trend = stock.get('trend', 'SIDEWAYS')
        vol = stock.get('avg_daily_range_pct', 0)

        # Цвет по тренду
        if trend == "UP":
            color = '#00C853' # Зеленый
        elif trend == "DOWN":
            color = '#D50000' # Красный
        else:
            color = '#FFD600' # Желтый

        # Размер пузыря зависит от оборота (масштабируем)
        size = turnover / 2_000_000 

        ax.scatter(i, 0, s=size, color=color, alpha=0.7, edgecolors='white', linewidth=1.5)
        ax.text(i, 0, f"${ticker}", ha='center', va='center', fontweight='bold', fontsize=10, color='black')
        ax.text(i, -0.5, f"{vol:.1f}%", ha='center', va='center', fontsize=9, color='#aaaaaa')

    ax.set_title("Волатильность и объем (размер = оборот)", color='white', pad=20)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['bottom'].set_visible(False)
    ax.spines['left'].set_visible(False)
    
    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=120, bbox_inches='tight')
    plt.close(fig)
    buf.seek(0)
    return buf

def main():
    if not BOT_TOKEN or not CHANNEL_ID:
        log.error("Отсутствуют переменные окружения: INVEST_BOT_TOKEN или TG_T_INVEST_CHANNEL")
        sys.exit(1)

    # 1. Загружаем данные
    whitelist_data = load_json(WHITELIST_PATH)
    best_params = load_json(BEST_PARAMS_PATH)

    if not whitelist_data or not best_params:
        log.error("Не удалось загрузить данные для отчета.")
        sys.exit(1)

    all_stocks = whitelist_data.get("data", [])
    total_found = whitelist_data.get("metadata", {}).get("total_found", len(all_stocks))
    
    # Получаем тикеры, которые выбрал тренер
    long_tickers = best_params.get("long_tickers", [])
    
    # Собираем полную инфу по выбранным тикерам
    top_stocks = [s for s in all_stocks if s["ticker"] in long_tickers]
    
    if not top_stocks:
        log.error("Не найдены данные по выбранным тикерам в whitelist.")
        sys.exit(1)

    # 2. Формируем текст
    try:
        intraday_model = best_params["intraday"]["long"].get("source", "XGBoost")
        swing_model = best_params["swing"]["long"].get("source", "CatBoost")
    except (KeyError, TypeError):
        intraday_model = "ML-модель"
        swing_model = "ML-модель"

    text = (
        f"☀️ <b>Цели на сегодня</b>\n\n"
        f"Бот просканировал рынок и нашел <b>{total_found}</b> ликвидных бумаг. "
        f"Но для торговли на сегодня выбрал только <b>{len(top_stocks)}</b> лучших целей. Работаем только в Лонг.\n\n"
        f"<b>В фокусе:</b>\n"
    )

    for i, stock in enumerate(top_stocks, 1):
        text += f"{i}. <b>${stock['ticker']}</b> — Волатильность {stock['avg_daily_range_pct']}% | Оборот {format_money(stock['avg_daily_turnover_rub'])}.\n"

    text += (
        f"\n🤖 <b>Обучение завершено:</b> Лучшие модели — {intraday_model} (Intraday) и {swing_model} (Swing).\n\n"
        f"Ждем сигналов по часовым свечам. Сигналы и сделки пришлю сюда.\n"
        f"⚠️ <i>Не ИИР. Торговля — риск.</i>"
    )

    # 3. Рисуем график
    log.info("Генерация графика...")
    photo_buf = create_bubble_chart(top_stocks)

    # 4. Отправляем в Telegram
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
        response = requests.post(url, data=payload, files=files, timeout=15)
        data = response.json()
        if data.get("ok"):
            log.info("Утренний отчет успешно отправлен в канал.")
        else:
            log.error(f"Ошибка Telegram API: {data}")
            sys.exit(1)
    except Exception as e:
        log.error(f"Сбой сети при отправке: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()