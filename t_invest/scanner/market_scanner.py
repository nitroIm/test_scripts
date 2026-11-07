# PROD CONTOUR ONLY
# Python: 3.10
# t-tech-investments: 1.49.3

import os
import json
from datetime import timedelta, datetime, timezone

from t_tech.invest import Client
from t_tech.invest.constants import INVEST_GRPC_API
from t_tech.invest.schemas import CandleInterval, InstrumentStatus
from t_tech.invest.utils import now

TOKEN = os.environ.get("T_INVEST_TOKEN")

# === НАСТРОЙКИ ФИЛЬТРОВ ===
MIN_DAILY_TURNOVER_RUB = 50_000_000  # 50 млн рублей
MAX_SPREAD_PERCENT = 0.5             # 0.5%
CANDLES_DAYS = 10                    # дней истории для анализа

def quotation_to_float(q):
    if q is None:
        return 0.0
    return q.units + (q.nano / 1e9)

def classify_volatility(avg_daily_range_pct):
    if avg_daily_range_pct < 2.0:
        return "LOW_VOL"
    elif avg_daily_range_pct < 5.0:
        return "MID_VOL"
    else:
        return "HIGH_VOL"

def classify_trend(closes):
    if len(closes) < 5:
        return "SIDEWAYS"
    recent = closes[-5:]
    if recent[-1] > recent[0] * 1.02:
        return "UP"
    elif recent[-1] < recent[0] * 0.98:
        return "DOWN"
    else:
        return "SIDEWAYS"

def analyze_share(client, share):
    figi = share.figi
    ticker = share.ticker

    try:
        ob = client.market_data.get_order_book(figi=figi, depth=1)
        if not ob.bids or not ob.asks:
            return None, "Нет заявок в стакане"
        best_bid = quotation_to_float(ob.bids[0].price)
        best_ask = quotation_to_float(ob.asks[0].price)
        if best_bid <= 0 or best_ask <= 0:
            return None, "Нулевые цены в стакане"
        spread_pct = (best_ask - best_bid) / best_bid * 100
        if spread_pct > MAX_SPREAD_PERCENT:
            return None, f"Спред {spread_pct:.2f}% > {MAX_SPREAD_PERCENT}%"
    except Exception as e:
        return None, f"Ошибка стакана: {e}"

    try:
        candles_resp = client.market_data.get_candles(
            figi=figi,
            from_=now() - timedelta(days=CANDLES_DAYS),
            to=now(),
            interval=CandleInterval.CANDLE_INTERVAL_DAY,
        )
        candles = candles_resp.candles
        if len(candles) < 3:
            return None, "Мало дневных свечей"
    except Exception as e:
        return None, f"Ошибка свечей: {e}"

    turnovers = []
    ranges = []
    closes = []
    for c in candles:
        close = quotation_to_float(c.close)
        high = quotation_to_float(c.high)
        low = quotation_to_float(c.low)
        vol = c.volume
        turnover_rub = vol * close
        turnovers.append(turnover_rub)
        if low > 0:
            ranges.append((high - low) / low * 100)
        closes.append(close)

    avg_turnover = sum(turnovers) / len(turnovers)
    if avg_turnover < MIN_DAILY_TURNOVER_RUB:
        return None, f"Оборот {avg_turnover/1e6:.1f} млн < {MIN_DAILY_TURNOVER_RUB/1e6} млн"

    avg_range = sum(ranges) / len(ranges) if ranges else 0
    vol_tag = classify_volatility(avg_range)
    trend = classify_trend(closes)

    result = {
        "ticker": ticker,
        "figi": figi,
        "name": share.name,
        "trade_method": "API" if share.api_trade_available_flag else "MANUAL",
        "api_trade_available": share.api_trade_available_flag,
        "buy_available": share.buy_available_flag,
        "sell_available": share.sell_available_flag,
        "lot": share.lot,
        "last_price": quotation_to_float(candles[-1].close),
        "avg_daily_turnover_rub": round(avg_turnover, 2),
        "spread_pct": round(spread_pct, 4),
        "avg_daily_range_pct": round(avg_range, 2),
        "volatility_tag": vol_tag,
        "trend": trend,
        "is_new": False,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    return result, None

def main():
    if not TOKEN:
        print("❌ T_INVEST_TOKEN не задан")
        return

    output_path = "t_invest/data/scanner/whitelist.json"
    old_data = {}
    if os.path.exists(output_path):
        try:
            with open(output_path, "r", encoding="utf-8") as f:
                content = f.read()
                if content:
                    old_list = json.loads(content)
                    old_data = {item["ticker"]: item for item in old_list}
        except Exception as e:
            print(f"⚠️ Не удалось прочитать старый whitelist: {e}")

    with Client(TOKEN, target=INVEST_GRPC_API) as client:
        shares_resp = client.instruments.shares(
            instrument_status=InstrumentStatus.INSTRUMENT_STATUS_ALL
        )
        shares = shares_resp.instruments
        print(f"Всего акций получено: {len(shares)}")

        results = []
        skipped = 0
        
        for share in shares:
            # Проверяем только флаги, которые гарантированно работают в API
            if not share.buy_available_flag or not share.sell_available_flag:
                skipped += 1
                continue

            analyzed, reason = analyze_share(client, share)
            if analyzed:
                if share.ticker not in old_data:
                    analyzed["is_new"] = True
                results.append(analyzed)
            else:
                skipped += 1

        print(f"✅ Прошло фильтры: {len(results)}")
        print(f"⛔ Отсеяно: {skipped}")

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

        print(f"💾 Сохранено в {output_path}")

if __name__ == "__main__":
    main()