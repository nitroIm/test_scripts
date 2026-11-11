# ============================================================
# T-INVEST NEWS COLLECTOR
# Path: t_invest/news/t_invest_news_collector.py
# ============================================================

import os, json, logging, hashlib
from datetime import datetime, timezone, timedelta
from pathlib import Path
from t_tech.invest import Client
from t_tech.invest.constants import INVEST_GRPC_API
from t_tech.invest.utils import now

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("news_collector")

# --- НАСТРОЙКИ ---
TOKEN = os.environ.get("T_INVEST_TOKEN")
WHITELIST_FILE = Path("t_invest/data/scanner/whitelist.json")
NEWS_FILE = Path("t_invest/data/news/t_invest_news_collector.json")

# Глубина запроса: 36 часов
FETCH_HOURS = 36
# Срок хранения: 30 дней
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
    """Стабильный хеш заголовка для дедупликации"""
    normalized = title.lower().strip()
    return hashlib.md5(normalized.encode()).hexdigest()

def main():
    log.info("STARTING NEWS COLLECTOR")
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

    with Client(TOKEN, target=INVEST_GRPC_API) as client:
        try:
            # Запрашиваем новости (limit=1000 — максимум)
            response = client.instruments.news(limit=1000)
            items = response.items
            log.info(f"Received {len(items)} news items from API")

            for item in items:
                # Проверяем, относится ли новость к нашим тикерам
                tickers_in_news = [inst.ticker for inst in item.instrument_id]
                matching = set(tickers_in_news) & tickers
                if not matching:
                    continue

                # Проверяем время публикации
                pub_time = item.ts
                if pub_time.tzinfo is None:
                    pub_time = pub_time.replace(tzinfo=timezone.utc)
                if pub_time < cutoff_fetch:
                    continue

                # Дедупликация по ID
                if item.id in existing_ids:
                    continue

                # Дедупликация по заголовку
                h = news_hash(item.title)
                if h in existing_hashes:
                    continue

                # Формируем запись
                record = {
                    "id": item.id,
                    "tickers": list(matching),
                    "title": item.title,
                    "content": item.content[:500] if item.content else "",
                    "source": item.source,
                    "ts": pub_time.isoformat(),
                    "hash": h,
                }
                new_items.append(record)
                existing_ids.add(item.id)
                existing_hashes.add(h)

        except Exception as e:
            log.error(f"Error fetching news: {e}")
            return

    if new_items:
        log.info(f"New unique news items: {len(new_items)}")
        existing.extend(new_items)
    else:
        log.info("No new unique news items")

    # Очистка старых записей (старше STORE_DAYS)
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
            cleaned.append(item)  # оставляем, если не смогли распарсить

    if removed:
        log.info(f"Removed {removed} old news items")

    save_news(cleaned)
    log.info("NEWS COLLECTOR DONE")

if __name__ == "__main__":
    main()