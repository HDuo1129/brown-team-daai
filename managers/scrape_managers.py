"""
scrape_managers.py
==================
Scrapes managerial history for all Turkey Süper Lig clubs from Transfermarkt
and outputs a CSV that can be joined to the match-level data in ../data/.

Output schema (managers.csv)
-----------------------------
football_data_name   : club name as used in football-data.co.uk files
transfermarkt_name   : official name on Transfermarkt
manager              : manager full name
nationality          : manager nationality
start_date           : appointment date (YYYY-MM-DD)
end_date             : departure date  (YYYY-MM-DD, or '' if still in charge)

Join to match data
------------------
For each match row, find the manager who was in charge of each team on
that match date:

    match_date = pd.to_datetime(match_row['Date'], dayfirst=True)
    home_mgr = managers[
        (managers['football_data_name'] == match_row['HomeTeam']) &
        (managers['start_date'] <= match_date) &
        ((managers['end_date'] >= match_date) | managers['end_date'].isna())
    ]

Usage
-----
    pip install requests beautifulsoup4 pandas
    python scrape_managers.py

Transfermarkt blocks many automated requests. If you get 403 errors:
  - Add a longer delay (DELAY_SECONDS)
  - Run with --limit N to scrape only the first N clubs for testing
  - Clubs with NEEDS_MANUAL in their ID are skipped automatically
"""

import csv
import ssl
import time
import urllib.request
import argparse
from datetime import datetime
from pathlib import Path

try:
    from bs4 import BeautifulSoup
except ImportError:
    raise SystemExit("Install beautifulsoup4 first:  pip install beautifulsoup4")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
MAPPING_FILE = Path(__file__).parent / "team_mapping.csv"
OUTPUT_FILE  = Path(__file__).parent / "managers.csv"
DELAY_SECONDS = 4          # polite crawl delay between requests
TM_BASE_URL   = "https://www.transfermarkt.com"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# SSL context that tolerates sites with missing intermediate certs
SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE

OUTPUT_COLUMNS = [
    "football_data_name",
    "transfermarkt_name",
    "manager",
    "nationality",
    "start_date",
    "end_date",
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_mapping(path: Path) -> list[dict]:
    """Load team_mapping.csv and filter out clubs with no TM ID."""
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    valid = [r for r in rows if r["transfermarkt_id"] not in ("", "NEEDS_MANUAL")]
    skipped = [r["football_data_name"] for r in rows if r["transfermarkt_id"] in ("", "NEEDS_MANUAL")]
    if skipped:
        print(f"  Skipping {len(skipped)} clubs with no TM profile: {skipped}")
    return valid


def fetch_page(url: str) -> str | None:
    """Fetch a URL and return the HTML as a string, or None on failure."""
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, context=SSL_CTX, timeout=20) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception as exc:
        print(f"    FETCH ERROR {url}: {exc}")
        return None


def parse_date(raw: str) -> str:
    """
    Convert Transfermarkt date strings to YYYY-MM-DD.
    Formats seen: 'Jan 1, 2020', '01/01/2020', 'Jan 2020', '2020'
    Returns '' if unparseable.
    """
    raw = raw.strip()
    if not raw or raw in ("-", "–", "?", "N/A"):
        return ""
    for fmt in ("%b %d, %Y", "%d/%m/%Y", "%m/%d/%Y", "%b %Y", "%Y"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    # Last resort: return as-is
    return raw


def parse_manager_table(html: str, football_data_name: str, tm_name: str) -> list[dict]:
    """
    Parse the Transfermarkt /trainer/verein/ page and extract coaching stints.
    Returns a list of record dicts.
    """
    soup = BeautifulSoup(html, "html.parser")
    records = []

    # The coaching history table has class "items" on Transfermarkt
    table = soup.find("table", class_="items")
    if not table:
        # Try any table containing "trainer" rows
        tables = soup.find_all("table")
        for t in tables:
            if t.find("tr") and len(t.find_all("tr")) > 2:
                table = t
                break

    if not table:
        print(f"    WARNING: no manager table found for {football_data_name}")
        return records

    rows = table.find_all("tr")
    for row in rows:
        cells = row.find_all("td")
        if len(cells) < 3:
            continue

        # Extract manager name (usually in a link or the 2nd/3rd cell)
        manager_name = ""
        nationality  = ""
        start_date   = ""
        end_date     = ""

        # Cell layout varies; try to find the name anchor
        for cell in cells:
            link = cell.find("a", href=lambda h: h and "/trainer/" in h)
            if link:
                manager_name = link.get_text(strip=True)
                break

        if not manager_name:
            # Fallback: grab text from the first non-empty, non-icon cell
            texts = [c.get_text(strip=True) for c in cells if c.get_text(strip=True)]
            manager_name = texts[0] if texts else ""

        # Nationality flag img alt text
        flag = row.find("img", class_=lambda c: c and "flagge" in c)
        if flag:
            nationality = flag.get("title", flag.get("alt", "")).strip()

        # Dates — look for cells whose text looks like a date
        date_cells = []
        for cell in cells:
            text = cell.get_text(strip=True)
            # Simple heuristic: contains digits and slash or comma
            if any(ch.isdigit() for ch in text) and (
                "/" in text or "," in text or len(text) == 4
            ):
                date_cells.append(text)

        if len(date_cells) >= 2:
            start_date = parse_date(date_cells[0])
            end_date   = parse_date(date_cells[1])
        elif len(date_cells) == 1:
            start_date = parse_date(date_cells[0])

        if manager_name:
            records.append({
                "football_data_name": football_data_name,
                "transfermarkt_name": tm_name,
                "manager":            manager_name,
                "nationality":        nationality,
                "start_date":         start_date,
                "end_date":           end_date,
            })

    return records


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Scrape manager history from Transfermarkt.")
    parser.add_argument("--limit", type=int, default=None,
                        help="Scrape only the first N clubs (useful for testing).")
    parser.add_argument("--delay", type=float, default=DELAY_SECONDS,
                        help=f"Seconds to wait between requests (default: {DELAY_SECONDS}).")
    args = parser.parse_args()

    clubs = load_mapping(MAPPING_FILE)
    if args.limit:
        clubs = clubs[: args.limit]

    all_records: list[dict] = []
    total = len(clubs)

    for i, club in enumerate(clubs, 1):
        fd_name = club["football_data_name"]
        tm_name = club["transfermarkt_name"]
        url     = club["transfermarkt_trainer_url"]

        print(f"[{i}/{total}] {fd_name}  →  {url}")

        html = fetch_page(url)
        if html is None:
            print(f"    Skipped (fetch failed).")
            time.sleep(args.delay)
            continue

        records = parse_manager_table(html, fd_name, tm_name)
        print(f"    Found {len(records)} coaching stints.")
        all_records.extend(records)

        if i < total:
            time.sleep(args.delay)

    # Write output
    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(all_records)

    print(f"\nDone. {len(all_records)} total records written to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
