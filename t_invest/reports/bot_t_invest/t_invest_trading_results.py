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
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

# --- НАСТРОЙКИ ---
TOKEN = os.environ.get("INVEST_BOT_TOKEN")
CHAT_ID = os.environ.get("TG_T_INVEST_CHANNEL")

HISTORY_FILE = Path("t_invest/data/simulator/trade_history.json")
CONFIG_FILE = Path("t_invest/data/simulator/simulator_config.json")

KLG_TZ = timezone(timedelta(hours=2))
START_BALANCE = 10000.0

def load_json(path, default):
    if not path.exists(): return default
    try:
        with open(path, "r", encoding="utf-8") as f: return json.load(f)
    except: return default

def send_telegram_photo(photo_buf, caption):
    if not TOKEN or not CHAT_ID: 
        log.error("Нет TG токена или ID канала")
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

def create_pnl_chart(intraday_pnl, swing_pnl):
    plt.style.use('dark_background')
    fig, ax = plt.subplots(figsize=(10, 5), facecolor='#1a1a1a')
    ax.set_facecolor('#1a1a1a')

    labels = ['Intraday', 'Swing']
    values = [intraday_pnl, swing_pnl]
    colors = ['#00C853' if v >= 0 else '#D50000' for v in values]

    bars = ax.bar(labels, values, color=colors, width=0.5)
    
    # Линия нуля
    ax.axhline(0, color='#555555', linewidth=1, zorder=0)

    # Автоматически подписываем столбики (сверху или снизу)
    # Это самый надежный способ, он не ломает масштаб оси
    ax.bar_label(bars, fmt='%+.2f ₽', padding=5, color='white', fontsize=14, fontweight='bold')

    ax.set_title("Результат за день по режимам", color='#ffffff', pad=20, fontsize=16, fontweight='bold')
    
    # Убираем рамки
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['bottom'].set_visible(False)
    ax.spines['left'].set_visible(False)
    
    ax.tick_params(axis='x', colors='#aaaaaa', labelsize=14)
    ax.tick_params(axis='y', colors='#555555')

    # Защита от схлопывания графика, если PnL равен нулю
    max_val = max([abs(v) for v in values] + [10.0]) # минимум 10 рублей для масштаба
    ax.set_ylim(-max_val * 1.5, max_val * 1.5)

    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=150, facecolor='#1a1a1a', bbox_inches='tight')
    plt.close(fig)
    buf.seek(0)
    return buf

def main():
    history = load_json(HISTORY_FILE, [])
    config = load_json(CONFIG_FILE, {})

    now_time = datetime.now(KLG_TZ)
    today_str = now_time.strftime("%Y-%m-%d")
    date_formatted = now_time.strftime("%d.%m.%Y")

    # --- СБОР СТАТИСТИКИ ---
    today_wins = 0
    today_losses = 0
    today_pnl = 0.0
    intraday_today_pnl = 0.0
    swing_today_pnl = 0.0

    all_wins = 0
    all_losses = 0
    all_pnl = 0.0
    first_trade_dt = None

    for t in history:
        if t.get("type") != "SELL": continue
        
        pnl = t.get("pnl_rub", 0.0)
        mode = t.get("mode", "")
        res = t.get("result", "")
        exit_time = t.get("exit_time", "")
        
        # Общая статистика
        all_pnl += pnl
        if res == "WIN": all_wins += 1
        elif res == "LOSS": all_losses += 1

        # Дата самой первой сделки
        if "entry_time" in t:
            try:
                dt = datetime.fromisoformat(t["entry_time"])
                if first_trade_dt is None or dt < first_trade_dt:
                    first_trade_dt = dt
            except: pass

        # Статистика за СЕГОДНЯ
        if exit_time.startswith(today_str):
            today_pnl += pnl
            if res == "WIN": today_wins += 1
            elif res == "LOSS": today_losses += 1
            
            if mode == "intraday": intraday_today_pnl += pnl
            elif mode == "swing": swing_today_pnl += pnl

    # --- РАСЧЕТ МЕТРИК ---
    total_today_trades = today_wins + today_losses
    today_winrate = (today_wins / total_today_trades * 100) if total_today_trades > 0 else 0.0
    today_pnl_pct = (today_pnl / START_BALANCE) * 100

    total_all_trades = all_wins + all_losses
    all_winrate = (all_wins / total_all_trades * 100) if total_all_trades > 0 else 0.0
    all_pnl_pct = (all_pnl / START_BALANCE) * 100
    current_balance = START_BALANCE + all_pnl

    days_active = 1
    if first_trade_dt:
        days_active = (now_time - first_trade_dt.astimezone(KLG_TZ)).days + 1

    # --- ФОРМИРОВАНИЕ ТЕКСТА ---
    text = f"🌙 <b>Результаты торговли | {date_formatted}</b>\n\n"

    text += f"💰 <b>За сегодня:</b>\n"
    text += f"PnL: <b>{today_pnl:+.2f} ₽</b> ({today_pnl_pct:+.2f}%)\n"
    text += f"Баланс: {current_balance:.2f} ₽\n"
    text += f"Сделок: {total_today_trades} (WIN: {today_wins}, LOSS: {today_losses})\n"
    text += f"Винрейт: {today_winrate:.1f}%\n\n"

    text += f"📈 <b>За всё время ({days_active} дн.):</b>\n"
    text += f"Общий PnL: <b>{all_pnl:+.2f} ₽</b> ({all_pnl_pct:+.2f}%)\n"
    text += f"Всего сделок: {total_all_trades}\n"
    text += f"Винрейт: {all_winrate:.1f}%\n\n"

    if config:
        text += f"⚙️ <b>Текущие настройки аудита:</b>\n"
        if "intraday" in config:
            text += f"Intraday: Порог {config['intraday'].get('min_prob', 0.45)} | Трейлинг {config['intraday'].get('trail_mult', 0.8)}\n"
        if "swing" in config:
            text += f"Swing: Порог {config['swing'].get('min_prob', 0.45)} | Трейлинг {config['swing'].get('trail_mult', 0.8)}\n"
        text += "\n"

    text += "⚠️ <i>Не ИИР. Торговля — риск.</i>"

    # --- ГЕНЕРАЦИЯ И ОТПРАВКА ---
    log.info("Генерация графика...")
    chart_buf = create_pnl_chart(intraday_today_pnl, swing_today_pnl)

    log.info("Отправка в Telegram...")
    if send_telegram_photo(chart_buf, text):
        log.info("Вечерний отчет успешно отправлен в канал.")
    else:
        log.error("Ошибка отправки в Telegram.")
        sys.exit(1)

if __name__ == "__main__":
    main()