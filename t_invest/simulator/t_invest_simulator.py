# ============================================================
# T-INVEST - SIMULATOR (SANDBOX) WITH STATS IN TG
# Path: t_invest/simulator/t_invest_simulator.py
# ============================================================

import os, sys, json, logging, joblib, requests
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

# --- НАСТРОЙКИ ---
TOKEN = os.environ.get("T_INVEST_TOKEN")
TG_TOKEN = os.environ.get("INVEST_BOT_TOKEN")
TG_CHAT_ID = os.environ.get("INVEST_BOT_CHAT_ID")

BEST_PARAMS_FILE = Path("t_invest/data/model/best_params.json")
WHITELIST_FILE = Path("t_invest/data/scanner/whitelist.json")
STATE_FILE = Path("t_invest/data/simulator/state.json")
HISTORY_FILE = Path("t_invest/data/simulator/trade_history.json")
NEWS_SCORES_FILE = Path("t_invest/data/news/t_invest_news_scores.json")

FEATURE_COLS = ["open", "high", "low", "close", "volume", "rsi", "rsi_7", "rsi_21", "macd_hist", "ema_20", "ema_50", "ema_200", "vol_sma", "atr_7", "atr_14", "atr_50", "atr_100", "price_change_1h", "price_change_4h", "price_change_24h"]

# ПОДНЯЛИ ПОРОГ ДО 0.45
MIN_PROBABILITY = 0.45
NEWS_BLOCK_THRESHOLD = -0.5 
KLG_TZ = timezone(timedelta(hours=2))

def send_tg(text):
    if not TG_TOKEN or not TG_CHAT_ID: return
    try:
        requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", json={"chat_id": TG_CHAT_ID, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}, timeout=10)
    except: pass

def q2f(q): return q.units + q.nano / 1e9

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

def fetch_h1_candles(client, figi, count=720):
    try:
        resp = client.market_data.get_candles(figi=figi, from_=now()-timedelta(hours=count), to=now(), interval=CandleInterval.CANDLE_INTERVAL_HOUR)
        rows = [{"time": c.time, "open": q2f(c.open), "high": q2f(c.high), "low": q2f(c.low), "close": q2f(c.close), "volume": c.volume} for c in resp.candles]
        df = pd.DataFrame(rows)
        df['time'] = pd.to_datetime(df['time'], utc=True)
        return df
    except Exception as e:
        log.error(f"Error fetching H1 {figi}: {e}")
        return pd.DataFrame()

def get_last_price(client, figi):
    try:
        resp = client.market_data.get_last_prices(figi=[figi])
        if resp.last_prices: return q2f(resp.last_prices[0].price)
    except Exception as e:
        log.error(f"Error fetching last price {figi}: {e}")
    return 0.0

def load_news_scores():
    if not NEWS_SCORES_FILE.exists(): return {}
    try:
        with open(NEWS_SCORES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e: return {}

def get_stats_text(ticker, history, now_time):
    today_str = now_time.strftime("%Y-%m-%d")
    today_wins = 0
    today_losses = 0
    ticker_wins = 0
    ticker_losses = 0
    first_trade_dt = None

    for record in history:
        if record.get("type") == "BUY" and "entry_time" in record:
            try:
                dt = datetime.fromisoformat(record["entry_time"])
                if first_trade_dt is None or dt < first_trade_dt:
                    first_trade_dt = dt
            except: pass

        if record.get("type") == "SELL":
            res = record.get("result")
            t = record.get("ticker")
            exit_time_str = record.get("exit_time", "")

            if t == ticker:
                if res == "WIN": ticker_wins += 1
                elif res == "LOSS": ticker_losses += 1

            if exit_time_str.startswith(today_str):
                if res == "WIN": today_wins += 1
                elif res == "LOSS": today_losses += 1

    total_today = today_wins + today_losses
    winrate = (today_wins / total_today * 100) if total_today > 0 else 0.0
    total_ticker = ticker_wins + ticker_losses

    first_trade_str = "Неизвестно"
    if first_trade_dt:
        days_active = (now_time - first_trade_dt).days + 1
        first_trade_str = f"{first_trade_dt.astimezone(KLG_TZ).strftime('%d.%m.%Y')} ({days_active} дн.)"

    text = (
        f"\n\n📊 <b>Статистика за сегодня ({today_str}):</b>\n"
        f"Всего: {total_today} (WIN: {today_wins}, LOSS: {today_losses})\n"
        f"Винрейт: {winrate:.1f}%\n\n"
        f"🎯 <b>По тикеру {ticker}:</b>\n"
        f"Всего: {total_ticker} (WIN: {ticker_wins}, LOSS: {ticker_losses})\n\n"
        f"📅 <b>Симулятор в работе с:</b> {first_trade_str}"
    )
    return text

def main():
    log.info("STARTING SIMULATOR (WITH STATS)")
    if not BEST_PARAMS_FILE.exists() or not WHITELIST_FILE.exists():
        log.error("best_params.json or whitelist.json not found"); return

    with open(BEST_PARAMS_FILE) as f: params_data = json.load(f)
    with open(WHITELIST_FILE) as f: wl_data = json.load(f)
    
    wl_stocks = wl_data["data"] if isinstance(wl_data, dict) and "data" in wl_data else wl_data
    figi_map = {s["ticker"]: s["figi"] for s in wl_stocks}
    
    cfg_intraday = params_data.get("intraday", {}).get("long")
    cfg_swing = params_data.get("swing", {}).get("long")

    if not cfg_intraday and not cfg_swing:
        log.error("No params for intraday or swing"); return
    
    tickers = set(params_data.get("long_tickers", []))
    if cfg_intraday: tickers.update(params_data.get("long_tickers", []))
    
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    state = {"positions": {}, "last_h1_candle": {}, "deposit_v3": False, "alert_sent_v3": False}
    
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE) as f: loaded_state = json.load(f)
            if isinstance(loaded_state, dict):
                for k, v in loaded_state.items(): state[k] = v
        except: pass
        
    if "positions" not in state: state["positions"] = {}
    if "last_h1_candle" not in state: state["last_h1_candle"] = {}
        
    history = []
    if HISTORY_FILE.exists():
        try:
            with open(HISTORY_FILE) as f: history = json.load(f)
        except: pass
    
    news_scores = load_news_scores()
    now_time = datetime.now(timezone.utc)
    current_klg = now_time.astimezone(KLG_TZ).strftime("%d.%m.%Y %H:%M")

    models = {}
    if cfg_intraday and cfg_intraday.get("model_path"):
        p = cfg_intraday["model_path"]
        if Path(p).exists(): models["intraday"] = joblib.load(p)
    if cfg_swing and cfg_swing.get("model_path"):
        p = cfg_swing["model_path"]
        if Path(p).exists(): models["swing"] = joblib.load(p)

    with Client(TOKEN, target=INVEST_GRPC_API_SANDBOX) as client:
        accounts = client.users.get_accounts()
        if not accounts.accounts: 
            try:
                new_acc = client.sandbox.open_sandbox_account()
                acc_id = new_acc.account_id
                log.info(f"Created sandbox account: {acc_id}")
            except Exception as e:
                log.error(f"Failed to create sandbox account: {e}")
                return
        else:
            acc_id = accounts.accounts[0].id

        rub_balance = 0.0
        try:
            positions = client.operations.get_positions(account_id=acc_id)
            for m in positions.money:
                if m.currency == "rub":
                    rub_balance = q2f(m)
                    break

            if not state.get("deposit_v3", False):
                if rub_balance < 10:
                    client.sandbox.sandbox_pay_in(
                        account_id=acc_id,
                        amount=MoneyValue(currency="rub", units=10000, nano=0)
                    )
                    log.info(f"Первый запуск. Баланс пополнен на 10 000 ₽.")
                    rub_balance = 10000.0
                state["deposit_v3"] = True
                state["alert_sent_v3"] = False
            else:
                log.info(f"Текущий баланс: {rub_balance:.2f} ₽. Пополнение отключено.")
                
            if rub_balance > 1000:
                state["alert_sent_v3"] = False
                
        except Exception as e:
            log.warning(f"Не удалось проверить/пополнить баланс: {e}")

        for ticker in tickers:
            figi = figi_map.get(ticker)
            if not figi: continue

            current_price = get_last_price(client, figi)
            if current_price <= 0: continue

            df_h1 = fetch_h1_candles(client, figi)
            if len(df_h1) < 200: continue
                
            last_candle_time = df_h1.iloc[-1]['time'].isoformat()
            df_h1 = compute_features(df_h1).dropna()
            if df_h1.empty: continue
                
            last_candle = df_h1.iloc[-1]
            lot = next((s['lot'] for s in wl_stocks if s['ticker'] == ticker), 1)

            for mode, cfg in [("intraday", cfg_intraday), ("swing", cfg_swing)]:
                if not cfg: continue
                pos_key = f"{ticker}_{mode}"

                # === ВЫХОД ===
                if pos_key in state["positions"]:
                    pos = state["positions"][pos_key]
                    if current_price > pos["highest"]: pos["highest"] = current_price
                    
                    # РАСШИРИЛИ ТРЕЙЛИНГ-СТОП (было 0.5, стало 0.8)
                    trail_dist_pct = cfg["params"]["sl_pct"] * 0.8
                    new_trail = pos["highest"] * (1 - trail_dist_pct / 100)
                    if new_trail > pos["trailing_stop"]:
                        pos["trailing_stop"] = new_trail

                    exit_reason = None
                    if current_price <= pos["trailing_stop"]: exit_reason = "TRAILING_STOP"
                    elif current_price >= pos["tp"]: exit_reason = "TAKE_PROFIT"
                    elif now_time >= datetime.fromisoformat(pos["exit_time"]): exit_reason = "TIME_EXIT"

                    if exit_reason:
                        try:
                            client.sandbox.post_sandbox_order(figi=figi, quantity=pos["qty"], direction=OrderDirection.ORDER_DIRECTION_SELL, account_id=acc_id, order_type=OrderType.ORDER_TYPE_MARKET)
                            
                            entry_time_str = pos.get("entry_time", now_time.isoformat())
                            entry_time = datetime.fromisoformat(entry_time_str)
                            duration_hours = round((now_time - entry_time).total_seconds() / 3600, 2)
                            
                            pnl_pct = (current_price - pos["entry"]) / pos["entry"] * 100
                            pnl_rub = (current_price - pos["entry"]) * pos["qty"] * lot
                            rub_balance += (current_price * pos["qty"] * lot)
                            
                            result_str = "WIN" if pnl_pct > 0 else "LOSS"
                            if result_str == "WIN":
                                emoji = "✅"
                                title = "СДЕЛКА ЗАКРЫТА В ПЛЮС"
                            else:
                                emoji = "❌"
                                title = "СДЕЛКА ЗАКРЫТА В МИНУС"
                            
                            trade_record = {
                                "ticker": ticker,
                                "mode": mode,
                                "type": "SELL",
                                "result": result_str,
                                "entry_time": entry_time_str,
                                "entry_price": round(pos["entry"], 2),
                                "entry_prob": pos.get("entry_prob", 0.0),
                                "exit_time": now_time.isoformat(),
                                "exit_price": round(current_price, 2),
                                "reason": exit_reason,
                                "duration_hours": duration_hours,
                                "pnl_pct": round(pnl_pct, 2),
                                "pnl_rub": round(pnl_rub, 2),
                                "balance_after": round(rub_balance, 2)
                            }
                            
                            log.info(f"AUDIT_TRADE: {json.dumps(trade_record)}")
                            history.append(trade_record)
                            
                            stats_text = get_stats_text(ticker, history, now_time)

                            msg_text = (
                                f"{emoji} <b>{title} {ticker} ({mode.upper()})</b>\n"
                                f"Причина: {exit_reason}\n"
                                f"Вход: {pos['entry']:.2f}₽ → Выход: {current_price:.2f}₽\n"
                                f"Держали: {duration_hours} ч.\n"
                                f"PnL: {pnl_pct:+.2f}% ({pnl_rub:+.2f}₽)\n"
                                f"Баланс: {rub_balance:.2f}₽\n"
                                f"Время: {current_klg} КЛГ"
                                f"{stats_text}"
                            )
                            
                            send_tg(msg_text)
                            del state["positions"][pos_key]
                        except Exception as e: log.error(f"Sell error {pos_key}: {e}")

                # === ВХОД ===
                if pos_key not in state["positions"]:
                    model = models.get(mode)
                    signal = 0
                    prob = 0.0
                    
                    if model is not None:
                        try:
                            X = last_candle[FEATURE_COLS].values.reshape(1, -1)
                            if hasattr(model, "predict_proba"):
                                prob = model.predict_proba(X)[0][1]
                                signal = 1 if prob >= MIN_PROBABILITY else 0
                            else:
                                signal = int(model.predict(X)[0])
                                prob = 1.0 if signal == 1 else 0.0
                        except Exception as e: log.error(f"Pred error {pos_key}: {e}")
                    elif cfg["source"] == "model_custom":
                        if last_candle['rsi'] < 30 and last_candle['macd_hist'] > 0:
                            signal = 1
                            prob = 1.0

                    news_data = news_scores.get(ticker, {})
                    news_score = news_data.get("score", 0.0) if isinstance(news_data, dict) else 0.0
                    
                    log.info(f"{pos_key}: prob={prob:.2f}, news={news_score:.2f}, signal={signal}, balance={rub_balance:.2f}")

                    if signal == 1:
                        if state["last_h1_candle"].get(pos_key) == last_candle_time:
                            continue

                        if news_score < NEWS_BLOCK_THRESHOLD:
                            log.info(f"{pos_key} SIGNAL! Но новости плохие ({news_score}). Пропуск.")
                            continue
                        
                        trade_cost = current_price * lot
                        if rub_balance < trade_cost:
                            if rub_balance < 100 and not state.get("alert_sent_v3", False):
                                log.warning(f"{pos_key} Баланс критический ({rub_balance:.2f}₽). Требуется пополнение.")
                                send_tg(f"⚠️ <b>ВНИМАНИЕ! ДЕНЬГИ ЗАКОНЧИЛИСЬ</b>\n\nБаланс песочницы упал до {rub_balance:.2f} ₽.\nДля совершения новых сделок необходимо пополнить счет.")
                                state["alert_sent_v3"] = True
                            else:
                                log.warning(f"{pos_key} SIGNAL! Но не хватает на лот (нужно {trade_cost:.2f}₽, есть {rub_balance:.2f}₽). Пропуск.")
                            continue
                        
                        log.info(f"{pos_key} SIGNAL! Buying...")
                        try:
                            client.sandbox.post_sandbox_order(figi=figi, quantity=1, direction=OrderDirection.ORDER_DIRECTION_BUY, account_id=acc_id, order_type=OrderType.ORDER_TYPE_MARKET)
                            entry_price = current_price
                            tp_price = entry_price * (1 + cfg["params"]["tp_pct"] / 100)
                            sl_price = entry_price * (1 - cfg["params"]["sl_pct"] / 100)
                            exit_time = now_time + timedelta(hours=cfg["params"]["time_exit_h"])
                            
                            rub_balance -= trade_cost
                            
                            state["positions"][pos_key] = {
                                "side": "long", "entry": entry_price, "qty": 1,
                                "entry_time": now_time.isoformat(),
                                "entry_prob": prob,
                                "tp": tp_price, "sl": sl_price,
                                "trailing_stop": sl_price, "highest": entry_price,
                                "exit_time": exit_time.isoformat(), "figi": figi
                            }
                            state["last_h1_candle"][pos_key] = last_candle_time
                            
                            history.append({
                                "ticker": ticker,
                                "mode": mode,
                                "type": "BUY",
                                "entry_time": now_time.isoformat(),
                                "entry_price": round(entry_price, 2),
                                "entry_prob": round(prob, 4)
                            })
                            
                            send_tg(f"🟢 <b>ПОКУПКА (LONG) {ticker} [{mode.upper()}]</b>\n"
                                    f"Цена: {entry_price:.2f}₽\n"
                                    f"Лот: {lot} шт.\n"
                                    f"TP: {tp_price:.2f}₽\n"
                                    f"SL: {sl_price:.2f}₽\n"
                                    f"Вероятность: {prob*100:.0f}%\n"
                                    f"Остаток баланса: {rub_balance:.2f}₽\n"
                                    f"Время: {current_klg} КЛГ")
                        except Exception as e: log.error(f"Buy error {pos_key}: {e}")

    with open(STATE_FILE, "w") as f: json.dump(state, f, indent=2, default=str)
    with open(HISTORY_FILE, "w") as f: json.dump(history, f, indent=2, default=str)
    log.info("Simulator done.")

if __name__ == "__main__":
    main()