# ============================================================
# T-INVEST - LEARN REPORT BOT
# Path: t_invest/reports/t_invest_learn_report.py
# ============================================================

import os
import json
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path

TOKEN = os.environ.get("INVEST_BOT_TOKEN")
CHAT_ID = os.environ.get("INVEST_BOT_CHAT_ID")
MODEL_OUT_FILE = Path("t_invest/data/model/best_params.json")

# Калининградское время (UTC+2)
KLG_TZ = timezone(timedelta(hours=2))

def send_telegram(text):
    if not TOKEN or not CHAT_ID:
        print("Telegram secrets missing.")
        return
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}
    try:
        requests.post(url, json=payload, timeout=10)
        print("Report sent to Telegram.")
    except Exception as e:
        print(f"Telegram error: {e}")

def main():
    if not MODEL_OUT_FILE.exists():
        print("best_params.json not found.")
        return

    with open(MODEL_OUT_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Извлекаем данные
    tickers = data.get("long_tickers", [])
    intraday = data.get("intraday", {}).get("long")
    swing = data.get("swing", {}).get("long")
    stats = data.get("stats", {})
    
    elapsed_sec = stats.get("elapsed_seconds", 0)
    elapsed_min = elapsed_sec // 60
    elapsed_sec_rem = elapsed_sec % 60
    total_rows = stats.get("total_rows", 0)

    now_klg = datetime.now(KLG_TZ)
    tickers_str = ", ".join(tickers)

    # Формируем сообщение
    msg = f"🏆 <b>Обучение завершено (LONG)</b>\n\n"
    msg += f"⏱ <b>Время:</b> {elapsed_min} мин {elapsed_sec_rem} сек\n"
    msg += f"📅 <b>Дата (КЛГ):</b> {now_klg.strftime('%d.%m.%Y в %H:%M')}\n"
    msg += f"📊 <b>Данные:</b> {len(tickers)} акций ({tickers_str}) | {total_rows} строк\n\n"
    
    if intraday:
        msg += f"🥇 <b>INTRADAY:</b> {intraday['source']} (Score: {intraday['metrics']['score']})\n"
    if swing:
        msg += f"🥈 <b>SWING:</b> {swing['source']} (Score: {swing['metrics']['score']})\n"
    
    msg += f"\n🤖 <i>Бот готов к торговле по лучшим моделям.</i>"
    
    send_telegram(msg)

if __name__ == "__main__":
    main()