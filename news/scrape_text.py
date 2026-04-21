"""
news/scrape_text.py
====================
Scrape full article text for manager-related articles.

Strategy:
  - Fotomaç URLs  → direct fetch + trafilatura extract (full body)
  - Google News URLs → try to resolve to source article via requests;
                       fall back to title-only if blocked

Output: news/articles_text.csv
  Columns: news_uid, source, team, date, title, url, actual_url,
           body, lead, body_available, fetch_status

Usage:
    python news/scrape_text.py               # all articles
    python news/scrape_text.py --limit 50    # test run
    python news/scrape_text.py --team Galatasaray
"""

import argparse
import csv
import re
import ssl
import time
import warnings
from pathlib import Path

import requests
import trafilatura
import pandas as pd

warnings.filterwarnings('ignore', message='Unverified HTTPS')

ROOT    = Path(__file__).parent.parent
IN_FILE = ROOT / 'news' / 'articles_managers.csv'
OUT_FILE= ROOT / 'news' / 'articles_text.csv'

# ---------------------------------------------------------------------------
# HTTP session
# ---------------------------------------------------------------------------

SESSION = requests.Session()
SESSION.verify = False
SESSION.headers.update({
    'User-Agent': (
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/122.0.0.0 Safari/537.36'
    ),
    'Accept-Language': 'tr-TR,tr;q=0.9,en;q=0.8',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
})

# Sources that block scraping (return stub pages / paywalls)
BLOCKED_DOMAINS = {
    'milliyet.com.tr', 'sabah.com.tr', 'hurriyet.com.tr',
    'dha.com.tr', 'aa.com.tr',
}

def domain(url: str) -> str:
    m = re.search(r'https?://(?:www\.)?([^/]+)', url)
    return m.group(1).lower() if m else ''


# ---------------------------------------------------------------------------
# Fetch helpers
# ---------------------------------------------------------------------------

def fetch_html(url: str, timeout: int = 12) -> tuple[str, str]:
    """
    Returns (actual_url, html). actual_url may differ from url after redirects.
    Returns ('', '') on failure.
    """
    try:
        r = SESSION.get(url, timeout=timeout, allow_redirects=True)
        if r.status_code == 200 and 'text/html' in r.headers.get('Content-Type', ''):
            return r.url, r.text
        return r.url, ''
    except Exception:
        return url, ''


def resolve_google_news(gn_url: str) -> tuple[str, str]:
    """
    Try to resolve a Google News redirect to the real article.
    Returns (actual_url, html) or (gn_url, '') if blocked.
    """
    actual_url, html = fetch_html(gn_url)
    # If we ended up at consent.google.com or still on news.google.com → failed
    if 'consent.google.com' in actual_url or 'news.google.com' in actual_url:
        return gn_url, ''
    return actual_url, html


def extract_text(html: str) -> tuple[str, str]:
    """
    Returns (body, lead) using trafilatura.
    lead = first non-empty paragraph of body (≤ 300 chars).
    """
    if not html:
        return '', ''
    text = trafilatura.extract(
        html,
        include_comments=False,
        include_tables=False,
        no_fallback=False,
    ) or ''
    text = text.strip()
    # Lead = first paragraph
    paragraphs = [p.strip() for p in text.split('\n') if p.strip()]
    lead = paragraphs[0][:300] if paragraphs else ''
    return text, lead


# ---------------------------------------------------------------------------
# Main scraper
# ---------------------------------------------------------------------------

def scrape(df: pd.DataFrame) -> list[dict]:
    results   = []
    n         = len(df)
    fotomac   = df[df['source'] == 'fotomac']
    gnews     = df[df['source'] == 'google_news']

    print(f"  Fotomaç:     {len(fotomac):,} articles (direct scrape)")
    print(f"  Google News: {len(gnews):,} articles (resolve + fallback)")
    print()

    for idx, (_, row) in enumerate(df.iterrows(), 1):
        url    = str(row['url'])
        src    = row['source']
        result = {
            'news_uid':       row['news_uid'],
            'source':         src,
            'team':           row['team'],
            'date':           row['date'],
            'title':          row['title'],
            'url':            url,
            'actual_url':     url,
            'matched_manager':row.get('matched_manager', ''),
            'match_type':     row.get('match_type', ''),
            'body':           '',
            'lead':           '',
            'body_available': False,
            'fetch_status':   'pending',
        }

        # ── Fotomaç ────────────────────────────────────────────────────────
        if src == 'fotomac':
            actual_url, html = fetch_html(url)
            result['actual_url'] = actual_url
            if html:
                body, lead = extract_text(html)
                if body:
                    result.update(body=body, lead=lead,
                                  body_available=True, fetch_status='ok')
                else:
                    result['fetch_status'] = 'extract_failed'
            else:
                result['fetch_status'] = 'fetch_failed'
            time.sleep(0.4)

        # ── Google News ────────────────────────────────────────────────────
        # Google News redirects through a consent page — cannot follow server-side.
        # Use title as text (title carries the key scoring signal for the LLM).
        else:
            title_text = str(row.get('title', ''))
            # Strip " - SourceName" suffix so only headline text goes to the LLM
            clean_title = re.sub(r'\s+-\s+[^-]{2,40}$', '', title_text).strip()
            result.update(
                body=clean_title,
                lead=clean_title,
                body_available=False,
                fetch_status='title_only',
            )

        results.append(result)

        # Progress log every 50
        if idx % 50 == 0 or idx == n:
            ok  = sum(1 for r in results if r['body_available'])
            pct = ok / len(results) * 100
            print(f"  [{idx:>4}/{n}]  body_available: {ok}/{len(results)} ({pct:.0f}%)")

    return results


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit', type=int, default=None, help='Max articles (test mode)')
    parser.add_argument('--team',  default=None,           help='Single team only')
    args = parser.parse_args()

    df = pd.read_csv(IN_FILE)
    if args.team:
        df = df[df['team'] == args.team]
    if args.limit:
        df = df.head(args.limit)

    print(f"Scraping {len(df):,} articles → {OUT_FILE.name}\n")

    rows = scrape(df)

    out = pd.DataFrame(rows)
    out.to_csv(OUT_FILE, index=False, encoding='utf-8')

    # Summary
    ok       = out['body_available'].sum()
    statuses = out['fetch_status'].value_counts()
    body_len = out.loc[out['body_available'], 'body'].str.len()

    print(f"\n{'='*50}")
    print(f"Total scraped:    {len(out):,}")
    print(f"body_available:   {ok:,} ({ok/len(out)*100:.1f}%)")
    print(f"\nFetch status breakdown:")
    print(statuses.to_string())
    if len(body_len):
        print(f"\nBody length (chars):")
        print(f"  median: {body_len.median():.0f}")
        print(f"  mean:   {body_len.mean():.0f}")
        print(f"  min:    {body_len.min():.0f}")
        print(f"  max:    {body_len.max():.0f}")
    print(f"\nSaved → {OUT_FILE}")


if __name__ == '__main__':
    main()
