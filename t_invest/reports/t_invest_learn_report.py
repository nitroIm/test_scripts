# ============================================================
# T-INVEST - LEARN REPORT BOT v2.0
# Path: t_invest/reports/t_invest_learn_report.py
# ============================================================

import os
import json
import sys
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path

TOKEN = os.environ.get("INVEST_BOT_TOKEN")
CHAT_ID = os.environ.get("INVEST_BOT_CHAT_ID")
MODEL_OUT_FILE = Path("t_invest/data/model/best_params.json")
WHITELIST_FILE = Path("t_invest/data/scanner/whitelist.json")

# Калининградское время (UTC+2)
KLG_TZ = timezone(timedelta(hours=2))

# Минимум данных, при котором обучение считается состоявшимся
MIN_TICKERS = 3
MIN_ROWS = 500


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


def load_json(path):
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Ошибка чтения {path}: {e}")
        return None


def main():
    if not MODEL_OUT_FILE.exists():
        msg = (
            "🚫 <b>Обучение НЕ выполнено</b>\n\n"
            "best_params.json не найден — тренер не записал результаты.\n"
            "Проверь лог шага тренера в workflow."
        )
        print("best_params.json not found.")
        send_telegram(msg)
        sys.exit(1)

    data = load_json(MODEL_OUT_FILE)
    if data is None:
        msg = "🚫 <b>Обучение НЕ выполнено</b>\n\nbest_params.json битый (не читается как JSON)."
        send_telegram(msg)
        sys.exit(1)

    # --- ИЗВЛЕКАЕМ ДАННЫЕ ---
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

    # --- ВАЛИДАЦИЯ: пустое обучение = провал, а не победа ---
    if len(tickers) < MIN_TICKERS or total_rows < MIN_ROWS:
        wl = load_json(WHITELIST_FILE)
        wl_count = 0
        wl_hint = "whitelist.json не найден — проверь шаг сканера."
        if wl is not None:
            wl_count = len(wl.get("data", []))
            if wl_count > 0:
                wl_hint = (
                    f"Сканер нашёл {wl_count} бумаг, но тренер их не получил.\n"
                    "Проверь передачу whitelist между шагами."
                )
            else:
                wl_hint = "Сканер вернул ПУСТОЙ список бумаг — проверь запрос к базе в сканере."

        msg = (
            "⚠️ <b>Обучение НЕ состоялось</b>\n\n"
            f"📅 Дата (КЛГ): {now_klg.strftime('%d.%m.%Y в %H:%M')}\n"
            f"📊 Тикеров: <b>{len(tickers)}</b> | Строк: <b>{total_rows}</b>\n\n"
            f"Диагноз: {wl_hint}"
        )
        print(f"FAIL: tickers={len(tickers)}, rows={total_rows}")
        send_telegram(msg)
        sys.exit(1)  # шаг падает — Notify on failure тоже сработает

    # --- УСПЕШНОЕ ОБУЧЕНИЕ ---
    msg = f"🏆 <b>Обучение завершено (LONG)</b>\n\n"
    msg += f"⏱ <b>Время:</b> {elapsed_min} мин {elapsed_sec_rem} сек\n"
    msg += f"📅 <b>Дата (КЛГ):</b> {now_klg.strftime('%d.%m.%Y в %H:%M')}\n"
    msg += f"📊 <b>Данные:</b> {len(tickers)} акций ({tickers_str}) | {total_rows} строк\n\n"

    if intraday:
        msg += f"🥇 <b>INTRADAY:</b> {intraday['source']} (Score: {intraday['metrics']['score']})\n"
    else:
        msg += "🥇 <b>INTRADAY:</b> нет данных\n"

    if swing:
        msg += f"🥈 <b>SWING:</b> {swing['source']} (Score: {swing['metrics']['score']})\n"
    else:
        msg += "🥈 <b>SWING:</b> нет данных\n"

    msg += f"\n🤖 <i>Бот готов к торговле по лучшим моделям.</i>"

    print("OK")
    send_telegram(msg)


if __name__ == "__main__":
    main()
