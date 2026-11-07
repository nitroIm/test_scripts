import os
import joblib
import itertools
import numpy as np
import pandas as pd
import lightgbm as lgb

INITIAL_BALANCE = 100.0
POSITION_NOTIONAL = 20.0
FEE_RATE = 0.0005
MIN_TRADES_FOR_FULL_SCORE = 30

FEATURE_COLS = ["open", "high", "low", "close", "volume", "rsi", "rsi_7", "rsi_21", "macd_hist",
                "ema_20", "ema_50", "ema_200", "vol_sma", "atr_7", "atr_14", "atr_50", "atr_100",
                "price_change_1h", "price_change_4h", "price_change_24h"]

GRID_EXIT = {"tp_pct": [1.0, 2.0, 3.0], "sl_pct": [0.5, 1.0, 2.0], "time_exit_h": [4, 8, 12, 24]}

def run_backtest_single(df, predictions, side, tp_pct, sl_pct, time_exit_h):
    trades, in_pos, entry_price, entry_idx = [], False, 0.0, 0
    for i in range(1, len(df)):
        curr = df.iloc[i]
        if in_pos:
            gross_pct = (curr['close'] - entry_price) / entry_price * 100.0 if side == "long" else (entry_price - curr['close']) / entry_price * 100.0
            if gross_pct <= -sl_pct or gross_pct >= tp_pct or (i - entry_idx) >= time_exit_h:
                trades.append(POSITION_NOTIONAL * ((gross_pct - (FEE_RATE * 200)) / 100.0))
                in_pos = False
        if not in_pos and predictions[i] == 1:
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
    df['target'] = (df.groupby('ticker')['close'].shift(-1) > df['close']).astype(int) if side == "long" else (df.groupby('ticker')['close'].shift(-1) < df['close']).astype(int)
    df = df.dropna(subset=FEATURE_COLS + ['target']).reset_index(drop=True)
    
    split = int(len(df) * 0.8)
    X_train, y_train = df.iloc[:split][FEATURE_COLS].values, df.iloc[:split]['target'].values
    test_df = df.iloc[split:].reset_index(drop=True)
    
    model = lgb.LGBMClassifier(n_estimators=100, num_leaves=31, random_state=42, verbose=-1)
    model.fit(X_train, y_train)
    test_df['pred'] = model.predict(test_df[FEATURE_COLS].values)
    
    keys, values = zip(*GRID_EXIT.items())
    combos = [dict(zip(keys, v)) for v in itertools.product(*values)]
    
    best_metrics, best_params = None, None
    for params in combos:
        all_trades = []
        for _, t_df in test_df.groupby('ticker'):
            all_trades.extend(run_backtest_single(t_df.reset_index(drop=True), t_df['pred'].values, side, params["tp_pct"], params["sl_pct"], params["time_exit_h"]))
        m = calculate_metrics(all_trades)
        if m and (best_metrics is None or m["score"] > best_metrics["score"]):
            best_metrics, best_params = m, params
            
    if not best_params: return None
    
    model_path = f"t_invest/data/model/model_lgbm_{mode}_{side}.pkl"
    os.makedirs(os.path.dirname(model_path), exist_ok=True)
    joblib.dump(model, model_path)
    return {"params": {**best_params, "model_type": "lgbm"}, "metrics": best_metrics, "model_path": model_path}