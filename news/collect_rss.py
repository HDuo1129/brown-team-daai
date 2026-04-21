"""
news/collect_rss.py
===================
Collect Turkish Süper Lig manager-related articles from two sources:
  1. Fotomaç RSS (team-specific feeds)          — Turkish tabloid
  2. Google News RSS (team + keyword queries)    — multi-source aggregator

Output: news/articles_raw.csv
  Columns: news_uid, source, team, date, title, url, query

Usage:
    python news/collect_rss.py
    python news/collect_rss.py --season 2025-2026   # default
    python news/collect_rss.py --team Galatasaray   # single team test
"""

import argparse
import csv
import hashlib
import ssl
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).parent.parent
OUT  = Path(__file__).parent / "articles_raw.csv"

# ---------------------------------------------------------------------------
# Team configuration: football_data_name -> Fotomaç slug + Turkish display name
# ---------------------------------------------------------------------------

TEAM_CONFIG = {
    "Alanyaspor":    {"fotomac": "alanyaspor",       "tr_name": "Alanyaspor"},
    "Antalyaspor":   {"fotomac": "antalyaspor",      "tr_name": "Antalyaspor"},
    "Besiktas":      {"fotomac": "besiktas",          "tr_name": "Beşiktaş"},
    "Buyuksehyr":    {"fotomac": "basaksehir",        "tr_name": "Başakşehir"},
    "Eyupspor":      {"fotomac": "eyupspor",          "tr_name": "Eyüpspor"},
    "Fenerbahce":    {"fotomac": "fenerbahce",        "tr_name": "Fenerbahçe"},
    "Galatasaray":   {"fotomac": "galatasaray",       "tr_name": "Galatasaray"},
    "Gaziantep":     {"fotomac": "gaziantep",         "tr_name": "Gaziantep FK"},
    "Genclerbirligi":{"fotomac": "genclerbirligi",    "tr_name": "Gençlerbirliği"},
    "Goztep":        {"fotomac": "goztepe",           "tr_name": "Göztepe"},
    "Karagumruk":    {"fotomac": "fatih-karagumruk",  "tr_name": "Fatih Karagümrük"},
    "Kasimpasa":     {"fotomac": "kasimpasa",         "tr_name": "Kasımpaşa"},
    "Kayserispor":   {"fotomac": "kayserispor",       "tr_name": "Kayserispor"},
    "Kocaelispor":   {"fotomac": "kocaelispor",       "tr_name": "Kocaelispor"},
    "Konyaspor":     {"fotomac": "konyaspor",         "tr_name": "Konyaspor"},
    "Rizespor":      {"fotomac": "rizespor",          "tr_name": "Çaykur Rizespor"},
    "Samsunspor":    {"fotomac": "samsunspor",        "tr_name": "Samsunspor"},
    "Trabzonspor":   {"fotomac": "trabzonspor",       "tr_name": "Trabzonspor"},
}

# Google News RSS queries per team: (query_string, language_hint)
# Turkish queries catch tabloid rumor language; English catches DS confirmations
def google_queries(tr_name: str, fd_name: str) -> list[tuple[str, str]]:
    return [
        (f"{tr_name} teknik direktör",        "tr"),  # coach, general
        (f"{tr_name} hoca ayrılık",            "tr"),  # informal: coach departure
        (f"{tr_name} teknik direktör istifa",  "tr"),  # resignation
        (f"{tr_name} teknik direktör görevden","tr"),  # removed from post
        (f"{fd_name} manager",                 "en"),  # English coverage
    ]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SSL_CTX = ssl._create_unverified_context()

def fetch_rss(url: str, timeout: int = 10) -> list[ET.Element]:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=SSL_CTX) as r:
            content = r.read()
        if not content.strip():
            return []
        root = ET.fromstring(content)
        return root.findall(".//item")
    except Exception as e:
        print(f"  WARN: could not fetch {url}: {e}")
        return []


def parse_pubdate(raw: str) -> str:
    """Return ISO date YYYY-MM-DD, or '' on failure."""
    if not raw:
        return ""
    try:
        dt = parsedate_to_datetime(raw)
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%d")
    except Exception:
        return ""


def make_uid(source: str, url: str) -> str:
    return hashlib.md5(f"{source}:{url}".encode()).hexdigest()[:12]


def item_to_row(item: ET.Element, source: str, team: str, query: str) -> dict:
    title = item.findtext("title", "").strip()
    url   = item.findtext("link", "").strip()
    pub   = parse_pubdate(item.findtext("pubDate", ""))
    return {
        "news_uid": make_uid(source, url),
        "source":   source,
        "team":     team,
        "date":     pub,
        "title":    title,
        "url":      url,
        "query":    query,
    }

# ---------------------------------------------------------------------------
# Collectors
# ---------------------------------------------------------------------------

def collect_fotomac(team: str, config: dict) -> list[dict]:
    slug = config["fotomac"]
    url  = f"https://www.fotomac.com.tr/rss/{slug}.xml"
    items = fetch_rss(url)
    rows = [item_to_row(i, "fotomac", team, f"fotomac/{slug}") for i in items]
    print(f"  Fotomaç  {team:<18} {len(rows):>3} articles")
    return rows


def collect_google_news(team: str, config: dict) -> list[dict]:
    tr_name = config["tr_name"]
    rows = []
    for query, lang in google_queries(tr_name, team):
        q   = urllib.parse.quote(query)
        gl  = "TR" if lang == "tr" else "US"
        ceid = f"{gl}:{lang}"
        url  = f"https://news.google.com/rss/search?q={q}&hl={lang}&gl={gl}&ceid={ceid}"
        items = fetch_rss(url)
        for i in items:
            rows.append(item_to_row(i, "google_news", team, query))
        time.sleep(0.3)  # be polite to Google
    # deduplicate by uid within this team
    seen, deduped = set(), []
    for r in rows:
        if r["news_uid"] not in seen:
            seen.add(r["news_uid"])
            deduped.append(r)
    print(f"  Google   {team:<18} {len(deduped):>3} articles ({len(rows)-len(deduped)} dupes removed)")
    return deduped

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def collect(teams: list[str], season: str) -> list[dict]:
    all_rows = []
    total_teams = len(teams)
    for idx, team in enumerate(teams, 1):
        config = TEAM_CONFIG[team]
        print(f"\n[{idx}/{total_teams}] {team}")
        all_rows.extend(collect_fotomac(team, config))
        all_rows.extend(collect_google_news(team, config))

    # Deduplicate across teams (same article can appear in multiple feeds)
    seen, deduped = set(), []
    for r in all_rows:
        if r["news_uid"] not in seen:
            seen.add(r["news_uid"])
            deduped.append(r)

    return deduped


def main():
    parser = argparse.ArgumentParser(description="Collect Süper Lig manager news via RSS")
    parser.add_argument("--season", default="2025-2026", help="Season label (informational)")
    parser.add_argument("--team",   default=None,        help="Single team name to test")
    args = parser.parse_args()

    teams = [args.team] if args.team else list(TEAM_CONFIG.keys())
    print(f"Collecting news for season {args.season} — {len(teams)} team(s)")
    print(f"Sources: Fotomaç RSS + Google News RSS")
    print(f"Output:  {OUT}\n")

    rows = collect(teams, args.season)

    # Sort by team then date
    rows.sort(key=lambda r: (r["team"], r["date"] or ""))

    fieldnames = ["news_uid", "source", "team", "date", "title", "url", "query"]
    OUT.parent.mkdir(exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\n{'='*50}")
    print(f"Total articles collected: {len(rows)}")
    from collections import Counter
    by_source = Counter(r["source"] for r in rows)
    for src, n in by_source.most_common():
        print(f"  {src:<15} {n:>4} articles")
    print(f"Saved → {OUT}")


if __name__ == "__main__":
    main()
