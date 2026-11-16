# ============================================================
# T-INVEST - CUSTOM ONLINE MODEL (RIVER)
# Path: t_invest/learn/models/model_custom.py
# ============================================================

import pandas as pd
import numpy as np
import pickle
import os
from river import linear_model, preprocessing, metrics

FEATURE_COLS = [
    "open", "high", "low", "close", "volume", "rsi", "rsi_7", "rsi_21",
    "macd_hist", "ema_20", "ema_50", "ema_200", "vol_sma",
    "atr_7", "atr_14", "atr_50", "atr_100",
    "price_change_1h", "price_change_4h", "price_change_24h"
]

def train(df, side="long", mode="intraday"):
    if df.empty or len(df) < 100:
        return None

    # Создаем таргет: для long -> цена выросла, для short -> цена упала
    df = df.copy()
    future_close = df['close'].shift(-1)
    if side == "long":
        df['target'] = (future_close > df['close']).astype(int)
    else:
        df['target'] = (future_close < df['close']).astype(int)

    df = df.dropna(subset=['target'])

    # Инициализируем онлайн-модель
    model = preprocessing.StandardScaler() | linear_model.LogisticRegression()

    # Обучаем на исторических данных (онлайн, по одному наблюдению)
    for _, row in df.iterrows():
        x = row[FEATURE_COLS].to_dict()
        y = row['target']
        model.learn_one(x, y)

    # Оцениваем на последних 20% данных (для отчета)
    test_size = int(len(df) * 0.2)
    test_df = df.iloc[-test_size:]
    y_true = []
    y_pred = []
    for _, row in test_df.iterrows():
        x = row[FEATURE_COLS].to_dict()
        prob = model.predict_proba_one(x).get(1, 0.0)
        y_true.append(row['target'])
        y_pred.append(1 if prob >= 0.5 else 0)

    accuracy = metrics.Accuracy().update(y_true, y_pred).get()
    score = accuracy * 100  # простой скор

    # Сохраняем модель
    model_path = f"t_invest/data/model/custom_{side}_{mode}.pkl"
    os.makedirs(os.path.dirname(model_path), exist_ok=True)
    with open(model_path, "wb") as f:
        pickle.dump(model, f)

    return {
        "source": "model_custom_online",
        "metrics": {"score": round(score, 4)},
        "model_path": model_path,
        "params": {}
    }