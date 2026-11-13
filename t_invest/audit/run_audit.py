# ============================================================
# T-INVEST - AUDIT RUNNER (SMART STARVATION & LOSS LOGIC)
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
    
    # Добавляем поле starvation_count в дефолтный конфиг
    config = load_json(CONFIG_FILE, {
        "intraday": {"min_prob": 0.45, "trail_mult": 0.8, "news_block": -0.5, "starvation_count": 0},
        "swing": {"min_prob": 0.45, "trail_mult": 0.8, "news_block": -0.5, "starvation_count": 0}
    })

    # На случай, если старый конфиг без поля starvation_count
    for mode in ["intraday", "swing"]:
        if "starvation_count" not in config[mode]:
            config[mode]["starvation_count"] = 0

    today_str = datetime.now(KLG_TZ).strftime("%Y-%m-%d")
    changes_made = []
    
    for mode in ["intraday", "swing"]:
        # Собираем ВСЕ сделки за сегодня (и покупки, и продажи) для этого режима
        today_trades = [t for t in history if t.get("mode") == mode and t.get("entry_time", "").startswith(today_str)]
        
        # Считаем убытки подряд (только закрытые сделки)
        today_sells = [t for t in today_trades if t.get("type") == "SELL"]
        consecutive_losses = 0
        for t in reversed(today_sells):
            if t.get("result") == "LOSS":
                consecutive_losses += 1
            else:
                break
        
        log.info(f"{mode.upper()}: Сделок за сегодня: {len(today_trades)}, Убытков подряд: {consecutive_losses}, Голодание: {config[mode]['starvation_count']}")

        # === ЛОГИКА 1: СЕРИЯ УБЫТКОВ (Повышаем порог) ===
        if consecutive_losses >= 3:
            old_prob = config[mode]["min_prob"]
            old_trail = config[mode]["trail_mult"]
            
            config[mode]["min_prob"] = min(0.65, round(old_prob + 0.02, 2))
            config[mode]["trail_mult"] = min(1.5, round(old_trail + 0.2, 1))
            config[mode]["starvation_count"] = 0 # Сбрасываем голодание
            
            if old_prob != config[mode]["min_prob"] or old_trail != config[mode]["trail_mult"]:
                changes_made.append(f"{mode.upper()}: {consecutive_losses} LOSS подряд. Порог: {old_prob}->{config[mode]['min_prob']}. Трейлинг: {old_trail}->{config[mode]['trail_mult']}")

        # === ЛОГИКА 2: ГОЛОДАНИЕ (Понижаем порог, если 0 сделок) ===
        elif len(today_trades) == 0:
            config[mode]["starvation_count"] += 1
            log.info(f"{mode.upper()}: Нет сделок. Счетчик голодания: {config[mode]['starvation_count']}/3")
            
            # Если 3 часа подряд нет сделок — снижаем порог
            if config[mode]["starvation_count"] >= 3:
                old_prob = config[mode]["min_prob"]
                config[mode]["min_prob"] = max(0.35, round(old_prob - 0.02, 2))
                config[mode]["starvation_count"] = 0 # Сбрасываем счетчик после снижения
                
                if old_prob != config[mode]["min_prob"]:
                    changes_made.append(f"{mode.upper()}: 3 часа без сделок (голодание). Порог снижен: {old_prob}->{config[mode]['min_prob']}")

        # Если сделки были, но мало (1-2), просто сбрасываем счетчик голодания
        else:
            config[mode]["starvation_count"] = 0

    if changes_made:
        save_json(CONFIG_FILE, config)
        log.info("Config updated.")
        
        msg = "🚨 <b>АУДИТ ВНЕС ИЗМЕНЕНИЯ</b>\n\n"
        msg += "\n".join([f"• {c}" for c in changes_made])
        send_tg(msg)
    else:
        log.info("Изменений не требуется. Бот в норме.")

if __name__ == "__main__":
    main()