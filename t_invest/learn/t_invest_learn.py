# ============================================================
# T-INVEST - TRAINER ORCHESTRATOR (LONG & SHORT, ONLINE CUSTOM)
# Version: 7.4
# Path: t_invest/learn/t_invest_learn.py
# ============================================================

import os, json, logging, importlib.util, pandas as pd, numpy as np, time, subprocess
from pathlib import Path
from datetime import datetime, timezone, timedelta
from t_tech.invest import Client
from t_tech.invest.constants import INVEST_GRPC_API
from t_tech.invest.schemas import CandleInterval
from t_tech.invest.utils import now

# --- КОНФИГУРАЦИЯ ---
VERSION = "7.4-online-custom-180d"
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("t_invest.trainer")

TOKEN = os.environ.get("T_INVEST_TOKEN")
WHITELIST_PATH = "t_invest/data/scanner/whitelist.json"
MODEL_OUT_FILE = Path("t_invest/data/model/best_params.json")
MODELS_SRC_DIR = Path("t_invest/learn/models")

TOP_N_STOCKS = 5
HISTORY_DAYS = 180

# Валидация: ниже этих порогов обучение не состоится
MIN_STOCKS = 3      # минимум бумаг в whitelist
MIN_ROWS = 500      # минимум строк данных после загрузки

# Телеграм для алертов (те же секреты, что у отчёта)
ALERT_TOKEN = os.environ.get("INVEST_BOT_TOKEN", "").strip()
ALERT_CHAT = os.environ.get("INVEST_BOT_CHAT_ID", "").strip()

MODEL_OUT_FILE.parent.mkdir(parents=True, exist_ok=True)


def send_alert(text):
    """Алерты о провале обучения. Не мешает exit, если Telegram недоступен."""
    if not ALERT_TOKEN or not ALERT_CHAT:
        log.warning("Нет секретов для алерта — сообщение ушло только в лог.")
        return
    try:
        import requests
        url = f"https://api.telegram.org/bot{ALERT_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": ALERT_CHAT, "text": text, "parse_mode": "HTML"}, timeout=10)
    except Exception as e:
        log.warning(f"Алерт не отправлен: {e}")


# --- ИНДИКАТОРЫ ---
def calculate_ema(s, p): return s.ewm(span=p, adjust=False).mean()
def calculate_rsi(s, p=14):
    d = s.diff(); g = (d.where(d > 0, 0)).rolling(window=p).mean(); l = (-d.where(d < 0, 0)).rolling(window=p).mean()
    return 100 - (100 / (1 + g/l))
def calculate_macd(s, f=12, sl=26, sig=9):
    m = calculate_ema(s, f) - calculate_ema(s, sl); return m - calculate_ema(m, sig)
def calculate_atr(df, p=14):
    tr = pd.concat([df['high']-df['low'], (df['high']-df['close'].shift()).abs(), (df['low']-df['close'].shift()).abs()], axis=1).max(axis=1)
    return tr.rolling(window=p).mean()


# --- ЗАГРУЗКА ДАННЫХ ---
def fetch_data(client, figi, days=HISTORY_DAYS, ticker=""):
    end = now(); start = end - timedelta(days=days); all_c = []; cur = start
    while cur < end:
        c_end = min(cur + timedelta(days=90), end)
        try:
            resp = client.market_data.get_candles(figi=figi, from_=cur, to=c_end, interval=CandleInterval.CANDLE_INTERVAL_HOUR)
            all_c.extend(resp.candles)
        except Exception as e:
            # ГЛОТАТЬ ОШИБКИ МОЛЧА БОЛЬШЕ НЕЛЬЗЯ: каждая ошибка видна в логе
            log.error(f"  Fetch error {ticker or figi} [{cur:%Y-%m-%d}]: {e}")
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


# --- ЗАГРУЗКА МОДЕЛЕЙ ---
def load_models():
    models = []
    for f in MODELS_SRC_DIR.glob("model_*.py"):
        name = f.stem
        try:
            spec = importlib.util.spec_from_file_location(name, f); mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
            if hasattr(mod, "train"): models.append((name, mod))
        except Exception as e: log.error(f"Failed to load {name}: {e}")
    return models


def cleanup_model_files():
    """Ротация артефактов: в папке моделей остаются только best_*.pkl.
    Всё остальное (временные, незавершённые) удаляется."""
    kept = 0; removed = 0
    for pkl in MODEL_OUT_FILE.parent.glob("*.pkl"):
        if pkl.name.startswith("best_"):
            kept += 1
        else:
            pkl.unlink(missing_ok=True); removed += 1
    log.info(f"Model cleanup: kept {kept} best_*.pkl, removed {removed} stray files.")


def main():
    start_time = time.time()
    log.info(f"STARTING TRAINER v{VERSION}")

    # --- ШАГ 1: whitelist ---
    if not os.path.exists(WHITELIST_PATH):
        msg = "🚫 Тренер: whitelist.json не найден.\nСканер не отработал до тренера — проверь порядок шагов в workflow."
        log.error(msg); send_alert(msg); sys.exit(1)

    try:
        with open(WHITELIST_PATH, "r", encoding="utf-8") as f: data = json.load(f)
    except Exception as e:
        msg = f"🚫 Тренер: whitelist.json битый ({e})."
        log.error(msg); send_alert(msg); sys.exit(1)

    stocks = data["data"] if isinstance(data, dict) and "data" in data else data

    # ЗАЩИТА: пустой whitelist = провал ДО всякого обучения.
    # best_params.json НЕ трогаем — вчерашние модели остаются в силе.
    if not stocks or len(stocks) < MIN_STOCKS:
        msg = (
            "⚠️ <b>Обучение отменено: пустой whitelist</b>\n\n"
            f"Бумаг в сканере: <b>{len(stocks) if stocks else 0}</b> (нужно минимум {MIN_STOCKS}).\n"
            "best_params.json НЕ перезаписан — работает предыдущая модель.\n\n"
            "Проверь шаг сканера: почему он вернул пустоту."
        )
        log.error(f"Whitelist has {len(stocks) if stocks else 0} stocks — aborting BEFORE training.")
        send_alert(msg)
        sys.exit(1)

    stocks.sort(key=lambda x: x.get("avg_daily_range_pct", 0), reverse=True)
    top_stocks = stocks[:TOP_N_STOCKS]

    log.info(f"TOP-{TOP_N_STOCKS} for training: {[s['ticker'] for s in top_stocks]}")

    # --- ШАГ 2: загрузка данных ---
    dfs = []
    fetch_errors = 0
    with Client(TOKEN, target=INVEST_GRPC_API) as client:
        for s in top_stocks:
            df = fetch_data(client, s["figi"], ticker=s["ticker"])
            if not df.empty:
                df = add_indicators(df)
                if len(df) > 100:
                    df['ticker'] = s["ticker"]; dfs.append(df)
                else:
                    fetch_errors += 1
                    log.warning(f"  {s['ticker']}: после индикаторов осталось {len(df)} строк — пропущен.")
            else:
                fetch_errors += 1
                log.warning(f"  {s['ticker']}: свечи не получены вовсе.")

    full_df = pd.concat(dfs).sort_values('open_time').reset_index(drop=True) if dfs else pd.DataFrame()

    # ЗАЩИТА: данных нет — обучение не запускаем, best_params.json НЕ трогаем.
    if full_df.empty or len(full_df) < MIN_ROWS:
        msg = (
            "⚠️ <b>Обучение отменено: нет данных</b>\n\n"
            f"Бумаг выбрано: <b>{len(top_stocks)}</b>\n"
            f"Строк получено: <b>{len(full_df)}</b> (нужно минимум {MIN_ROWS})\n"
            f"Ошибок загрузки: <b>{fetch_errors}</b>\n\n"
            "best_params.json НЕ перезаписан — работает предыдущая модель.\n\n"
            "Возможные причины: невалидный T_INVEST_TOKEN, недоступен API Тинькофф,"
            " или биржа не отдала свечи. Смотри строки 'Fetch error' в логе."
        )
        log.error(f"Insufficient data: rows={len(full_df)}, fetch_errors={fetch_errors} — aborting BEFORE training.")
        send_alert(msg)
        sys.exit(1)

    log.info(f"Data OK: {len(full_df)} rows from {len(dfs)} tickers. Training...")

    models = load_models()
    if not models:
        msg = "🚫 Тренер: не загружено ни одной модели из models/ — нечему обучаться."
        log.error(msg); send_alert(msg); sys.exit(1)

    # --- ШАГ 3: обучение ---
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

    # --- ШАГ 4: атомарная запись результатов ---
    out_data["stats"] = {
        "total_rows": len(full_df),
        "elapsed_seconds": int(time.time() - start_time),
        "fetch_errors": fetch_errors
    }

    # Пишем через временный файл: крэш на середине записи не оставит битый JSON
    tmp_file = MODEL_OUT_FILE.with_suffix(".json.tmp")
    with open(tmp_file, "w", encoding="utf-8") as f:
        json.dump(out_data, f, ensure_ascii=False, indent=2)
    os.replace(tmp_file, MODEL_OUT_FILE)

    # Ротация: удаляем всё лишнее, оставляем только best_*.pkl
    cleanup_model_files()

    log.info(f"Training done in {int(time.time() - start_time)} sec. Starting report script...")
    subprocess.run(["python", "t_invest/reports/t_invest_learn_report.py"], check=False)


if __name__ == "__main__":
    main()
