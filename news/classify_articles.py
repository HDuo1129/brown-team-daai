"""
news/classify_articles.py
==========================
Classify all articles in articles_text.csv using the validated LLM prompt.
Outputs:
  news/articles_classified.csv  — one row per article with score, is_relevant, reason, score_pct
  news/expectations.csv         — one row per (team, gameweek) with avg_score, n_articles

Usage:
    export ANTHROPIC_API_KEY=sk-ant-...
    python news/classify_articles.py               # all articles
    python news/classify_articles.py --limit 50    # test run
    python news/classify_articles.py --team Galatasaray
    python news/classify_articles.py --resume      # skip already-classified rows
"""

import argparse
import json
import os
import re
import time
from pathlib import Path

import anthropic
import pandas as pd

ROOT     = Path(__file__).parent.parent
IN_FILE  = ROOT / 'news' / 'articles_text.csv'
OUT_FILE = ROOT / 'news' / 'articles_classified.csv'
EXP_FILE = ROOT / 'news' / 'expectations.csv'

SAVE_EVERY = 100   # checkpoint to disk every N articles

# ---------------------------------------------------------------------------
# Validated prompt (matches classify_validate.py)
# ---------------------------------------------------------------------------

SYSTEM = """You are a football analyst scoring Turkish Süper Lig news articles for a research project.
Your task: assess how strongly each article signals that a manager change is IMMINENT or HAS JUST BEEN CONFIRMED (firing or resignation only).

SCORING SCALE:
0 = No signal: routine post-match quote, tactical discussion, player transfer, OR new-manager appointment article (change already happened — post-change period, not a pre-change signal)
1 = Mild signal: manager asked about his future, brief/unresolved departure rumours, speculation about replacement after a previous manager already left
2 = Moderate signal: explicit criticism of manager, poor results blamed on him, board dissatisfaction mentioned
3 = Strong signal: fans publicly demanding change (protests, chants), credible reports of board meeting about the manager, named replacement candidates
4 = Confirmed change: firing, resignation, or mutual termination explicitly stated

CRITICAL RULE — APPOINTMENTS SCORE 0:
Articles that announce WHO the new manager is ("X is the new coach", "who is X?", "X appointed") must receive score=0.
These describe the post-change period. Score 4 is ONLY for firing/resignation articles, never for appointment articles.

is_relevant — INDEPENDENT of score. Use these distinctions:
- true: manager's job security, pressure, departure, firing/resignation; OR "who is the new manager?" profile articles; OR articles asking/speculating whether a new coach has been decided; OR manager answering questions about his own future
- false: ONLY articles with no manager-change connection at all — player transfers, match tactics, cup draws, match results with zero managerial angle; OR brief one-line appointment announcements ("X is the new coach" with no further content)

THREE APPOINTMENT CASES — distinguish carefully:
1. "X is the new coach" (pure statement) → score=0, is_relevant=false (no content beyond the fact)
2. "Who is X? / What will X bring?" (new-manager profile) → score=0, is_relevant=true (manager-focused content)
3. "Has the new coach been decided yet? / Will X be appointed?" (question/speculation) → score=1, is_relevant=true (still in the expectation window, change not yet confirmed)

Return ONLY a single JSON object — no markdown, no extra text:
{"score": <0-4>, "is_relevant": <true|false>, "reason": "<one sentence in English>"}"""


def build_user_prompt(title: str, team: str, date: str, body: str = "") -> str:
    if body and body.strip():
        text_section = f"Article headline: {title}\nArticle body:\n{body.strip()[:1500]}"
    else:
        text_section = f"Article headline: {title}"
    return f"""{text_section}
Team: {team}
Date: {date}

Score this article for manager-change expectation signal."""


# ---------------------------------------------------------------------------
# API call (with retry on rate-limit)
# ---------------------------------------------------------------------------

def classify(client: anthropic.Anthropic, title: str, team: str,
             date: str, body: str = "", retries: int = 3) -> dict:
    for attempt in range(retries):
        try:
            msg = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=150,
                system=SYSTEM,
                messages=[{"role": "user", "content": build_user_prompt(title, team, date, body)}],
            )
            raw = msg.content[0].text.strip()
            match = re.search(r'\{.*?\}', raw, re.DOTALL)
            if match:
                return json.loads(match.group())
            return json.loads(raw)
        except anthropic.RateLimitError:
            wait = 30 * (attempt + 1)
            print(f"  Rate limit — waiting {wait}s...")
            time.sleep(wait)
        except Exception as e:
            if attempt == retries - 1:
                raise
            time.sleep(5)
    raise RuntimeError("Max retries exceeded")


# ---------------------------------------------------------------------------
# Main classification loop
# ---------------------------------------------------------------------------

def run_classification(df: pd.DataFrame, client: anthropic.Anthropic,
                       existing_uids: set) -> list[dict]:
    results = []
    todo = df[~df['news_uid'].isin(existing_uids)]
    n = len(todo)

    if n == 0:
        print("All articles already classified.")
        return results

    print(f"Classifying {n:,} articles (skipping {len(existing_uids):,} already done)...\n")

    for i, (_, row) in enumerate(todo.iterrows(), 1):
        title = str(row.get('title', ''))
        team  = str(row.get('team', ''))
        date  = str(row.get('date', ''))
        body  = str(row.get('body', '')) if row.get('body_available') else ''

        try:
            out       = classify(client, title, team, date, body)
            score     = int(out.get('score', -1))
            is_rel    = bool(out.get('is_relevant', False))
            reason    = str(out.get('reason', ''))
            score_pct = score * 25  # 0→0%, 1→25%, 2→50%, 3→75%, 4→100%
        except Exception as e:
            print(f"  ERROR [{row['news_uid']}] {title[:50]}: {e}")
            score, is_rel, reason, score_pct = -1, False, f"ERROR: {e}", -1

        results.append({
            'news_uid':    row['news_uid'],
            'source':      row.get('source', ''),
            'team':        team,
            'date':        date,
            'title':       title,
            'score':       score,
            'is_relevant': is_rel,
            'reason':      reason,
            'score_pct':   score_pct,
            'used_body':   bool(body),
        })

        # Progress log
        if i % 50 == 0 or i == n:
            done_ok = sum(1 for r in results if r['score'] >= 0)
            print(f"  [{i:>4}/{n}]  classified: {done_ok}/{i}  errors: {i - done_ok}")

        # Checkpoint save
        if i % SAVE_EVERY == 0:
            _checkpoint(results, existing_uids, df)

        time.sleep(0.3)

    return results


def _checkpoint(new_results: list, existing_uids: set, df: pd.DataFrame):
    """Merge new results with any existing classified rows and save."""
    rows = []
    if OUT_FILE.exists() and existing_uids:
        rows = pd.read_csv(OUT_FILE).to_dict('records')
    rows.extend(new_results)
    pd.DataFrame(rows).drop_duplicates('news_uid').to_csv(OUT_FILE, index=False)
    print(f"  [checkpoint] saved {len(rows)} rows → {OUT_FILE.name}")


# ---------------------------------------------------------------------------
# Aggregation: team × gameweek panel
# ---------------------------------------------------------------------------

SCORE_NORM = {0: 0, 1: 25, 2: 50, 3: 75, 4: 100}

def build_expectations(classified: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate to one row per (team, gameweek).
    Gameweek = ISO calendar week (year-Www, e.g. 2025-W32).
    Only uses articles where score >= 0 (no errors).
    """
    df = classified[classified['score'] >= 0].copy()
    df['date'] = pd.to_datetime(df['date'], errors='coerce')
    df = df.dropna(subset=['date'])

    iso = df['date'].dt.isocalendar()
    df['gameweek'] = iso['year'].astype(str) + '-W' + iso['week'].astype(str).str.zfill(2)
    df['week_start'] = df['date'] - pd.to_timedelta(df['date'].dt.dayofweek, unit='D')

    agg = (
        df.groupby(['team', 'gameweek', 'week_start'])
        .agg(
            avg_score     = ('score', 'mean'),
            avg_score_pct = ('score_pct', 'mean'),
            n_articles    = ('news_uid', 'count'),
            n_relevant    = ('is_relevant', 'sum'),
        )
        .reset_index()
        .sort_values(['team', 'week_start'])
    )
    agg['avg_score']     = agg['avg_score'].round(3)
    agg['avg_score_pct'] = agg['avg_score_pct'].round(1)
    return agg


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit',  type=int, default=None, help='Max articles (test mode)')
    parser.add_argument('--team',   default=None,           help='Single team only')
    parser.add_argument('--resume', action='store_true',    help='Skip already-classified articles')
    args = parser.parse_args()

    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        print("ERROR: set ANTHROPIC_API_KEY environment variable")
        return

    client = anthropic.Anthropic(api_key=api_key)

    # Load input
    df = pd.read_csv(IN_FILE)
    if args.team:
        df = df[df['team'] == args.team]
    if args.limit:
        df = df.head(args.limit)

    print(f"Input: {len(df):,} articles from {IN_FILE.name}\n")

    # Resume: find already-classified UIDs
    existing_uids = set()
    if args.resume and OUT_FILE.exists():
        existing = pd.read_csv(OUT_FILE)
        existing_uids = set(existing['news_uid'].dropna())
        print(f"Resume mode: {len(existing_uids):,} articles already classified")

    # Classify
    new_results = run_classification(df, client, existing_uids)

    # Merge with existing and save
    all_rows = []
    if OUT_FILE.exists() and existing_uids:
        all_rows = pd.read_csv(OUT_FILE).to_dict('records')
    all_rows.extend(new_results)

    classified = pd.DataFrame(all_rows).drop_duplicates('news_uid')
    classified.to_csv(OUT_FILE, index=False)

    # Summary
    ok      = classified[classified['score'] >= 0]
    errors  = classified[classified['score'] < 0]
    rel     = ok[ok['is_relevant'] == True]
    print(f"\n{'='*55}")
    print(f"Total classified:   {len(ok):,}  (errors: {len(errors)})")
    print(f"is_relevant=true:   {len(rel):,} ({len(rel)/max(len(ok),1)*100:.1f}%)")
    print(f"\nScore distribution:")
    print(ok['score'].value_counts().sort_index().to_string())
    print(f"\nSaved → {OUT_FILE}")

    # Build expectations panel
    exp = build_expectations(classified)
    exp.to_csv(EXP_FILE, index=False)
    print(f"\nExpectations panel: {len(exp):,} team-gameweek rows")
    print(f"Teams: {exp['team'].nunique()}  |  Gameweeks: {exp['gameweek'].nunique()}")
    print(f"Saved → {EXP_FILE}")


if __name__ == '__main__':
    main()
