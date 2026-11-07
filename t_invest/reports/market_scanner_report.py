# PROD CONTOUR ONLY
# Python: 3.10
# Файл: t_invest/reports/market_scanner_report.py

import os
import json
import requests
from datetime import datetime, timedelta, timezone

TOKEN = os.environ.get("INVEST_BOT_TOKEN")
CHAT_ID = os.environ.get("INVEST_BOT_CHAT_ID")
WHITELIST_PATH = "t_invest/data/scanner/whitelist.json"

# Калининградское время (UTC+2)
KLG_TZ = timezone(timedelta(hours=2))

def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML"
    }
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code != 200:
            print(f"❌ Ошибка Telegram API: {response.text}")
        else:
            print("✅ Отчет успешно отправлен в Telegram!")
    except Exception as e:
        print(f"❌ Ошибка отправки запроса: {e}")

def format_money(value):
    """Красиво форматирует суммы: 1 500 000 000 -> 1.5 млрд, 50 000 000 -> 50.0 млн"""
    if value >= 1_000_000_000:
        return f"{value / 1_000_000_000:,.2f} млрд ₽".replace(",", " ")
    else:
        return f"{value / 1_000_000:,.1f} млн ₽".replace(",", " ")

def get_advice(stock):
    """Генерирует краткий совет по торговле на основе метрик"""
    vol = stock.get("volatility_tag", "")
    trend = stock.get("trend", "")
    
    advice = []
    # Совет по волатильности
    if vol == "HIGH_VOL":
        advice.append("🔥 Подходит для агрессивного дейтрейдинга (быстрый вход/выход).")
    elif vol == "MID_VOL":
        advice.append("⚖️ Сбалансированная волатильность для краткосрочных сделок.")
    elif vol == "LOW_VOL":
        advice.append("🛡️ Низкий риск, подходит для консервативных позиций или ручной торговли.")
        
    # Совет по тренду
    if trend == "UP":
        advice.append("📈 Растущий тренд — можно искать точку входа в лонг.")
    elif trend == "DOWN":
        advice.append("📉 Падающий тренд — рискованно для покупки, лучше наблюдать.")
    else:
        advice.append("↔️ Боковик — цена стоит на месте, ждем пробоя.")
        
    return " ".join(advice)

def main():
    if not TOKEN or not CHAT_ID:
        print("❌ Не заданы INVEST_BOT_TOKEN или INVEST_BOT_CHAT_ID")
        return

    if not os.path.exists(WHITELIST_PATH):
        print("❌ Файл whitelist.json не найден.")
        return

    with open(WHITELIST_PATH, "r", encoding="utf-8") as f:
        content = f.read().strip()
        if not content:
            print("❌ Файл whitelist.json пуст.")
            return
        data = json.loads(content)

    # Поддержка нового формата с метаданными
    if isinstance(data, dict) and "data" in data:
        stocks = data["data"]
        collected_at_str = data.get("metadata", {}).get("collected_at", "")
    elif isinstance(data, list):
        stocks = data
        collected_at_str = ""
    else:
        print("❌ Неизвестный формат whitelist.json")
        return

    if not stocks:
        send_telegram_message("⚠️ Сканер не нашел сегодня ликвидных акций.")
        return

    # Сортируем по среднему дневному обороту (самые ликвидные) и берем ТОП-5
    top_5 = sorted(stocks, key=lambda x: x.get("avg_daily_turnover_rub", 0), reverse=True)[:5]

    # Конвертация времени сбора данных в Калининград
    time_str = "Неизвестно"
    if collected_at_str:
        try:
            # Парсим ISO строку и конвертируем в KLG
            dt_utc = datetime.fromisoformat(collected_at_str.replace("Z", "+00:00"))
            dt_klg = dt_utc.astimezone(KLG_TZ)
            time_str = dt_klg.strftime("%d.%m.%Y в %H:%M (КЛГ)")
        except Exception:
            pass

    # Формируем сообщение
    date_str = datetime.now(KLG_TZ).strftime("%d.%m.%Y")
    msg = f"📊 <b>ТОП-5 ЛИКВИДНЫХ АКЦИЙ НА {date_str}</b>\n\n"

    for i, stock in enumerate(top_5, 1):
        ticker = stock.get("ticker", "???")
        name = stock.get("name", "")
        price = stock.get("last_price", 0.0)
        turnover = stock.get("avg_daily_turnover_rub", 0)
        vol_tag = stock.get("volatility_tag", "N/A")
        trend = stock.get("trend", "N/A")
        trade_method = stock.get("trade_method", "API")
        spread = stock.get("spread_pct", 0.0)

        # Эмодзи для визуализации
        trend_emoji = "🟢" if trend == "UP" else "🔴" if trend == "DOWN" else "⚪️"
        method_emoji = "🤖" if trade_method == "API" else "✋"

        msg += (
            f"{i}. <b>{ticker}</b> ({name[:25]})\n"
            f"💰 Цена: {price:,.2f} ₽\n".replace(",", " ") +
            f"📈 Оборот: {format_money(turnover)}\n"
            f"📏 Спред: {spread:.2f}%\n"
            f"⚡️ Волатильность: {vol_tag}\n"
            f"{trend_emoji} Тренд: {trend}\n"
            f"{method_emoji} Режим: {trade_method}\n"
            f"💡 <i>{get_advice(stock)}</i>\n\n"
        )

    msg += f"<i>Всего в белом списке: {len(stocks)} акций.\nДанные собраны: {time_str}</i>"

    send_telegram_message(msg)

if __name__ == "__main__":
    main()