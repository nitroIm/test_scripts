# ============================================================
# T-INVEST - AUDIT RUNNER
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

# Настройки путей
BASE_DIR = Path(__file__).resolve().parent.parent.parent
HISTORY_FILE = BASE_DIR / "t_invest/data/simulator/trade_history.json"
CONFIG_FILE = BASE_DIR / "t_invest/data/simulator/simulator_config.json"

# Telegram
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
    config = load_json(CONFIG_FILE, {
        "intraday": {"min_prob": 0.45, "trail_mult": 0.8, "news_block": -0.5},
        "swing": {"min_prob": 0.45, "trail_mult": 0.8, "news_block": -0.5}
    })

    today_str = datetime.now(KLG_TZ).strftime("%Y-%m-%d")
    changes_made = []
    
    # Анализируем каждый режим отдельно
    for mode in ["intraday", "swing"]:
        # Берем сделки за сегодня для этого режима
        today_trades = [t for t in history if t.get("type") == "SELL" and t.get("mode") == mode and t.get("exit_time", "").startswith(today_str)]
        
        # Считаем убытки подряд (с конца)
        consecutive_losses = 0
        for t in reversed(today_trades):
            if t.get("result") == "LOSS":
                consecutive_losses += 1
            else:
                break
        
        log.info(f"{mode.upper()}: Сделок за сегодня: {len(today_trades)}, Убытков подряд: {consecutive_losses}")

        # === ЛОГИКА ИЗМЕНЕНИЙ ===
        # 1. Если 3 и более убытка подряд -> Повышаем порог и расширяем трейлинг
        if consecutive_losses >= 3:
            old_prob = config[mode]["min_prob"]
            old_trail = config[mode]["trail_mult"]
            
            # Поднимаем порог (максимум до 0.65)
            config[mode]["min_prob"] = min(0.65, round(old_prob + 0.02, 2))
            # Расширяем трейлинг (максимум до 1.5)
            config[mode]["trail_mult"] = min(1.5, round(old_trail + 0.2, 1))
            
            if old_prob != config[mode]["min_prob"] or old_trail != config[mode]["trail_mult"]:
                changes_made.append(f"{mode.upper()}: {consecutive_losses} LOSS подряд. Порог: {old_prob}->{config[mode]['min_prob']}. Трейлинг: {old_trail}->{config[mode]['trail_mult']}")

        # 2. Если 0 сделок за сегодня (к концу дня) -> Понижаем порог, чтобы заставить торговать
        # (Это стоит запускать только вечером, но для теста оставим так)
        elif len(today_trades) == 0:
            old_prob = config[mode]["min_prob"]
            config[mode]["min_prob"] = max(0.35, round(old_prob - 0.02, 2))
            if old_prob != config[mode]["min_prob"]:
                changes_made.append(f"{mode.upper()}: 0 сделок. Порог снижен: {old_prob}->{config[mode]['min_prob']}")

    if changes_made:
        save_json(CONFIG_FILE, config)
        log.info("Config updated.")
        
        msg = "🚨 <b>АУДИТ ВНЕС ИЗМЕНЕНИЯ</b>\n\n"
        msg += "\n".join([f"• {c}" for c in changes_made])
        send_tg(msg)
    else:
        log.info("Изменений не требуется. Винрейт в норме.")

if __name__ == "__main__":
    main()