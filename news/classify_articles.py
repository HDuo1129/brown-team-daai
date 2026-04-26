"""
news/classify_articles.py
=========================
Classify all articles in articles_text.csv using Groq (LLaMA, free tier).
Saves to news/articles_classified.csv. Supports resume — done uids are skipped.

Articles within 4 weeks before a manager change are classified first.

Free-tier limits: 30 RPM, 14,400 RPD → all 2,524 articles in ~90 min.

Usage:
    export GROQ_API_KEY=gsk_...
    python news/classify_articles.py            # classify up to 1400 (safe)
    python news/classify_articles.py --all      # classify everything
    python news/classify_articles.py --limit 50 # quick test
"""
import json
import os
import time
import argparse
import logging
import groq
import pandas as pd
from pathlib import Path

ROOT          = Path(__file__).parent.parent
ARTICLES      = ROOT / "news" / "articles_text.csv"
MANAGERS      = ROOT / "managers" / "managers.csv"
OUT_CSV       = ROOT / "news" / "articles_classified.csv"
MODEL         = "llama-3.3-70b-versatile"
DAILY_DEFAULT = 1400

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger(__name__)

SYSTEM = """You are a football analyst scoring Turkish Süper Lig news articles for a research project.

TASK: Score each article on how strongly it signals a manager change is COMING. Return ONLY JSON.

SCORE SCALE (0–4):
0 = No signal: routine quote, tactics, player news, OR new-manager appointment (change already done)
1 = Mild signal: manager fielding departure questions, reversed rumour, post-dismissal replacement search
2 = Moderate signal: explicit board/media criticism, poor results blamed on manager
3 = Strong signal: fan protests demanding change, named replacement candidates, board meeting reports
4 = Confirmed change: firing/resignation confirmed as happening NOW in this article

CRITICAL RULES:
- "yeni teknik direktör X" / "X is the new coach" / "Who is X?" → score=0 (post-change appointment)
- Resignation reversed/lasted 1 week → score=1 (change did not happen)
- Searching for new coach AFTER previous was fired → score=1
- Score=4 ONLY when the headline itself confirms the departure is happening right now

OUTPUT: return exactly this JSON object, no other text:
{"score": <0-4>, "is_relevant": <true/false>, "reason": "<one sentence in English>"}

EXAMPLES:
"Beşiktaş'ın yeni teknik direktörü Sergen Yalçın" → {"score": 0, "is_relevant": false, "reason": "New manager appointed — post-change article."}
"Fenerbahçe'nin yeni teknik direktörü Domenico Tedesco kimdir?" → {"score": 0, "is_relevant": true, "reason": "Profile of newly appointed manager — post-change."}
"Taraftardan 'Recep Uçar istifa' sesleri!" → {"score": 3, "is_relevant": true, "reason": "Fans demanding manager resignation."}
"Gençlerbirliği Teknik Direktörü Volkan Demirel istifa etti" → {"score": 4, "is_relevant": true, "reason": "Confirmed resignation of head coach."}
"Emre Belözoğlu'ndan hiç beklenmedik karar! istifa etmişti, her şey 1 hafta sürdü..." → {"score": 1, "is_relevant": true, "reason": "Resignation reversed — mild signal."}
"Markus Gisdol'den sonra Kayserispor'un yeni hocası belli oldu mu?" → {"score": 1, "is_relevant": true, "reason": "Replacement search after dismissal — mild signal."}"""

SCALE     = {0: 0.0, 1: 0.25, 2: 0.5, 3: 0.75, 4: 1.0}
USER_TMPL = "Article headline: {title}\nTeam: {team}\nDate: {date}{body}\n\nScore this article."


def call_api(client: groq.Groq, title: str, team: str, date: str, body: str) -> dict:
    body_section = f"\nBody: {body[:800]}" if body else ""
    r = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM},
            {"role": "user",   "content": USER_TMPL.format(title=title, team=team, date=date, body=body_section)},
        ],
        max_tokens=200,
        temperature=0.0,
    )
    raw = r.choices[0].message.content.strip().strip("`").strip()
    if raw.lower().startswith("json"):
        raw = raw[4:].strip()
    return json.loads(raw)


def classify_with_backoff(client: groq.Groq, row: pd.Series, retries: int = 5) -> dict | None:
    body  = str(row.get("body", "")) if row.get("body_available") is True else ""
    delay = 4
    for attempt in range(retries):
        try:
            return call_api(client, row["title"], row["team"], row["date"], body)
        except groq.RateLimitError:
            log.warning("Rate limit — waiting %ds", delay)
            time.sleep(delay)
            delay = min(delay * 2, 60)
        except (json.JSONDecodeError, groq.APIError) as e:
            if attempt == retries - 1:
                log.error("Failed uid=%s: %s", row["news_uid"], e)
                return None
            time.sleep(delay)
            delay *= 2
    return None


def load_done() -> set[str]:
    if not OUT_CSV.exists():
        return set()
    return set(pd.read_csv(OUT_CSV)["news_uid"].astype(str).tolist())


def append_result(row: pd.Series, result: dict) -> None:
    score = int(result.get("score", 0))
    record = {
        "news_uid":    row["news_uid"],
        "team":        row["team"],
        "date":        row["date"],
        "score":       score,
        "score_norm":  SCALE.get(score, 0.0),
        "is_relevant": result.get("is_relevant", False),
        "reason":      result.get("reason", ""),
    }
    pd.DataFrame([record]).to_csv(OUT_CSV, mode="a", header=not OUT_CSV.exists(), index=False)


def prioritise(df: pd.DataFrame) -> pd.DataFrame:
    mgr = pd.read_csv(MANAGERS, parse_dates=["end_date"])
    change_dates = mgr["end_date"].dropna().unique()
    df = df.copy()
    df["_date"]     = pd.to_datetime(df["date"], errors="coerce")
    df["_priority"] = 1
    for change in change_dates:
        mask = (df["_date"] >= change - pd.Timedelta(weeks=4)) & (df["_date"] <= change)
        df.loc[mask, "_priority"] = 0
    return df.sort_values(["_priority", "_date"]).drop(columns=["_date", "_priority"]).reset_index(drop=True)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--all",   action="store_true")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise EnvironmentError("GROQ_API_KEY not set")

    df   = pd.read_csv(ARTICLES)
    done = load_done()
    todo = prioritise(df[~df["news_uid"].astype(str).isin(done)])
    limit = args.limit if args.limit else (None if args.all else DAILY_DEFAULT)
    if limit:
        todo = todo.head(limit)

    log.info("total=%d done=%d to_classify=%d limit=%s", len(df), len(done), len(todo), limit)
    if todo.empty:
        log.info("Nothing to do.")
        return

    client = groq.Groq(api_key=api_key)
    for i, (_, row) in enumerate(todo.iterrows(), 1):
        result = classify_with_backoff(client, row)
        if result is None:
            log.warning("Skipping uid=%s", row["news_uid"])
            continue
        append_result(row, result)
        if i % 100 == 0:
            log.info("Progress: %d / %d", i, len(todo))
        time.sleep(2.1)   # 30 RPM → 2s per request + safety margin

    total = len(pd.read_csv(OUT_CSV)) if OUT_CSV.exists() else 0
    log.info("Done. %d articles classified → %s", total, OUT_CSV)


if __name__ == "__main__":
    main()
