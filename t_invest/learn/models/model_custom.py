import itertools
import numpy as np
import pandas as pd

INITIAL_BALANCE = 100.0
POSITION_NOTIONAL = 20.0
FEE_RATE = 0.0005
MIN_TRADES_FOR_FULL_SCORE = 30

# Урезанная сетка, чтобы не ждать по полчаса
GRID_CUSTOM = {
    "rsi_threshold": [25, 30, 35],
    "vol_multiplier": [1.0, 1.2],
    "tp_pct": [1.0, 2.0, 3.0],
    "sl_pct": [0.5, 1.0, 2.0],
    "time_exit_h": [4, 8, 12]
}

def run_backtest_single(df, side, params):
    trades, in_pos, entry_price, entry_idx = [], False, 0.0, 0
    for i in range(1, len(df)):
        curr = df.iloc[i]
        if in_pos:
            gross_pct = (curr['close'] - entry_price) / entry_price * 100.0 if side == "long" else (entry_price - curr['close']) / entry_price * 100.0
            if gross_pct <= -params["sl_pct"] or gross_pct >= params["tp_pct"] or (i - entry_idx) >= params["time_exit_h"]:
                trades.append(POSITION_NOTIONAL * ((gross_pct - (FEE_RATE * 200)) / 100.0))
                in_pos = False
        
        if not in_pos:
            macd_cond = curr['macd_hist'] > 0 if side == "long" else curr['macd_hist'] < 0
            vol_cond = curr['volume'] > (curr['vol_sma'] * params["vol_multiplier"])
            
            if side == "long":
                rsi_cond = curr['rsi'] < params["rsi_threshold"]
            else:
                rsi_cond = curr['rsi'] > (100 - params["rsi_threshold"])
                
            if rsi_cond and macd_cond and vol_cond:
                in_pos, entry_price, entry_idx = True, curr['close'], i
    return trades

def calculate_metrics(trades):
    n = len(trades)
    if n == 0: return None
    pnls = np.array(trades)
    total_pnl = float(pnls.sum())
    cum = np.cumsum(pnls) + INITIAL_BALANCE
    peak = np.maximum.accumulate(cum)
    dd = (cum - peak) / peak * 100.0
    max_dd = float(dd.min()) if len(dd) else -0.1
    if max_dd == 0: max_dd = -0.1
    raw_score = total_pnl / abs(max_dd)
    return {"trades": n, "pnl": round(total_pnl, 2), "winrate": round(float((pnls > 0).mean()), 4),
            "max_dd": round(max_dd, 2), "score": round(raw_score * min(1.0, n / MIN_TRADES_FOR_FULL_SCORE), 2), "raw_score": round(raw_score, 2)}

def train(df, side="long", mode="swing"):
    df = df.sort_values(['ticker', 'open_time']).reset_index(drop=True)
    
    # 80% Train, 20% Test (Строго по времени, без перемешивания!)
    split = int(len(df) * 0.8)
    train_df = df.iloc[:split]
    test_df = df.iloc[split:]
    
    keys, values = zip(*GRID_CUSTOM.items())
    combos = [dict(zip(keys, v)) for v in itertools.product(*values)]
    
    best_train_score = -99999
    best_params = None
    
    # 1. Ищем лучшие параметры ТОЛЬКО на Train части
    for params in combos:
        all_trades = []
        for _, t_df in train_df.groupby('ticker'):
            all_trades.extend(run_backtest_single(t_df.reset_index(drop=True), side, params))
        m = calculate_metrics(all_trades)
        if m and m["score"] > best_train_score:
            best_train_score = m["score"]
            best_params = params
            
    if not best_params: return None
    
    # 2. Проверяем эти параметры на Test части (которую модель не видела)
    test_trades = []
    for _, t_df in test_df.groupby('ticker'):
        test_trades.extend(run_backtest_single(t_df.reset_index(drop=True), side, best_params))
    test_metrics = calculate_metrics(test_trades)
    
    if not test_metrics: return None
    
    return {"params": {**best_params, "model_type": "custom"}, "metrics": test_metrics}