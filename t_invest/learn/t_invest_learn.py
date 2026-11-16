# ============================================================
# T-INVEST - TRAINER ORCHESTRATOR (LONG & SHORT, ONLINE CUSTOM)
# Path: t_invest/learn/t_invest_learn.py
# ============================================================

import os, json, logging, importlib.util, pandas as pd, numpy as np, time, subprocess
from pathlib import Path
from datetime import datetime, timezone, timedelta
from t_tech.invest import Client
from t_tech.invest.constants import INVEST_GRPC_API
from t_tech.invest.schemas import CandleInterval
from t_tech.invest.utils import now

VERSION = "7.3-online-custom"
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("t_invest.trainer")

TOKEN = os.environ.get("T_INVEST_TOKEN")
WHITELIST_PATH = "t_invest/data/scanner/whitelist.json"
MODEL_OUT_FILE = Path("t_invest/data/model/best_params.json")
MODELS_SRC_DIR = Path("t_invest/learn/models")

TOP_N_STOCKS = 5
HISTORY_DAYS = 180

MODEL_OUT_FILE.parent.mkdir(parents=True, exist_ok=True)

# ... (функции calculate_ema, calculate_rsi, calculate_macd, calculate_atr, fetch_data, add_indicators, load_models остаются без изменений)

def main():
    start_time = time.time()
    log.info(f"STARTING TRAINER v{VERSION}")

    with open(WHITELIST_PATH, "r", encoding="utf-8") as f: data = json.load(f)
    stocks = data["data"] if isinstance(data, dict) and "data" in data else data

    stocks.sort(key=lambda x: x.get("avg_daily_range_pct", 0), reverse=True)
    top_stocks = stocks[:TOP_N_STOCKS]

    log.info(f"TOP-{TOP_N_STOCKS} for training: {[s['ticker'] for s in top_stocks]}")
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

    out_data = {
        "trainer_version": VERSION,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "long_tickers": [s["ticker"] for s in top_stocks],
        "short_tickers": [s["ticker"] for s in top_stocks],
        "intraday": {"long": None, "short": None},
        "swing": {"long": None, "short": None}
    }

    for mode in ["intraday", "swing"]:
        for side in ["long", "short"]:
            log.info(f"--- Searching best model for {mode.upper()} / {side.upper()} ---")
            best_score = -99999; best_model_data = None

            for model_name, module in models:
                try:
                    res = module.train(full_df, side=side, mode=mode)
                    if res and res.get("metrics"):
                        sc = res["metrics"].get("score", -99999)
                        if sc > best_score:
                            best_score = sc; res["source"] = model_name; best_model_data = res
                            log.info(f"  🏆 New best: {model_name} (Score: {sc})")
                except Exception as e:
                    log.error(f"  ❌ Model {model_name} crashed for {side}: {e}")

            if best_model_data:
                out_data[mode][side] = best_model_data
                if "model_path" in best_model_data:
                    old_p = Path(best_model_data["model_path"])
                    new_p = MODEL_OUT_FILE.parent / f"best_{mode}_{side}.pkl"
                    if old_p.exists():
                        os.replace(old_p, new_p)
                        best_model_data["model_path"] = str(new_p)

    out_data["stats"] = {
        "total_rows": len(full_df),
        "elapsed_seconds": int(time.time() - start_time)
    }

    for pkl in MODEL_OUT_FILE.parent.glob("*.pkl"):
        if "best_" not in pkl.name:
            pkl.unlink()

    with open(MODEL_OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(out_data, f, ensure_ascii=False, indent=2)

    log.info("Starting report script...")
    subprocess.run(["python", "t_invest/reports/t_invest_learn_report.py"], check=False)

if __name__ == "__main__":
    main()