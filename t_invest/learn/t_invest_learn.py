# ============================================================
# T-INVEST - WEEKLY TRAINER ORCHESTRATOR (STOCKS) v2.0 (TOP-5 & FAST)
# Path: t_invest/learn/t_invest_learn.py
# ============================================================

import os
import json
import logging
import importlib.util
import requests
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timezone, timedelta
from t_tech.invest import Client
from t_tech.invest.constants import INVEST_GRPC_API
from t_tech.invest.schemas import CandleInterval
from t_tech.invest.utils import now

VERSION = "2.0-stocks-fast"
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("t_invest.trainer")

# --- НАСТРОЙКИ ПУТЕЙ ---
TOKEN = os.environ.get("T_INVEST_TOKEN")
TG_TOKEN = os.environ.get("INVEST_BOT_TOKEN")
TG_CHAT_ID = os.environ.get("INVEST_BOT_CHAT_ID")

WHITELIST_PATH = "t_invest/data/scanner/whitelist.json"
MODEL_OUT_FILE = Path("t_invest/data/model/best_params.json")
MODELS_SRC_DIR = Path("t_invest/learn/models")

# --- НАСТРОЙКИ ОБУЧЕНИЯ ---
TOP_N_STOCKS = 5        # Берем только 5 самых волатильных
HISTORY_DAYS = 90       # Берем 3 месяца истории для скорости

MODEL_OUT_FILE.parent.mkdir(parents=True, exist_ok=True)

def send_telegram(text):
    if not TG_TOKEN or not TG_CHAT_ID: return
    try:
        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": TG_CHAT_ID, "text": text, "parse_mode": "HTML"}, timeout=10)
    except Exception as e:
        log.error(f"Telegram error: {e}")

# --- ИНДИКАТОРЫ ---
def calculate_ema(series, period): return series.ewm(span=period, adjust=False).mean()

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def calculate_macd(series, fast=12, slow=26, signal=9):
    ema_fast = calculate_ema(series, fast)
    ema_slow = calculate_ema(series, slow)
    macd_line = ema_fast - ema_slow
    signal_line = calculate_ema(macd_line, signal)
    return macd_line - signal_line

def calculate_atr(df, period=14):
    high_low = df['high'] - df['low']
    high_close = (df['high'] - df['close'].shift()).abs()
    low_close = (df['low'] - df['close'].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()

def fetch_data_from_tinvest(client, figi, days=HISTORY_DAYS):
    end = now()
    start = end - timedelta(days=days)
    all_candles = []
    current = start
    while current < end:
        chunk_end = min(current + timedelta(days=90), end)
        try:
            resp = client.market_data.get_candles(
                figi=figi, from_=current, to=chunk_end, interval=CandleInterval.CANDLE_INTERVAL_HOUR
            )
            all_candles.extend(resp.candles)
        except Exception:
            pass
        current = chunk_end
    
    if not all_candles: return pd.DataFrame()
    
    rows = [{"open_time": c.time, "open": c.open.units + c.open.nano/1e9, "high": c.high.units + c.high.nano/1e9,
             "low": c.low.units + c.low.nano/1e9, "close": c.close.units + c.close.nano/1e9, "volume": c.volume} for c in all_candles]
    
    df = pd.DataFrame(rows)
    df['open_time'] = pd.to_datetime(df['open_time'], utc=True)
    return df

def load_models():
    models = []
    if not MODELS_SRC_DIR.exists(): return models
    for file_path in MODELS_SRC_DIR.glob("model_*.py"):
        model_name = file_path.stem
        try:
            spec = importlib.util.spec_from_file_location(model_name, file_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            if hasattr(module, "train"):
                models.append((model_name, module))
                log.info(f"Loaded model: {model_name}")
            else:
                log.warning(f"Model {model_name} skipped: no 'train' function.")
        except Exception as e:
            log.error(f"Failed to load model {model_name}: {e}")
    return models

def main():
    log.info(f"STARTING TRAINER ORCHESTRATOR v{VERSION}")
    
    if not TOKEN or not os.path.exists(WHITELIST_PATH):
        log.error("No token or whitelist.json missing.")
        return

    # 1. Читаем и сортируем акции по волатильности
    with open(WHITELIST_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    stocks = data["data"] if isinstance(data, dict) and "data" in data else data
    
    # Сортируем по среднему дневному размаху (avg_daily_range_pct), убывание
    stocks.sort(key=lambda x: x.get("avg_daily_range_pct", 0), reverse=True)
    top_stocks = stocks[:TOP_N_STOCKS]
    
    log.info(f"Selected TOP-{TOP_N_STOCKS} stocks for training: {[s['ticker'] for s in top_stocks]}")

    all_dfs = []
    with Client(TOKEN, target=INVEST_GRPC_API) as client:
        for s in top_stocks:
            ticker, figi = s["ticker"], s["figi"]
            df = fetch_data_from_tinvest(client, figi)
            if df.empty: continue

            # Индикаторы
            df['rsi'] = calculate_rsi(df['close'], 14)
            df['rsi_7'] = calculate_rsi(df['close'], 7)
            df['rsi_21'] = calculate_rsi(df['close'], 21)
            df['macd_hist'] = calculate_macd(df['close'], 12, 26, 9)
            df['ema_50'] = calculate_ema(df['close'], 50)
            df['ema_20'] = calculate_ema(df['close'], 20)
            df['ema_200'] = calculate_ema(df['close'], 200)
            df['vol_sma'] = df['volume'].rolling(window=20).mean()
            df['atr_7'] = calculate_atr(df, 7)
            df['atr_14'] = calculate_atr(df, 14)
            df['atr_50'] = calculate_atr(df, 50)
            df['atr_100'] = calculate_atr(df, 100)
            df['price_change_1h'] = df['close'].pct_change(1)
            df['price_change_4h'] = df['close'].pct_change(4)
            df['price_change_24h'] = df['close'].pct_change(24)
            
            df = df.dropna()
            if len(df) > 100:
                df['ticker'] = ticker
                all_dfs.append(df)
            log.info(f"Loaded {ticker}: {len(df)} rows")

    if not all_dfs:
        log.error("No data downloaded.")
        return

    # Склеиваем в один датафрейм
    full_df = pd.concat(all_dfs).sort_values('open_time').reset_index(drop=True)
    log.info(f"Data ready. Total rows: {len(full_df)}")

    models = load_models()
    if not models:
        log.error("No models found!")
        return

    out_data = {
        "trainer_version": VERSION,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "selected_tickers": [s["ticker"] for s in top_stocks],
        "total_rows": len(full_df),
        "intraday": {"long": None, "short": None},
        "swing": {"long": None, "short": None},
        "all_scores": {}
    }

    for mode in ["intraday", "swing"]:
        out_data["all_scores"][mode] = {}
        for side in ["long", "short"]:
            log.info(f"--- Searching best model for {mode.upper()} / {side.upper()} ---")
            best_score = -99999
            best_model_data = None
            model_scores = {}

            for model_name, module in models:
                try:
                    res = module.train(full_df, side=side, mode=mode)
                    if res and res.get("metrics"):
                        sc = res["metrics"].get("score", -99999)
                        model_scores[model_name] = res["metrics"]
                        if sc > best_score:
                            best_score = sc
                            res["source"] = model_name
                            best_model_data = res
                            log.info(f"  🏆 New best: {model_name} (Score: {sc})")
                except Exception as e:
                    log.error(f"  ❌ Model {model_name} crashed on {mode}/{side}: {e}")
                    model_scores[model_name] = {"error": str(e)}
                    
            if best_model_data:
                out_data[mode][side] = best_model_data
            out_data["all_scores"][mode][side] = model_scores

    with open(MODEL_OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(out_data, f, ensure_ascii=False, indent=2)
    log.info(f"💾 Saved to {MODEL_OUT_FILE}")

    # Отчет в Телеграм
    msg = f"🏆 <b>Обучение завершено (TOP-{TOP_N_STOCKS})</b>\n\n📊 Акции: {', '.join([s['ticker'] for s in top_stocks])}\n\n"
    for mode in ["intraday", "swing"]:
        for side in ["long", "short"]:
            res = out_data[mode][side]
            if res:
                msg += f"<b>{mode.upper()} {side.upper()}</b>: {res['source']} (Score: {res['metrics']['score']})\n"
            else:
                msg += f"<b>{mode.upper()} {side.upper()}</b>: Нет результатов\n"
    
    send_telegram(msg)
    log.info("Done.")

if __name__ == "__main__":
    main()