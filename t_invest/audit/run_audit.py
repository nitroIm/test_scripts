# ============================================================
# T-INVEST - AUDIT RUNNER (FINAL LOGIC)
# Path: t_invest/audit/run_audit.py
# ============================================================

import os
import json
import logging
import requests
from pathlib import Path
from datetime import datetime, timezone, timedelta

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("audit")

BASE_DIR = Path(__file__).resolve().parent.parent.parent
HISTORY_FILE = BASE_DIR / "t_invest/data/simulator/trade_history.json"
CONFIG_FILE = BASE_DIR / "t_invest/data/simulator/simulator_config.json"
STATE_FILE = BASE_DIR / "t_invest/data/simulator/state.json" # Нужен для проверки лимитов

TG_TOKEN = os.environ.get("INVEST_BOT_TOKEN")
TG_CHAT_ID = os.environ.get("INVEST_BOT_CHAT_ID")
KLG_TZ = timezone(timedelta(hours=2))

def send_tg(text):
    if not TG_TOKEN or not TG_CHAT_ID: return
    try:
        requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", json={"chat_id": TG_CHAT_ID, "text": text, "parse_mode": "HTML"}, timeout=10)
    except Exception as e:
        log.error(f"TG error: {e}")

def load_json(path, default):
    if not path.exists(): return default
    try:
        with open(path, "r", encoding="utf-8") as f: return json.load(f)
    except: return default

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def main():
    log.info("STARTING AUDIT")
    
    history = load_json(HISTORY_FILE, [])
    state = load_json(STATE_FILE, {})
    
    config = load_json(CONFIG_FILE, {
        "intraday": {"min_prob": 0.45, "trail_mult": 0.8, "news_block": -0.5, "starvation_count": 0},
        "swing": {"min_prob": 0.45, "trail_mult": 0.8, "news_block": -0.5, "starvation_count": 0}
    })

    # Защита от старых конфигов
    for mode in ["intraday", "swing"]:
        if "starvation_count" not in config[mode]:
            config[mode]["starvation_count"] = 0

    today_str = datetime.now(KLG_TZ).strftime("%Y-%m-%d")
    changes_made = []
    
    for mode in ["intraday", "swing"]:
        # Берем закрытые сделки за сегодня
        today_sells = [t for t in history if t.get("type") == "SELL" and t.get("mode") == mode and t.get("exit_time", "").startswith(today_str)]
        
        total_trades = len(today_sells)
        wins = sum(1 for t in today_sells if t.get("result") == "WIN")
        winrate = (wins / total_trades * 100) if total_trades > 0 else 0.0
        
        # Считаем убытки подряд
        consecutive_losses = 0
        for t in reversed(today_sells):
            if t.get("result") == "LOSS":
                consecutive_losses += 1
            else:
                break
        
        # Проверяем лимит сделок (чтобы не включать голодание, если лимит исчерпан)
        max_trades = 3 if mode == "intraday" else 2
        daily_trades_count = state.get("daily_trades", {}).get(mode, 0)
        limit_reached = daily_trades_count >= max_trades

        log.info(f"{mode.upper()}: Сделок: {total_trades}, Винрейт: {winrate:.1f}%, Убытков подряд: {consecutive_losses}, Голодание: {config[mode]['starvation_count']}, Лимит: {limit_reached}")

        # ЛОГИКА 1: Мясорубка (много сделок, плохой винрейт)
        if total_trades >= 5 and winrate < 40.0:
            old_prob = config[mode]["min_prob"]
            config[mode]["min_prob"] = min(0.75, round(old_prob + 0.02, 2))
            config[mode]["trail_mult"] = min(1.5, round(config[mode]["trail_mult"] + 0.2, 1))
            config[mode]["starvation_count"] = 0
            if old_prob != config[mode]["min_prob"]:
                changes_made.append(f"{mode.upper()}: Винрейт {winrate:.1f}% на {total_trades} сделках. Порог: {old_prob}->{config[mode]['min_prob']}.")
        
        # ЛОГИКА 2: Серия убытков
        elif consecutive_losses >= 3:
            old_prob = config[mode]["min_prob"]
            config[mode]["min_prob"] = min(0.75, round(old_prob + 0.02, 2))
            config[mode]["trail_mult"] = min(1.5, round(config[mode]["trail_mult"] + 0.2, 1))
            config[mode]["starvation_count"] = 0
            if old_prob != config[mode]["min_prob"]:
                changes_made.append(f"{mode.upper()}: {consecutive_losses} LOSS подряд. Порог: {old_prob}->{config[mode]['min_prob']}.")

        # ЛОГИКА 3: Голодание (нет сделок, лимит не исчерпан)
        elif total_trades == 0 and not limit_reached:
            config[mode]["starvation_count"] += 1
            log.info(f"{mode.upper()}: Нет сделок. Счетчик голодания: {config[mode]['starvation_count']}/2")
            
            if config[mode]["starvation_count"] >= 2:
                old_prob = config[mode]["min_prob"]
                config[mode]["min_prob"] = max(0.35, round(old_prob - 0.02, 2))
                config[mode]["starvation_count"] = 0
                if old_prob != config[mode]["min_prob"]:
                    changes_made.append(f"{mode.upper()}: 2 часа без сделок. Порог снижен: {old_prob}->{config[mode]['min_prob']}")

        # В остальных случаях просто сбрасываем счетчик голодания
        else:
            config[mode]["starvation_count"] = 0

    if changes_made:
        save_json(CONFIG_FILE, config)
        msg = "🚨 <b>АУДИТ ВНЕС ИЗМЕНЕНИЯ</b>\n\n" + "\n".join([f"• {c}" for c in changes_made])
        send_tg(msg)
        log.info("Config updated.")
    else:
        log.info("Изменений не требуется. Бот в норме.")

if __name__ == "__main__":
    main()