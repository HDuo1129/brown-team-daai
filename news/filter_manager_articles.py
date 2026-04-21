"""
news/filter_manager_articles.py
================================
Filter articles_raw.csv to keep only articles that contain
manager-related information for the 2025-26 season.

Two-pass filter:
  1. Name match  — article title mentions a manager from our stints list
  2. Keyword match — article contains Turkish/English manager change keywords

Output: news/articles_managers.csv
  Same columns as articles_raw.csv, plus:
    matched_manager  — manager name detected (or '' if keyword-only match)
    match_type       — 'name' | 'keyword' | 'name+keyword'

Usage:
    python news/filter_manager_articles.py
"""

import re
import csv
import unicodedata
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).parent.parent
SEASON_START = '2025-07-01'
SEASON_END   = '2026-06-30'

# ---------------------------------------------------------------------------
# 1. Build manager name lookup from stints
# ---------------------------------------------------------------------------

def strip_accents(s: str) -> str:
    """Normalize accented characters for fuzzy matching."""
    return unicodedata.normalize('NFD', s).encode('ascii', 'ignore').decode('utf-8').lower()


def name_tokens(full_name: str) -> list[str]:
    """Return last name + full name as search tokens (both accented and stripped)."""
    parts = full_name.strip().split()
    tokens = set()
    tokens.add(full_name.strip())           # full name
    if len(parts) >= 2:
        tokens.add(parts[-1])               # last name only
        tokens.add(parts[0])                # first name only (for single-name coaches)
    # Also add accent-stripped versions
    stripped = {strip_accents(t) for t in tokens}
    return list(tokens | stripped)


def build_manager_lookup() -> dict[str, list[tuple[str, str, str, str]]]:
    """
    Returns: {football_data_name: [(manager, start_date, end_date, token), ...]}
    """
    mgr = pd.read_csv(ROOT / 'managers' / 'managers.csv')
    mgr['start'] = pd.to_datetime(mgr['start_date'], errors='coerce')
    mgr['end_fill'] = pd.to_datetime(mgr['end_date'], errors='coerce').fillna(pd.Timestamp('2026-12-31'))

    current_teams = [
        'Alanyaspor','Antalyaspor','Besiktas','Buyuksehyr','Eyupspor',
        'Fenerbahce','Galatasaray','Gaziantep','Genclerbirligi','Goztep',
        'Karagumruk','Kasimpasa','Kayserispor','Kocaelispor','Konyaspor',
        'Rizespor','Samsunspor','Trabzonspor'
    ]

    season_mgrs = mgr[
        (mgr['football_data_name'].isin(current_teams)) &
        (mgr['start'] <= pd.Timestamp(SEASON_END)) &
        (mgr['end_fill'] >= pd.Timestamp(SEASON_START))
    ]

    # Build a flat list: (manager_name, token) for name matching
    all_entries = []
    for _, row in season_mgrs.iterrows():
        name = str(row['manager'])
        for token in name_tokens(name):
            if len(token) >= 4:  # skip very short tokens (e.g. "Ak")
                all_entries.append((
                    row['football_data_name'],
                    name,
                    str(row['start_date']),
                    str(row['end_date']) if pd.notna(row['end_date']) else '',
                    token
                ))
    return all_entries


# ---------------------------------------------------------------------------
# 2. Manager change keywords
# ---------------------------------------------------------------------------

# Turkish and English keywords that signal manager-related content
MANAGER_KEYWORDS = [
    # Turkish — role
    'teknik direktör', 'teknik direktor', 'teknik yönetici',
    'antrenör', 'hoca',
    # Turkish — change events
    'ayrılık', 'ayrilik', 'istifa', 'görevden', 'gorevden',
    'sözleşme fesih', 'sozlesme fesih', 'feshedildi',
    'görevine son', 'koltuğunu', 'kovuldu', 'ihraç',
    'yeni hoca', 'yeni teknik direktör',
    # Turkish — pressure signals
    'baskı altında', 'koltuğu sallantıda', 'koltugu sallantida',
    'mevkisi tehlikede', 'görevini bırak',
    # English
    'manager sacked', 'coach sacked', 'fired', 'dismissed',
    'new manager', 'new coach', 'appointed', 'resignation',
    'managerial change', 'under pressure',
]

# Compile into a single regex (case-insensitive)
_KW_PATTERN = re.compile(
    '|'.join(re.escape(kw) for kw in MANAGER_KEYWORDS),
    re.IGNORECASE
)

def has_keyword(text: str) -> bool:
    return bool(_KW_PATTERN.search(text))


# ---------------------------------------------------------------------------
# 3. Filter
# ---------------------------------------------------------------------------

def classify_article(title: str, url: str, team: str,
                     mgr_entries: list) -> tuple[str, str]:
    """
    Returns (matched_manager, match_type) where match_type is
    'name', 'keyword', 'name+keyword', or '' (no match).
    """
    text = (title + ' ' + url).lower()
    text_stripped = strip_accents(text)

    # Name match: check if any manager token appears in the text
    matched = set()
    for fd_name, mgr_name, start, end, token in mgr_entries:
        if fd_name != team:
            continue
        tok_lower = token.lower()
        if tok_lower in text or tok_lower in text_stripped:
            matched.add(mgr_name)

    name_hit = bool(matched)
    kw_hit   = has_keyword(title)  # check title only for keyword (more precise)

    if name_hit and kw_hit:
        return ', '.join(sorted(matched)), 'name+keyword'
    elif name_hit:
        return ', '.join(sorted(matched)), 'name'
    elif kw_hit:
        return '', 'keyword'
    else:
        return '', ''


def main():
    articles = pd.read_csv(ROOT / 'news' / 'articles_raw.csv')
    # Filter to season window
    articles_season = articles[
        (articles['date'] >= SEASON_START) &
        (articles['date'] <= SEASON_END)
    ].copy()

    print(f"Input:  {len(articles_season):,} articles (season window)")

    mgr_entries = build_manager_lookup()
    unique_managers = len({e[1] for e in mgr_entries})
    print(f"Managers in lookup: {unique_managers} ({len(mgr_entries)} name tokens)")

    # Apply filter
    results = []
    for _, row in articles_season.iterrows():
        matched_mgr, match_type = classify_article(
            str(row.get('title', '')),
            str(row.get('url', '')),
            row['team'],
            mgr_entries
        )
        if match_type:
            r = row.to_dict()
            r['matched_manager'] = matched_mgr
            r['match_type'] = match_type
            results.append(r)

    out = pd.DataFrame(results)
    out = out.sort_values(['team', 'date'])

    # Save
    out_path = ROOT / 'news' / 'articles_managers.csv'
    out.to_csv(out_path, index=False, encoding='utf-8')

    # Summary
    print(f"\nOutput: {len(out):,} articles retained ({len(out)/len(articles_season)*100:.1f}%)")
    print(f"\nBy match type:")
    for mt, grp in out.groupby('match_type'):
        print(f"  {mt:<15} {len(grp):>5}")

    print(f"\nBy team:")
    by_team = out.groupby('team').agg(
        total=('news_uid','count'),
        name_matches=('match_type', lambda x: (x.isin(['name','name+keyword'])).sum()),
        kw_only=('match_type', lambda x: (x=='keyword').sum()),
    ).sort_values('total', ascending=False)
    print(by_team.to_string())

    print(f"\nSaved → {out_path}")


if __name__ == '__main__':
    main()
