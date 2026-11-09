# ============================================================
# T-INVEST - SIMULATOR (SANDBOX) WITH TRAILING STOP
# Path: t_invest/simulator/t_invest_simulator.py
# ============================================================

import os, json, logging, joblib, requests
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timezone, timedelta
from t_tech.invest import Client
from t_tech.invest.constants import INVEST_GRPC_API_SANDBOX
from t_tech.invest.schemas import CandleInterval, OrderDirection, OrderType
from t_tech.invest.utils import now

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("simulator")

# --- НАСТРОЙКИ ---
TOKEN = os.environ.get("T_INVEST_TOKEN") # Используем прод-токен для Sandbox
TG_TOKEN = os.environ.get("INVEST_BOT_TOKEN")
TG_CHAT_ID = os.environ.get("INVEST_BOT_CHAT_ID")

BEST_PARAMS_FILE = Path("t_invest/data/model/best_params.json")
STATE_FILE = Path("t_invest/data/simulator/state.json")

FEATURE_COLS = ["open", "high", "low", "close", "volume", "rsi", "rsi_7", "rsi_21", "macd_hist", "ema_20", "ema_50", "ema_200", "vol_sma", "atr_7", "atr_14", "atr_50", "atr_100", "price_change_1h", "price_change_4h", "price_change_24h"]

KLG_TZ = timezone(timedelta(hours=2))

def send_tg(text):
    if not TG_TOKEN or not TG_CHAT_ID: return
    try:
        requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", json={"chat_id": TG_CHAT_ID, "text": text, "parse_mode": "HTML"}, timeout=10)
    except: pass

def q2f(q): return q.units + q.nano / 1e9

# --- ИНДИКАТОРЫ (копия из learn) ---
def calc_ema(s, p): return s.ewm(span=p, adjust=False).mean()
def calc_rsi(s, p=14):
    d = s.diff(); g = (d.where(d>0,0)).rolling(window=p).mean(); l = (-d.where(d<0,0)).rolling(window=p).mean()
    return 100 - (100 / (1 + g/l))
def calc_macd(s, f=12, sl=26, sig=9):
    m = calc_ema(s, f) - calc_ema(s, sl); return m - calc_ema(m, sig)
def calc_atr(df, p=14):
    tr = pd.concat([df['high']-df['low'], (df['high']-df['close'].shift()).abs(), (df['low']-df['close'].shift()).abs()], axis=1).max(axis=1)
    return tr.rolling(window=p).mean()

def compute_features(df):
    df['rsi'] = calc_rsi(df['close'], 14); df['rsi_7'] = calc_rsi(df['close'], 7); df['rsi_21'] = calc_rsi(df['close'], 21)
    df['macd_hist'] = calc_macd(df['close']); df['ema_50'] = calc_ema(df['close'], 50); df['ema_20'] = calc_ema(df['close'], 20); df['ema_200'] = calc_ema(df['close'], 200)
    df['vol_sma'] = df['volume'].rolling(window=20).mean()
    df['atr_7'] = calc_atr(df, 7); df['atr_14'] = calc_atr(df, 14); df['atr_50'] = calc_atr(df, 50); df['atr_100'] = calc_atr(df, 100)
    df['price_change_1h'] = df['close'].pct_change(1); df['price_change_4h'] = df['close'].pct_change(4); df['price_change_24h'] = df['close'].pct_change(24)
    return df

def fetch_last_candles(client, figi, count=50):
    try:
        resp = client.market_data.get_candles(figi=figi, from_=now()-timedelta(hours=count*2), to=now(), interval=CandleInterval.CANDLE_INTERVAL_HOUR)
        rows = [{"time": c.time, "open": q2f(c.open), "high": q2f(c.high), "low": q2f(c.low), "close": q2f(c.close), "volume": c.volume} for c in resp.candles]
        df = pd.DataFrame(rows)
        df['time'] = pd.to_datetime(df['time'], utc=True)
        return df
    except: return pd.DataFrame()

def main():
    log.info("STARTING SIMULATOR")
    if not BEST_PARAMS_FILE.exists():
        log.error("best_params.json not found"); return

    with open(BEST_PARAMS_FILE) as f: params_data = json.load(f)
    
    # Пока используем только INTRADAY LONG (для теста)
    mode = "intraday"
    side = "long"
    cfg = params_data.get(mode, {}).get(side)
    if not cfg:
        log.error(f"No params for {mode}/{side}"); return
    
    p = cfg["params"]
    model_path = cfg.get("model_path")
    tickers = params_data["long_tickers"]
    
    # Загрузка состояния
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    state = {"positions": {}}
    if STATE_FILE.exists():
        with open(STATE_FILE) as f: state = json.load(f)
    
    actions = []
    now_time = datetime.now(timezone.utc)
    current_klg = now_time.astimezone(KLG_TZ).strftime("%H:%M")

    with Client(TOKEN, target=INVEST_GRPC_API_SANDBOX) as client:
        accounts = client.users.get_accounts()
        if not accounts.accounts:
            log.error("No sandbox accounts"); return
        acc_id = accounts.accounts[0].id

        for ticker in tickers:
            # Получаем FIGI (из whitelist, но для простоты ищем через instruments)
            try:
                shares = client.instruments.shares(instrument_status=1).instruments
                share = next((s for s in shares if s.ticker == ticker), None)
                if not share: continue
                figi = share.figi
            except Exception as e:
                log.error(f"Error finding {ticker}: {e}"); continue

            df = fetch_last_candles(client, figi)
            if len(df) < 30: continue
            df = compute_features(df).dropna()
            if df.empty: continue
            
            last_candle = df.iloc[-1]
            current_price = last_candle['close']

            # === ЛОГИКА ВХОДА ===
            if ticker not in state["positions"]:
                signal = 0
                if cfg["source"] == "model_custom":
                    if last_candle['rsi'] < 30 and last_candle['macd_hist'] > 0:
                        signal = 1
                elif model_path and Path(model_path).exists():
                    try:
                        model = joblib.load(model_path)
                        X = last_candle[FEATURE_COLS].values.reshape(1, -1)
                        signal = int(model.predict(X)[0])
                    except Exception as e:
                        log.error(f"Pred error {ticker}: {e}")
                
                if signal == 1:
                    # Покупаем
                    try:
                        req = client.sandbox.post_sandbox_order(
                            figi=figi, quantity=1, direction=OrderDirection.ORDER_DIRECTION_BUY,
                            account_id=acc_id, order_type=OrderType.ORDER_TYPE_MARKET
                        )
                        # Ждем исполнения (упрощенно)
                        entry_price = current_price
                        tp_price = entry_price * (1 + p["tp_pct"] / 100)
                        sl_price = entry_price * (1 - p["sl_pct"] / 100)
                        exit_time = now_time + timedelta(hours=p["time_exit_h"])
                        
                        state["positions"][ticker] = {
                            "side": side, "entry": entry_price, "qty": 1,
                            "tp": tp_price, "sl": sl_price,
                            "trailing_stop": sl_price, "highest": entry_price,
                            "exit_time": exit_time.isoformat(), "figi": figi
                        }
                        msg = f"🟢 <b>ПОКУПКА {ticker}</b>\nЦена: {entry_price:.2f}₽\nTP: {tp_price:.2f}₽ | SL: {sl_price:.2f}₽\nВремя: {current_klg} КЛГ"
                        actions.append(msg)
                        send_tg(msg)
                    except Exception as e:
                        log.error(f"Buy error {ticker}: {e}")

            # === ЛОГИКА ВЫХОДА И ТРЕЙЛИНГА ===
            else:
                pos = state["positions"][ticker]
                trail_dist_pct = p["sl_pct"] * 0.5  # 50% от изначального SL
                
                # Обновляем highest по свече
                if last_candle['high'] > pos["highest"]:
                    pos["highest"] = last_candle['high']
                
                new_trail = pos["highest"] * (1 - trail_dist_pct / 100)
                if new_trail > pos["trailing_stop"]:
                    pos["trailing_stop"] = new_trail
                    log.info(f"{ticker} trailing stop moved to {new_trail:.2f}")

                exit_reason = None
                # Проверка по закрытию свечи
                if last_candle['close'] <= pos["trailing_stop"]:
                    exit_reason = "TRAILING_STOP"
                elif last_candle['close'] >= pos["tp"]:
                    exit_reason = "TAKE_PROFIT"
                elif now_time >= datetime.fromisoformat(pos["exit_time"]):
                    exit_reason = "TIME_EXIT"

                if exit_reason:
                    try:
                        client.sandbox.post_sandbox_order(
                            figi=figi, quantity=pos["qty"], direction=OrderDirection.ORDER_DIRECTION_SELL,
                            account_id=acc_id, order_type=OrderType.ORDER_TYPE_MARKET
                        )
                        pnl_pct = (current_price - pos["entry"]) / pos["entry"] * 100
                        msg = f"🔴 <b>ПРОДАЖА {ticker}</b>\nПричина: {exit_reason}\nЦена: {current_price:.2f}₽ | PnL: {pnl_pct:.2f}%\nВремя: {current_klg} КЛГ"
                        actions.append(msg)
                        send_tg(msg)
                        del state["positions"][ticker]
                    except Exception as e:
                        log.error(f"Sell error {ticker}: {e}")

    # Сохраняем состояние
    with open(STATE_FILE, "w") as f: json.dump(state, f, indent=2, default=str)
    log.info(f"Simulator done. Actions: {len(actions)}")

if __name__ == "__main__":
    main()