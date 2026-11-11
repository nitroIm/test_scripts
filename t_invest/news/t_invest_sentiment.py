# ============================================================
# T-INVEST SENTIMENT ENGINE (с фильтром макро и учётом источника)
# Path: t_invest/news/t_invest_sentiment.py
# ============================================================

import json, logging, re
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("sentiment")

NEWS_FILE = Path("t_invest/data/news/t_invest_news_collector.json")
SCORES_FILE = Path("t_invest/data/news/t_invest_news_scores.json")
DICT_FILE = Path("t_invest/data/news/sentiment_dictionary.json")

# Если у новости больше стольких тикеров — это макро-новость, идёт отдельно
MACRO_TICKER_THRESHOLD = 5

# Вес источника (eDisclosure — просто раскрытие фактов, понижаем вес)
SOURCE_WEIGHTS = {
    "eDisclosure": 0.5,
}

def load_dictionary():
    if not DICT_FILE.exists():
        log.error(f"Dictionary file not found: {DICT_FILE}")
        return None
    with open(DICT_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def load_news():
    if not NEWS_FILE.exists():
        log.error("News file not found")
        return []
    with open(NEWS_FILE, "r", encoding="utf-8") as f:
        content = f.read().strip()
        return json.loads(content) if content else []

def save_scores(scores):
    SCORES_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(SCORES_FILE, "w", encoding="utf-8") as f:
        json.dump(scores, f, ensure_ascii=False, indent=2)
    log.info(f"Saved scores for {len(scores)} entries to {SCORES_FILE}")

def get_source_weight(source):
    return SOURCE_WEIGHTS.get(source, 1.0)

def analyze_text(text, dictionary):
    if not text:
        return 0.0

    text_lower = text.lower()
    total_score = 0.0
    words = dictionary.get("words", {})
    boosters = dictionary.get("boosters", {})
    dampeners = dictionary.get("dampeners", {})

    tokens = re.findall(r'\b\w+\b', text_lower)
    
    for i, token in enumerate(tokens):
        weight = words.get(token, 0.0)
        if weight == 0:
            continue
        
        modifier = 1.0
        if i > 0:
            prev = tokens[i-1]
            if prev in boosters:
                modifier = boosters[prev]
            elif prev in dampeners:
                modifier = dampeners[prev]
        
        total_score += weight * modifier

    return total_score

def main():
    log.info("STARTING SENTIMENT ENGINE")
    dictionary = load_dictionary()
    if not dictionary:
        return

    news = load_news()
    if not news:
        log.warning("No news to analyze")
        return

    ticker_scores = {}
    market_total = 0.0
    market_count = 0
    macro_skipped = 0

    for item in news:
        title = item.get("title", "")
        content = item.get("content", "")
        full_text = f"{title} {content}"
        
        base_score = analyze_text(full_text, dictionary)
        if base_score == 0:
            continue

        source = item.get("source", "")
        news_score = base_score * get_source_weight(source)
        
        tickers = item.get("tickers", [])
        
        # Если новость макро (много тикеров) — обрабатываем отдельно
        if len(tickers) > MACRO_TICKER_THRESHOLD:
            market_total += news_score
            market_count += 1
            macro_skipped += 1
            continue
        
        for ticker in tickers:
            if ticker not in ticker_scores:
                ticker_scores[ticker] = {"total_score": 0.0, "count": 0}
            ticker_scores[ticker]["total_score"] += news_score
            ticker_scores[ticker]["count"] += 1

    now_iso = datetime.now(timezone.utc).isoformat()

    result = {}
    for ticker, data in ticker_scores.items():
        avg = data["total_score"] / data["count"] if data["count"] > 0 else 0
        normalized = max(-1.0, min(1.0, avg))
        result[ticker] = {
            "score": round(normalized, 2),
            "news_count": data["count"],
            "updated_at": now_iso
        }

    # Добавляем общий фон рынка
    if market_count > 0:
        avg = market_total / market_count
        result["_MARKET_"] = {
            "score": round(max(-1.0, min(1.0, avg)), 2),
            "news_count": market_count,
            "updated_at": now_iso
        }

    save_scores(result)
    if macro_skipped:
        log.info(f"Separated {macro_skipped} macro-news to _MARKET_")
    log.info("SENTIMENT ENGINE DONE")

if __name__ == "__main__":
    main()