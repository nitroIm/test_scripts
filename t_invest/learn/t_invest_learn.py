# PROD CONTOUR ONLY
# Python: 3.10
# Файл: learn/t_invest_learn.py

import os
import json
import joblib
import numpy as np
import pandas as pd
import requests
from datetime import datetime, timedelta, timezone
from t_tech.invest import Client
from t_tech.invest.constants import INVEST_GRPC_API
from t_tech.invest.schemas import CandleInterval
from t_tech.invest.utils import now

# === НАСТРОЙКИ ===
TOKEN = os.environ.get("T_INVEST_TOKEN")
TG_TOKEN = os.environ.get("INVEST_BOT_TOKEN")
TG_CHAT_ID = os.environ.get("INVEST_BOT_CHAT_ID")
WHITELIST_PATH = "t_invest/data/scanner/whitelist.json"
MODELS_DIR = "learn/models"
HISTORY_DAYS = 365  # 1 год истории
CHUNK_DAYS = 90     # 3 месяца (лимит API для H1)
TARGET_HORIZON = 1  # предсказываем цену через 1 час
TEST_SIZE = 0.2     # 20% последних данных для теста

# Калининградское время (UTC+2)
KLG_TZ = timezone(timedelta(hours=2))

def send_telegram(text):
    if not TG_TOKEN or not TG_CHAT_ID:
        print("Telegram secrets not set, skipping.")
        return
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    payload = {"chat_id": TG_CHAT_ID, "text": text, "parse_mode": "HTML"}
    try:
        requests.post(url, json=payload, timeout=10)
        print("Telegram message sent.")
    except Exception as e:
        print(f"Telegram error: {e}")

def fetch_candles(client, figi, days=HISTORY_DAYS):
    end = now()
    start = end - timedelta(days=days)
    all_candles = []
    current = start
    while current < end:
        chunk_end = min(current + timedelta(days=CHUNK_DAYS), end)
        try:
            resp = client.market_data.get_candles(
                figi=figi,
                from_=current,
                to=chunk_end,
                interval=CandleInterval.CANDLE_INTERVAL_HOUR,
            )
            all_candles.extend(resp.candles)
        except Exception as e:
            print(f"Chunk error {figi} {current.date()}: {e}")
        current = chunk_end
    if not all_candles:
        return None
    rows = []
    for c in all_candles:
        rows.append({
            "time": c.time,
            "open": c.open.units + c.open.nano / 1e9,
            "high": c.high.units + c.high.nano / 1e9,
            "low": c.low.units + c.low.nano / 1e9,
            "close": c.close.units + c.close.nano / 1e9,
            "volume": c.volume,
        })
    df = pd.DataFrame(rows)
    df["time"] = pd.to_datetime(df["time"], utc=True)
    df.set_index("time", inplace=True)
    return df

def add_features(df):
    # Базовые фичи
    df["sma_10"] = df["close"].rolling(10).mean()
    df["sma_50"] = df["close"].rolling(50).mean()
    df["rsi"] = compute_rsi(df["close"], 14)
    macd, signal = compute_macd(df["close"])
    df["macd"] = macd
    df["macd_signal"] = signal
    df["volume_sma"] = df["volume"].rolling(20).mean()
    df["volume_ratio"] = df["volume"] / df["volume_sma"]
    # Таргет: цена через TARGET_HORIZON часов выше текущей закрытия
    df["target"] = (df["close"].shift(-TARGET_HORIZON) > df["close"]).astype(int)
    df.dropna(inplace=True)
    return df

def compute_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def compute_macd(series, fast=12, slow=26, signal=9):
    exp1 = series.ewm(span=fast, adjust=False).mean()
    exp2 = series.ewm(span=slow, adjust=False).mean()
    macd = exp1 - exp2
    macd_signal = macd.ewm(span=signal, adjust=False).mean()
    return macd, macd_signal

def profit_factor(y_true, y_pred, returns):
    # Симуляция: если предсказано 1 (рост) -> зарабатываем returns, если 0 -> убыток returns
    pnl = np.where(y_pred == 1, returns, -returns)
    gross_profit = pnl[pnl > 0].sum()
    gross_loss = abs(pnl[pnl < 0].sum())
    if gross_loss == 0:
        return gross_profit if gross_profit > 0 else 0.0
    return gross_profit / gross_loss

def train_models(df):
    # Подготовка X, y
    feature_cols = ["open", "high", "low", "close", "volume",
                    "sma_10", "sma_50", "rsi", "macd", "macd_signal",
                    "volume_ratio"]
    X = df[feature_cols].values
    y = df["target"].values
    returns = df["close"].pct_change().shift(-TARGET_HORIZON).fillna(0).values

    split = int(len(df) * (1 - TEST_SIZE))
    X_train, X_test = X[:split], X[split:]
    y_train, y_test = y[:split], y[split:]
    ret_test = returns[split:]

    models = {}

    # 1. Custom model (простая логика на RSI + MACD + volume)
    class CustomModel:
        def fit(self, X, y):
            pass
        def predict(self, X):
            # используем индексы фичей: rsi=7, macd=8, macd_signal=9, volume_ratio=10
            rsi = X[:, 7]
            macd = X[:, 8]
            macd_sig = X[:, 9]
            vol_ratio = X[:, 10]
            pred = ((rsi < 30) & (macd > macd_sig) & (vol_ratio > 1.2)).astype(int)
            return pred
    models["custom"] = CustomModel()

    # 2. LogisticRegression
    from sklearn.linear_model import LogisticRegression
    models["logreg"] = LogisticRegression(max_iter=1000)

    # 3. RandomForest
    from sklearn.ensemble import RandomForestClassifier
    models["rf"] = RandomForestClassifier(n_estimators=100, random_state=42)

    # 4. XGBoost
    try:
        import xgboost as xgb
        models["xgb"] = xgb.XGBClassifier(use_label_encoder=False, eval_metric="logloss", random_state=42)
    except ImportError:
        print("XGBoost not installed, skipping.")

    # 5. LightGBM
    try:
        import lightgbm as lgb
        models["lgbm"] = lgb.LGBMClassifier(random_state=42, verbose=-1)
    except ImportError:
        print("LightGBM not installed, skipping.")

    # 6. CatBoost
    try:
        import catboost as cb
        models["catboost"] = cb.CatBoostClassifier(random_state=42, verbose=0)
    except ImportError:
        print("CatBoost not installed, skipping.")

    results = {}
    best_model = None
    best_pf = -1
    best_name = ""

    for name, model in models.items():
        try:
            model.fit(X_train, y_train)
            y_pred = model.predict(X_test)
            pf = profit_factor(y_test, y_pred, ret_test)
            results[name] = pf
            print(f"{name}: Profit Factor = {pf:.4f}")
            if pf > best_pf:
                best_pf = pf
                best_model = model
                best_name = name
        except Exception as e:
            print(f"Error training {name}: {e}")
            results[name] = None

    return best_model, best_name, best_pf, results

def main():
    if not TOKEN:
        print("No T_INVEST_TOKEN")
        return

    if not os.path.exists(WHITELIST_PATH):
        print("whitelist.json not found")
        return

    with open(WHITELIST_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict) and "data" in data:
        stocks = data["data"]
    else:
        stocks = data
    tickers = [s["ticker"] for s in stocks]
    print(f"Tickers to learn: {len(tickers)}")

    all_dfs = []
    with Client(TOKEN, target=INVEST_GRPC_API) as client:
        for ticker in tickers:
            # Нужен FIGI, но в whitelist он есть. Ищем.
            figi = None
            for s in stocks:
                if s["ticker"] == ticker:
                    figi = s["figi"]
                    break
            if not figi:
                continue
            print(f"Fetching {ticker}...")
            df = fetch_candles(client, figi)
            if df is not None and len(df) > 50:
                df["ticker"] = ticker
                all_dfs.append(df)

    if not all_dfs:
        send_telegram("⚠️ Обучение не удалось: нет данных.")
        return

    full_df = pd.concat(all_dfs)
    full_df = add_features(full_df)
    # Для простоты обучаем на всех данных сразу (можно и по тикерам отдельно)
    full_df.sort_index(inplace=True)
    # Убираем возможные дубликаты времени
    full_df = full_df[~full_df.index.duplicated(keep="first")]

    print(f"Total rows after features: {len(full_df)}")
    best_model, best_name, best_pf, results = train_models(full_df)

    if best_model is None:
        send_telegram("⚠️ Обучение не дало результатов.")
        return

    os.makedirs(MODELS_DIR, exist_ok=True)
    model_path = os.path.join(MODELS_DIR, "best_model.pkl")
    joblib.dump(best_model, model_path)
    print(f"Saved best model: {best_name} to {model_path}")

    # Сохраняем табло
    leaderboard = {
        "winner": best_name,
        "profit_factor": best_pf,
        "all_results": results,
        "trained_at": datetime.now(KLG_TZ).isoformat(),
        "tickers_count": len(tickers),
        "rows": len(full_df),
    }
    with open(os.path.join(MODELS_DIR, "leaderboard.json"), "w", encoding="utf-8") as f:
        json.dump(leaderboard, f, ensure_ascii=False, indent=2)

    # Одно сообщение в Telegram
    msg = (
        f"🏆 <b>Обучение завершено</b>\n\n"
        f"Победитель: <b>{best_name}</b>\n"
        f"Profit Factor: <b>{best_pf:.2f}</b>\n"
        f"Акций в обучении: {len(tickers)}\n"
        f"Строк данных: {len(full_df)}\n"
        f"Время (КЛГ): {datetime.now(KLG_TZ).strftime('%d.%m.%Y %H:%M')}"
    )
    send_telegram(msg)
    print("Done.")

if __name__ == "__main__":
    main()