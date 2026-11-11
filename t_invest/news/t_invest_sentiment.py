# ============================================================
# T-INVEST SENTIMENT ENGINE
# Path: t_invest/news/t_invest_sentiment.py
# ============================================================

import os, json, logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
import re

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("sentiment")

NEWS_FILE = Path("t_invest/data/news/t_invest_news_collector.json")
SCORES_FILE = Path("t_invest/data/news/t_invest_news_scores.json")

# === НАШ СОБСТВЕННЫЙ СЛОВАРЬ (можно дополнять) ===
POSITIVE_WORDS = [
    "рост", "вырос", "прибыль", "дивиденд", "рекорд", "увеличение", "повышение",
    "контракт", "позитивно", "прорыв", "успех", "развитие", "запуск", "соглашение"
]

NEGATIVE_WORDS = [
    "падение", "упал", "снижение", "убыток", "суд", "штраф", "санкции",
    "отмена", "негативно", "риск", "проблема", "запрет", "остановка", "расследование"
]

# Слова, которые меняют силу (необязательно пока, но задел на будущее)
INTENSIFIERS = ["резкое", "крупное", "серьезное", "существенное"]

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
    log.info(f"Saved scores for {len(scores)} tickers to {SCORES_FILE}")

def analyze_text(text):
    """Возвращает счет тональности для одного текста."""
    if not text:
        return 0.0
    
    text = text.lower()
    score = 0.0
    
    # Считаем позитив
    for word in POSITIVE_WORDS:
        if re.search(r'\b' + re.escape(word) + r'\b', text):
            score += 1.0
            
    # Считаем негатив
    for word in NEGATIVE_WORDS:
        if re.search(r'\b' + re.escape(word) + r'\b', text):
            score -= 1.0
            
    return score

def main():
    log.info("STARTING SENTIMENT ENGINE")
    news = load_news()
    if not news:
        log.warning("No news to analyze")
        return

    # Группируем новости по тикерам
    ticker_scores = {}
    
    for item in news:
        title = item.get("title", "")
        content = item.get("content", "")
        # Склеиваем заголовок и текст для анализа
        full_text = f"{title} {content}"
        
        # Считаем скор для этой новости
        news_score = analyze_text(full_text)
        if news_score == 0:
            continue # Если нейтрально, пропускаем
            
        # Распределяем скор по тикерам
        for ticker in item.get("tickers", []):
            if ticker not in ticker_scores:
                ticker_scores[ticker] = {"total_score": 0.0, "count": 0}
            
            ticker_scores[ticker]["total_score"] += news_score
            ticker_scores[ticker]["count"] += 1

    # Нормализуем (вычисляем средний скор)
    result = {}
    for ticker, data in ticker_scores.items():
        avg = data["total_score"] / data["count"] if data["count"] > 0 else 0
        # Ограничиваем от -1.0 до +1.0
        normalized = max(-1.0, min(1.0, avg))
        result[ticker] = {
            "score": round(normalized, 2),
            "news_count": data["count"],
            "updated_at": datetime.now(timezone.utc).isoformat()
        }

    save_scores(result)
    log.info("SENTIMENT ENGINE DONE")

if __name__ == "__main__":
    main()