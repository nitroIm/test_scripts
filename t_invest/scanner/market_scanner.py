# PROD CONTOUR ONLY
# Python: 3.10
# t-tech-investments: 1.49.3
#
# ИЗМЕНЕНИЯ v1.1:
#   - ФИКС КРИТИЧЕСКИЙ: with_retry теперь передаёт client в обёртки.
#     Раньше каждая бумага падала с TypeError (missing 'client'),
#     сканер отсеивал все 1909 акций и писал пустой whitelist.
#   - ФИКС: REQUEST_DELAY объявлен, но не использовался. Теперь пауза
#     реально работает — пауза стоит между запросами к API.
#   - Атомарная запись whitelist через .tmp: крэш на середине записи
#     больше не оставит битый файл.
#
# Осталось с прошлой версии:
#   - RETRY до 3 попыток при временных ошибках API.
#   - Причины отсева пишутся в лог (ошибки API — каждая, фильтры — суммарно).
#   - Незакрытая дневная свеча отрезается, чтобы не портить средние.

import os
import json
import time
import logging
from datetime import timedelta, datetime, timezone
from pathlib import Path

from t_tech.invest import Client
from t_tech.invest.constants import INVEST_GRPC_API
from t_tech.invest.schemas import CandleInterval, InstrumentStatus
from t_tech.invest.utils import now

TOKEN = os.environ.get("T_INVEST_TOKEN")

# === ЖЕСТКИЕ ФИЛЬТРЫ ЛИКВИДНОСТИ ===
MIN_DAILY_TURNOVER_RUB = 50_000_000
MAX_SPREAD_PERCENT = 0.5
CANDLES_DAYS = 10

# === ЗАЩИТА ОТ RATE LIMIT ===
REQUEST_DELAY = 0.25      # секунд между бумагами (~240 req/min)
MAX_RETRIES = 3           # попыток на запрос при сетевой ошибке
RETRY_DELAY = 2.0         # базовая пауза между попытками, сек

OUTPUT_PATH = Path("t_invest/data/scanner/whitelist.json")

log = logging.getLogger("scanner")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# Ошибки, при которых имеет смысл повторить запрос (rate limit / сеть)
RETRYABLE_MARKERS = ("rate limit", "ratelimit", "too many requests", "unavailable", "timeout", "connection")


def quotation_to_float(q):
    if q is None:
        return 0.0
    return q.units + (q.nano / 1e9)


def classify_volatility(avg_range):
    if avg_range < 2.0:
        return "LOW_VOL"
    elif avg_range < 5.0:
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
        return
