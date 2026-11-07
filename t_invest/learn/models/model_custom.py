# ============================================================
# T-INVEST - CUSTOM MODEL (GRID SEARCH)
# Path: t_invest/learn/models/model_custom.py
# ============================================================

import logging
import itertools
import numpy as np

log = logging.getLogger("model_custom")

INITIAL_BALANCE = 100.0
POSITION_NOTIONAL = 20.0
FEE_RATE = 0.0005 # 0.05% комиссия Т-Инвест
MIN_TRADES_FOR_FULL_SCORE = 30

# Сетка параметров для твоей логики (RSI + MACD + Volume)
GRID_CUSTOM = {
    "rsi_threshold": [25, 30, 35],       # Порог перепроданности / перекупленности
    "vol_multiplier": [1.0, 1.2, 1.5],   # Во сколько раз объем должен быть выше среднего
    "tp_pct": [1.0, 2.0, 3.0, 5.0],      # Тейк-профит в %
    "sl_pct": [0.5, 1.0, 2.0, 3.0],      # Стоп-лосс в %
    "time_exit_h": [4, 8, 12, 24, 48]    # Выход по времени (в часах)
}

def run_backtest(df, params, side="long"):
    trades = []
    in_pos = False
    entry_price = 0.0
    entry_idx = 0

    for i, curr in enumerate(df.itertuples()):
        if i == 0: continue
        
        # ЛОГИКА ВЫХОДА
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
        
        # ЛОГИКА ВХОДА (ТВОЯ КАСТОМНАЯ)
        if not in_pos:
            # MACD > 0 означает, что MACD выше сигнальной линии
            macd_condition = curr.macd_hist > 0 if side == "long" else curr.macd_hist < 0
            vol_condition = curr.volume > (curr.vol_sma * params["vol_multiplier"])
            
            if side == "long":
                # RSI перепродан
                rsi_condition = curr.rsi < params["rsi_threshold"]
                signal = rsi_condition and macd_condition and vol_condition
            else:
                # RSI перекуплен (для шорта)
                rsi_condition = curr.rsi > (100 - params["rsi_threshold"])
                signal = rsi_condition and macd_condition and vol_condition
                
            if signal:
                in_pos = True
                entry_price = curr.close
                entry_idx = i

    # РАСЧЕТ МЕТРИК (КАК В ARGUS)
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
    
    return {
        "trades": n, "pnl": round(total_pnl, 2),
        "winrate": round(float((pnls > 0).mean()), 4),
        "max_dd": round(max_dd, 2), 
        "score": round(adjusted_score, 2),
        "raw_score": round(raw_score, 2)
    }

def train(df, side="long", mode="swing"):
    # Выбираем сетку. Можно сделать отдельные для intraday/swing, 
    # но пока используем одну общую для кастомной модели.
    grid = GRID_CUSTOM
    
    keys, values = zip(*grid.items())
    combinations = [dict(zip(keys, v)) for v in itertools.product(*values)]
    
    best_result = None
    best_params = None

    for params in combinations:
        res = run_backtest(df, params, side=side)
        if res and (best_result is None or res["score"] > best_result["score"]):
            best_result = res
            best_params = params

    if not best_params:
        return None

    return {"params": best_params, "metrics": best_result}