# ============================================================
# T-INVEST - WEEKLY TRAINER ORCHESTRATOR v1.0 (STOCKS)
# Path: t_invest/learn/t_invest_learn.py
# ============================================================

import os
import sys
import json
import logging
import itertools
import requests
import numpy as np
import pandas as pd
from datetime import datetime, timezone, timedelta
from t_tech.invest import Client
from t_tech.invest.constants import INVEST_GRPC_API
from t_tech.invest.schemas import CandleInterval
from t_tech.invest.utils import now

# === НАСТРОЙКИ ===
TOKEN = os.environ.get("T_INVEST_TOKEN")
TG_TOKEN = os.environ.get("INVEST_BOT_TOKEN")
TG_CHAT_ID = os.environ.get("INVEST_BOT_CHAT_ID")
WHITELIST_PATH = "t_invest/data/scanner/whitelist.json"
MODEL_OUT_FILE = "t_invest/data/model/best_params.json"

# Параметры бэктеста (взято из ARGUS)
INITIAL_BALANCE = 100.0
POSITION_NOTIONAL = 20.0
FEE_RATE = 0.0005 # Комиссия Т-Инвест
MIN_TRADES_FOR_FULL_SCORE = 30 # Для акций снижено (меньше сделок, чем на крипте)

# Сетки параметров (взято из ARGUS)
GRID_SWING = {
    "use_trend_filter": [True, False],
    "use_volume_filter": [True, False],
    "rsi_min": [25, 30, 35],
    "rsi_max": [50, 55, 60, 70],
    "tp_pct": [3.0, 5.0, 8.0, 15.0],
    "sl_pct": [2.0, 3.0, 5.0, 10.0],
    "time_exit_h": [24, 48, 72, 168]
}

GRID_INTRADAY = {
    "use_trend_filter": [True, False],
    "use_volume_filter": [True, False],
    "rsi_min": [25, 30, 35],
    "rsi_max": [50, 55, 60, 70],
    "tp_pct": [1.0, 1.5, 2.0, 3.0],
    "sl_pct": [0.5, 1.0, 1.5, 2.0],
    "time_exit_h": [4, 8, 12, 24]
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("t_invest.trainer")

def send_telegram(text):
    if not TG_TOKEN or not TG_CHAT_ID: return
    try:
        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": TG_CHAT_ID, "text": text, "parse_mode": "HTML"}, timeout=10)
    except Exception as e:
        log.error(f"Telegram error: {e}")

# === ИНДИКАТОРЫ ===
def calc_ema(series, period): return series.ewm(span=period, adjust=False).mean()

def calc_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def calc_macd_hist(series, fast=12, slow=26, signal=9):
    ema_fast = calc_ema(series, fast)
    ema_slow = calc_ema(series, slow)
    macd_line = ema_fast - ema_slow
    signal_line = calc_ema(macd_line, signal)
    return macd_line - signal_line

def calc_atr(df, period=14):
    high_low = df['high'] - df['low']
    high_close = (df['high'] - df['close'].shift()).abs()
    low_close = (df['low'] - df['close'].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()

# === ЗАГРУЗКА ДАННЫХ ИЗ T-INVEST ===
def fetch_data_from_tinvest(client, figi, days=365):
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
        except Exception as e:
            log.warning(f"Chunk error {figi}: {e}")
        current = chunk_end
    
    if not all_candles: return pd.DataFrame()
    
    rows = [{"time": c.time, "open": c.open.units + c.open.nano/1e9, "high": c.high.units + c.high.nano/1e9,
             "low": c.low.units + c.low.nano/1e9, "close": c.close.units + c.close.nano/1e9, "volume": c.volume} for c in all_candles]
    
    df = pd.DataFrame(rows)
    df['time'] = pd.to_datetime(df['time'], utc=True)
    return df

# === БЭКТЕСТ (ЛОГИКА ARGUS) ===
def run_backtest(df, params, side="long"):
    trades = []
    in_pos = False
    entry_price = 0.0
    entry_idx = 0

    for i, curr in enumerate(df.itertuples()):
        if i == 0: continue
        
        if in_pos:
            if side == "long":
                gross_pct = (curr.close - entry_price) / entry_price * 100.0
            else:
                gross_pct = (entry_price - curr.close) / entry_price * 100.0

            bars_held = i - entry_idx
            exit_reason = None
            
            if gross_pct <= -params["sl_pct"]: exit_reason = "STOP_LOSS"
            elif gross_pct >= params["tp_pct"]: exit_reason = "TAKE_PROFIT"
            elif bars_held >= params["time_exit_h"]: exit_reason = "TIME_EXIT"
                
            if exit_reason:
                net_pct = gross_pct - (FEE_RATE * 200)
                pnl_usd = POSITION_NOTIONAL * (net_pct / 100.0)
                trades.append(pnl_usd)
                in_pos = False
        
        if not in_pos:
            if side == "long":
                signal = curr.macd_hist > 0 and (params["rsi_min"] < curr.rsi < params["rsi_max"])
                if params["use_trend_filter"]: signal = signal and (curr.close > curr.ema_50)
            else:
                signal = curr.macd_hist < 0 and (params["rsi_min"] < curr.rsi < params["rsi_max"])
                if params["use_trend_filter"]: signal = signal and (curr.close < curr.ema_50)

            if params["use_volume_filter"]: signal = signal and (curr.volume > curr.vol_sma)
                
            if signal:
                in_pos = True
                entry_price = curr.close
                entry_idx = i

    n = len(trades)
    if n == 0: return None

    pnls = np.array(trades)
    total_pnl = float(pnls.sum())
    cum = np.cumsum(pnls) + INITIAL_BALANCE
    peak = np.maximum.accumulate(cum)
    dd = (cum - peak) / peak * 100.0
    max_dd = float(dd.min()) if len(dd) else 0.0
    if max_dd == 0: max_dd = -0.1

    raw_score = total_pnl / abs(max_dd)
    trade_penalty = min(1.0, n / MIN_TRADES_FOR_FULL_SCORE)
    adjusted_score = raw_score * trade_penalty
    
    return {"trades": n, "pnl": round(total_pnl, 2), "winrate": round(float((pnls > 0).mean()), 4),
            "max_dd": round(max_dd, 2), "score": round(adjusted_score, 2), "raw_score": round(raw_score, 2)}

# === ТРЕНЕР (ПЕРЕБОР СЕТКИ) ===
def train_grid_search(df, side="long", mode="swing"):
    grid = GRID_INTRADAY if mode == "intraday" else GRID_SWING
    keys, values = zip(*grid.items())
    combinations = [dict(zip(keys, v)) for v in itertools.product(*values)]
    
    best_result = None
    best_params = None

    for params in combinations:
        res = run_backtest(df, params, side=side)
        if res and (best_result is None or res["score"] > best_result["score"]):
            best_result = res
            best_params = params

    if not best_params: return None
    return {"params": best_params, "metrics": best_result}

# === ГЛАВНЫЙ ОРКЕСТРАТОР ===
def main():
    log.info("STARTING T-INVEST WEEKLY TRAINER ORCHESTRATOR v1.0")
    
    if not TOKEN or not os.path.exists(WHITELIST_PATH):
        log.error("No token or whitelist.json missing.")
        return

    with open(WHITELIST_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    stocks = data["data"] if isinstance(data, dict) and "data" in data else data
    
    all_dfs = []
    data_start_time = None
    data_end_time = None
    
    log.info("Downloading data from T-Invest...")
    with Client(TOKEN, target=INVEST_GRPC_API) as client:
        for s in stocks:
            ticker, figi = s["ticker"], s["figi"]
            df = fetch_data_from_tinvest(client, figi)
            if df.empty: continue
            
            if data_start_time is None or df['time'].min() < data_start_time: data_start_time = df['time'].min()
            if data_end_time is None or df['time'].max() > data_end_time: data_end_time = df['time'].max()

            # Индикаторы
            df['rsi'] = calc_rsi(df['close'], 14)
            df['macd_hist'] = calc_macd_hist(df['close'], 12, 26, 9)
            df['ema_50'] = calc_ema(df['close'], 50)
            df['vol_sma'] = df['volume'].rolling(window=20).mean()
            df['atr_14'] = calc_atr(df, 14)
            
            df = df.dropna()
            if len(df) > 100:
                df['ticker'] = ticker
                all_dfs.append(df)
            log.info(f"Loaded {ticker}: {len(df)} rows")

    if not all_dfs:
        log.error("No data downloaded.")
        return

    # Склеиваем все акции в один датафрейм
    full_df = pd.concat(all_dfs).reset_index(drop=True)
    log.info(f"Total combined rows: {len(full_df)}")

    out_data = {
        "trainer_version": "1.0-stocks",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "data_start": data_start_time.strftime("%Y-%m-%d"),
        "data_end": data_end_time.strftime("%Y-%m-%d"),
        "total_rows": len(full_df),
        "intraday": {"long": None, "short": None},
        "swing": {"long": None, "short": None}
    }

    # Прогон по 4 режимам (intraday/swing x long/short)
    for mode in ["intraday", "swing"]:
        for side in ["long", "short"]:
            log.info(f"--- Searching best params for {mode.upper()} / {side.upper()} ---")
            best_data = train_grid_search(full_df, side=side, mode=mode)
            if best_data:
                out_data[mode][side] = best_data
                log.info(f"  🏆 Best Score: {best_data['metrics']['score']} | Params: {best_data['params']}")
            else:
                log.warning(f"  ⚠️ No trades generated for {mode}/{side}")

    os.makedirs(os.path.dirname(MODEL_OUT_FILE), exist_ok=True)
    with open(MODEL_OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(out_data, f, ensure_ascii=False, indent=2)
    log.info(f"💾 Saved to {MODEL_OUT_FILE}")

    # Отправка в телеграм
    msg = (
        f"🏆 <b>Обучение (ARGUS Grid) завершено</b>\n\n"
        f"📅 Период: {out_data['data_start']} — {out_data['data_end']}\n"
        f"📊 Всего строк: {len(full_df)}\n\n"
    )
    for mode in ["intraday", "swing"]:
        for side in ["long", "short"]:
            res = out_data[mode][side]
            if res:
                msg += f"<b>{mode.upper()} {side.upper()}</b>: Score {res['metrics']['score']} (PnL: {res['metrics']['pnl']}$, Сделок: {res['metrics']['trades']})\n"
            else:
                msg += f"<b>{mode.upper()} {side.upper()}</b>: Нет сделок\n"
    
    send_telegram(msg)
    log.info("Done.")

if __name__ == "__main__":
    main()