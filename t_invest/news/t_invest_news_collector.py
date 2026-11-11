# ============================================================
# T-INVEST NEWS COLLECTOR (REST API VERSION)
# Path: t_invest/news/t_invest_news_collector.py
# ============================================================

import os, json, logging, hashlib, requests
from datetime import datetime, timezone, timedelta
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("news_collector")

TOKEN = os.environ.get("T_INVEST_TOKEN")
WHITELIST_FILE = Path("t_invest/data/scanner/whitelist.json")
NEWS_FILE = Path("t_invest/data/news/t_invest_news_collector.json")

# REST-эндпоинт для получения новостей
NEWS_URL = "https://invest-public-api.tbank.ru/rest/tinkoff.public.invest.api.contract.v1.InstrumentsService/News"

FETCH_HOURS = 36
STORE_DAYS = 30

KLG_TZ = timezone(timedelta(hours=2))

def load_whitelist():
    if not WHITELIST_FILE.exists():
        log.error("whitelist.json not found")
        return set()
    with open(WHITELIST_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    stocks = data.get("data", data) if isinstance(data, dict) else data
    tickers = {s["ticker"] for s in stocks}
    log.info(f"Loaded {len(tickers)} tickers from whitelist")
    return tickers

def load_existing_news():
    if not NEWS_FILE.exists():
        return []
    try:
        with open(NEWS_FILE, "r", encoding="utf-8") as f:
            content = f.read().strip()
            return json.loads(content) if content else []
    except Exception as e:
        log.error(f"Error loading existing news: {e}")
        return []

def save_news(news_list):
    NEWS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(NEWS_FILE, "w", encoding="utf-8") as f:
        json.dump(news_list, f, ensure_ascii=False, indent=2)
    log.info(f"Saved {len(news_list)} news items to {NEWS_FILE}")

def news_hash(title):
    normalized = title.lower().strip()
    return hashlib.md5(normalized.encode()).hexdigest()

def main():
    log.info("STARTING NEWS COLLECTOR (REST API)")
    if not TOKEN:
        log.error("T_INVEST_TOKEN not set")
        return

    tickers = load_whitelist()
    if not tickers:
        log.warning("No tickers to collect news for")
        return

    existing = load_existing_news()
    existing_ids = {item["id"] for item in existing if "id" in item}
    existing_hashes = {news_hash(item["title"]) for item in existing if "title" in item}

    now_utc = datetime.now(timezone.utc)
    cutoff_fetch = now_utc - timedelta(hours=FETCH_HOURS)
    cutoff_store = now_utc - timedelta(days=STORE_DAYS)

    new_items = []

    # Прямой REST-запрос
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {"limit": 1000}

    try:
        resp = requests.post(NEWS_URL, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        items = data.get("items", [])
        log.info(f"Received {len(items)} news items from REST API")

        for item in items:
            # Тикеры, к которым относится новость
            instruments = item.get("instrumentId", [])
            tickers_in_news = []
            for inst in instruments:
                # В REST-ответе структура может быть { instrument: { ticker: ... } }
                if "instrument" in inst:
                    tickers_in_news.append(inst["instrument"].get("ticker"))
                elif "ticker" in inst:
                    tickers_in_news.append(inst["ticker"])
            
            matching = set(tickers_in_news) & tickers
            if not matching:
                continue

            # Время публикации (ISO-строка в поле ts)
            ts_str = item.get("ts")
            if not ts_str:
                continue
            pub_time = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            if pub_time.tzinfo is None:
                pub_time = pub_time.replace(tzinfo=timezone.utc)
            if pub_time < cutoff_fetch:
                continue

            news_id = item.get("id")
            if not news_id or news_id in existing_ids:
                continue

            title = item.get("title", "")
            h = news_hash(title)
            if h in existing_hashes:
                continue

            record = {
                "id": news_id,
                "tickers": list(matching),
                "title": title,
                "content": item.get("content", "")[:500],
                "source": item.get("source", ""),
                "ts": pub_time.isoformat(),
                "hash": h,
            }
            new_items.append(record)
            existing_ids.add(news_id)
            existing_hashes.add(h)

    except Exception as e:
        log.error(f"Error fetching news via REST: {e}")
        return

    if new_items:
        log.info(f"New unique news items: {len(new_items)}")
        existing.extend(new_items)
    else:
        log.info("No new unique news items")

    # Очистка старых записей
    cleaned = []
    removed = 0
    for item in existing:
        try:
            ts = datetime.fromisoformat(item["ts"])
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            if ts >= cutoff_store:
                cleaned.append(item)
            else:
                removed += 1
        except Exception:
            cleaned.append(item)

    if removed:
        log.info(f"Removed {removed} old news items")

    save_news(cleaned)
    log.info("NEWS COLLECTOR DONE")

if __name__ == "__main__":
    main()