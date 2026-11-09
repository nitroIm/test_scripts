# ============================================================
# T-INVEST - TRAINER ORCHESTRATOR (LONG ONLY)
# Path: t_invest/learn/t_invest_learn.py
# ============================================================

import os, json, logging, importlib.util, requests, pandas as pd, numpy as np
from pathlib import Path
from datetime import datetime, timezone, timedelta
from t_tech.invest import Client
from t_tech.invest.constants import INVEST_GRPC_API
from t_tech.invest.schemas import CandleInterval
from t_tech.invest.utils import now

VERSION = "6.0-long-only"
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("t_invest.trainer")

TOKEN = os.environ.get("T_INVEST_TOKEN")
TG_TOKEN = os.environ.get("INVEST_BOT_TOKEN")
TG_CHAT_ID = os.environ.get("INVEST_BOT_CHAT_ID")

WHITELIST_PATH = "t_invest/data/scanner/whitelist.json"
MODEL_OUT_FILE = Path("t_invest/data/model/best_params.json")
MODELS_SRC_DIR = Path("t_invest/learn/models")

TOP_N_STOCKS = 5        
HISTORY_DAYS = 90       

MODEL_OUT_FILE.parent.mkdir(parents=True, exist_ok=True)

def send_telegram(text):
    if not TG_TOKEN or not TG_CHAT_ID: return
    try:
        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": TG_CHAT_ID, "text": text, "parse_mode": "HTML"}, timeout=10)
    except Exception as e: log.error(f"Telegram error: {e}")

def calculate_ema(s, p): return s.ewm(span=p, adjust=False).mean()
def calculate_rsi(s, p=14):
    d = s.diff()
    g = (d.where(d > 0, 0)).rolling(window=p).mean()
    l = (-d.where(d < 0, 0)).rolling(window=p).mean()
    return 100 - (100 / (1 + g/l))
def calculate_macd(s, f=12, sl=26, sig=9):
    m = calculate_ema(s, f) - calculate_ema(s, sl)
    return m - calculate_ema(m, sig)
def calculate_atr(df, p=14):
    tr = pd.concat([df['high']-df['low'], (df['high']-df['close'].shift()).abs(), (df['low']-df['close'].shift()).abs()], axis=1).max(axis=1)
    return tr.rolling(window=p).mean()

def fetch_data(client, figi, days=HISTORY_DAYS):
    end = now(); start = end - timedelta(days=days); all_c = []; cur = start
    while cur < end:
        c_end = min(cur + timedelta(days=90), end)
        try:
            resp = client.market_data.get_candles(figi=figi, from_=cur, to=c_end, interval=CandleInterval.CANDLE_INTERVAL_HOUR)
            all_c.extend(resp.candles)
        except: pass
        cur = c_end
    if not all_c: return pd.DataFrame()
    rows = [{"open_time": c.time, "open": c.open.units+c.open.nano/1e9, "high": c.high.units+c.high.nano/1e9, "low": c.low.units+c.low.nano/1e9, "close": c.close.units+c.close.nano/1e9, "volume": c.volume} for c in all_c]
    df = pd.DataFrame(rows); df['open_time'] = pd.to_datetime(df['open_time'], utc=True); return df

def add_indicators(df):
    df['rsi'] = calculate_rsi(df['close'], 14); df['rsi_7'] = calculate_rsi(df['close'], 7); df['rsi_21'] = calculate_rsi(df['close'], 21)
    df['macd_hist'] = calculate_macd(df['close']); df['ema_50'] = calculate_ema(df['close'], 50); df['ema_20'] = calculate_ema(df['close'], 20); df['ema_200'] = calculate_ema(df['close'], 200)
    df['vol_sma'] = df['volume'].rolling(window=20).mean()
    df['atr_7'] = calculate_atr(df, 7); df['atr_14'] = calculate_atr(df, 14); df['atr_50'] = calculate_atr(df, 50); df['atr_100'] = calculate_atr(df, 100)
    df['price_change_1h'] = df['close'].pct_change(1); df['price_change_4h'] = df['close'].pct_change(4); df['price_change_24h'] = df['close'].pct_change(24)
    return df.dropna()

def load_models():
    models = []
    for f in MODELS_SRC_DIR.glob("model_*.py"):
        name = f.stem
        try:
            spec = importlib.util.spec_from_file_location(name, f); mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
            if hasattr(mod, "train"): models.append((name, mod))
        except Exception as e: log.error(f"Failed to load {name}: {e}")
    return models

def main():
    log.info(f"STARTING TRAINER v{VERSION}")
    with open(WHITELIST_PATH, "r", encoding="utf-8") as f: data = json.load(f)
    stocks = data["data"] if isinstance(data, dict) and "data" in data else data
    
    # Берем ТОП-5 по волатильности (без фильтра тренда)
    stocks.sort(key=lambda x: x.get("avg_daily_range_pct", 0), reverse=True)
    top_stocks = stocks[:TOP_N_STOCKS]

    log.info(f"TOP-{TOP_N_STOCKS} for LONG: {[s['ticker'] for s in top_stocks]}")
    dfs = []
    
    with Client(TOKEN, target=INVEST_GRPC_API) as client:
        for s in top_stocks:
            df = fetch_data(client, s["figi"])
            if not df.empty:
                df = add_indicators(df)
                if len(df) > 100: 
                    df['ticker'] = s["ticker"]; dfs.append(df)

    full_df = pd.concat(dfs).sort_values('open_time').reset_index(drop=True) if dfs else pd.DataFrame()
    models = load_models()
    
    out_data = {"trainer_version": VERSION, "updated_at": datetime.now(timezone.utc).isoformat(), "long_tickers": [s["ticker"] for s in top_stocks], "intraday": {"long": None}, "swing": {"long": None}}

    for mode in ["intraday", "swing"]:
        log.info(f"--- Searching best model for {mode.upper()} / LONG ---")
        best_score = -99999; best_model_data = None

        for model_name, module in models:
            try:
                res = module.train(full_df, side="long", mode=mode)
                if res and res.get("metrics"):
                    sc = res["metrics"].get("score", -99999)
                    if sc > best_score:
                        best_score = sc; res["source"] = model_name; best_model_data = res
                        log.info(f"  🏆 New best: {model_name} (Score: {sc})")
            except Exception as e: log.error(f"  ❌ Model {model_name} crashed: {e}")
                
        if best_model_data:
            out_data[mode]["long"] = best_model_data
            if "model_path" in best_model_data:
                old_p = Path(best_model_data["model_path"]); new_p = MODEL_OUT_FILE.parent / f"best_{mode}_long.pkl"
                if old_p.exists(): os.replace(old_p, new_p); best_model_data["model_path"] = str(new_p)

    for pkl in MODEL_OUT_FILE.parent.glob("model_*.pkl"): pkl.unlink()
    with open(MODEL_OUT_FILE, "w", encoding="utf-8") as f: json.dump(out_data, f, ensure_ascii=False, indent=2)
    
    msg = f"🏆 <b>Обучение (LONG ONLY) завершено</b>\n\n📈 Акции: {', '.join([s['ticker'] for s in top_stocks])}\n\n"
    for mode in ["intraday", "swing"]:
        res = out_data[mode]["long"]
        if res: msg += f"<b>{mode.upper()} LONG</b>: {res['source']} (Score: {res['metrics']['score']})\n"
    send_telegram(msg)

if __name__ == "__main__": main()