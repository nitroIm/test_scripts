# ============================================================
# T-INVEST - SIMULATOR (ONLINE LEARNING UPDATE)
# Path: t_invest/simulator/t_invest_simulator.py
# ============================================================

import os, sys, json, logging, joblib, requests, pickle
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timezone, timedelta
from t_tech.invest import Client
from t_tech.invest.constants import INVEST_GRPC_API_SANDBOX
from t_tech.invest.schemas import CandleInterval, OrderDirection, OrderType, MoneyValue
from t_tech.invest.utils import now

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("simulator")

# ... (настройки, FEATURE_COLS, DEFAULT_CONFIG, load_config, send_tg, q2f, calc_... остаются без изменений)

def main():
    # ... (начало main без изменений)
    config = load_config()

    # ... (загрузка данных, state, history, news_scores)

    models = {}
    # Загружаем ML-модели (joblib) и онлайн-модель (pickle)
    for mode in ["intraday", "swing"]:
        for side in ["long", "short"]:
            cfg = params_data.get(mode, {}).get(side)
            if cfg and cfg.get("model_path"):
                p = Path(cfg["model_path"])
                if p.exists():
                    if "custom_online" in cfg.get("source", ""):
                        with open(p, "rb") as f:
                            models[f"{mode}_{side}"] = pickle.load(f)
                    else:
                        models[f"{mode}_{side}"] = joblib.load(p)

    with Client(TOKEN, target=INVEST_GRPC_API_SANDBOX) as client:
        # ... (аккаунт, баланс)

        for ticker in tickers:
            # ... (получение свечей, last_candle, lot)

            for mode in ["intraday", "swing"]:
                for side in ["long", "short"]:
                    pos_key = f"{ticker}_{mode}_{side}"
                    mode_config = config.get(mode, DEFAULT_CONFIG[mode])

                    # === ВЫХОД ===
                    if pos_key in state["positions"]:
                        pos = state["positions"][pos_key]
                        # ... (логика выхода для long и short)

                        if exit_reason:
                            try:
                                # ... (закрытие ордера, расчет pnl)

                                result_str = "WIN" if pnl_pct > 0 else "LOSS"

                                # === ОБНОВЛЕНИЕ ОНЛАЙН-МОДЕЛИ ===
                                model_key = f"{mode}_{side}"
                                if model_key in models and "custom_online" in params_data.get(mode, {}).get(side, {}).get("source", ""):
                                    try:
                                        model = models[model_key]
                                        # Признаки на момент входа (сохранены в pos)
                                        x = pos.get("entry_features")
                                        if x:
                                            y = 1 if result_str == "WIN" else 0
                                            model.learn_one(x, y)
                                            # Сохраняем обновленную модель
                                            model_path = params_data[mode][side]["model_path"]
                                            with open(model_path, "wb") as f:
                                                pickle.dump(model, f)
                                            log.info(f"Online model updated for {model_key} with y={y}")
                                    except Exception as e:
                                        log.error(f"Online model update error: {e}")

                                # ... (отправка сообщения, удаление позиции)

                            except Exception as e:
                                log.error(f"Sell error {pos_key}: {e}")

                    # === ВХОД ===
                    if pos_key not in state["positions"]:
                        # ... (проверка лимитов, заморозки)

                        model = models.get(f"{mode}_{side}")
                        signal = 0
                        prob = 0.0

                        if model is not None:
                            try:
                                X = last_candle[FEATURE_COLS].values.reshape(1, -1)
                                if hasattr(model, "predict_proba"):
                                    prob = model.predict_proba(X)[0][1]
                                    signal = 1 if prob >= mode_config["min_prob"] else 0
                                elif hasattr(model, "predict_proba_one"):
                                    x_dict = last_candle[FEATURE_COLS].to_dict()
                                    prob = model.predict_proba_one(x_dict).get(1, 0.0)
                                    signal = 1 if prob >= mode_config["min_prob"] else 0
                                else:
                                    signal = int(model.predict(X)[0])
                                    prob = 1.0 if signal == 1 else 0.0
                            except Exception as e:
                                log.error(f"Pred error {pos_key}: {e}")

                        # ... (проверка новостей)

                        if signal == 1:
                            # ... (проверка стоимости, открытие позиции)

                            # СОХРАНЯЕМ ПРИЗНАКИ ДЛЯ ОНЛАЙН-ОБНОВЛЕНИЯ
                            entry_features = last_candle[FEATURE_COLS].to_dict()

                            state["positions"][pos_key] = {
                                "side": side,
                                "entry": entry_price,
                                "qty": 1,
                                "entry_time": now_time.isoformat(),
                                "entry_prob": prob,
                                "entry_features": entry_features,  # <-- сохраняем признаки
                                "tp": tp_price,
                                "sl": sl_price,
                                "trailing_stop": sl_price,
                                "highest": entry_price,
                                "exit_time": exit_time.isoformat(),
                                "figi": figi
                            }

                            # ... (отправка сообщения о покупке/продаже)

    # ... (сохранение state, history)