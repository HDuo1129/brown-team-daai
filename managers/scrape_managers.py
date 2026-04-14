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
For each match row, find the manager in charge of each team on the match date:

    match_date = pd.to_datetime(match_row['Date'], dayfirst=True)
    home_mgr = managers[
        (managers['football_data_name'] == match_row['HomeTeam']) &
        (managers['start_date'] <= match_date) &
        ((managers['end_date'] >= match_date) | managers['end_date'].isna())
    ]

Usage
-----
    pip install beautifulsoup4
    python scrape_managers.py              # full run (~60 clubs, 4 s delay)
    python scrape_managers.py --limit 5    # test with first 5 clubs
    python scrape_managers.py --delay 6    # slower crawl if you hit 403s
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
DELAY_SECONDS = 4

# Correct URL pattern confirmed working: slug is ignored, only ID matters
TM_URL_TEMPLATE = (
    "https://www.transfermarkt.com/x/mitarbeiterhistorie/verein/{id}/mitarbeitertyp/trainer"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

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
    with open(path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    valid   = [r for r in rows if r["transfermarkt_id"] not in ("", "NEEDS_MANUAL")]
    skipped = [r["football_data_name"] for r in rows if r["transfermarkt_id"] in ("", "NEEDS_MANUAL")]
    # De-duplicate: same TM id can appear under two football-data names (e.g. Ankaraspor/Osmanlispor)
    # Keep all entries — we want both name variants to map correctly
    if skipped:
        print(f"Skipping {len(skipped)} clubs with no TM profile: {skipped}\n")
    return valid


def fetch_html(url: str) -> str | None:
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, context=SSL_CTX, timeout=20) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception as exc:
        print(f"    FETCH ERROR: {exc}")
        return None


def parse_date(raw: str) -> str:
    """Convert DD/MM/YYYY (Transfermarkt default) to YYYY-MM-DD. Returns '' if empty."""
    raw = raw.strip()
    if not raw:
        return ""
    for fmt in ("%d/%m/%Y", "%m/%d/%Y", "%b %d, %Y", "%b %Y", "%Y"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return raw  # return as-is if unrecognised


def scrape_club(tm_id: str, fd_name: str, tm_name: str) -> list[dict]:
    """
    Fetch the Transfermarkt manager history page for one club and return
    a list of coaching-stint dicts.

    Page structure (confirmed):
      <table class="items">
        <tbody>
          <tr class="odd|even">
            <td>                        ← col 0: manager info (inline table)
              <a class="hauptlink">Name</a>
            </td>
            <td class="zentriert">      ← col 1: nationality flag img
              <img title="Nationality" />
            </td>
            <td class="zentriert">      ← col 2: start date  (DD/MM/YYYY)
            <td class="zentriert">      ← col 3: end date    (DD/MM/YYYY or empty)
            ...
          </tr>
        </tbody>
      </table>
    """
    url  = TM_URL_TEMPLATE.format(id=tm_id)
    html = fetch_html(url)
    if html is None:
        return []

    soup    = BeautifulSoup(html, "html.parser")
    table   = soup.find("table", class_="items")
    records = []

    if not table:
        print(f"    WARNING: no <table class='items'> found")
        return records

    for row in table.select("tr.odd, tr.even"):
        cells = row.find_all("td", recursive=False)
        if len(cells) < 4:
            continue

        # --- Manager name (col 0) ---
        # On TM, class="hauptlink" is on the <td>, not the <a>
        # Find the <a> inside a <td class="hauptlink">
        name_td  = cells[0].find("td", class_="hauptlink")
        name_tag = name_td.find("a") if name_td else None
        # Fallback: any <a> linking to a trainer profile
        if not name_tag:
            name_tag = cells[0].find("a", href=lambda h: h and "/profil/trainer/" in h)
        if not name_tag:
            continue
        manager = name_tag.get_text(strip=True)

        # --- Nationality (col 1) ---
        flag    = cells[1].find("img")
        nationality = flag.get("title", "").strip() if flag else ""

        # --- Dates (cols 2 and 3) ---
        start_date = parse_date(cells[2].get_text(strip=True))
        end_date   = parse_date(cells[3].get_text(strip=True))

        records.append({
            "football_data_name": fd_name,
            "transfermarkt_name": tm_name,
            "manager":            manager,
            "nationality":        nationality,
            "start_date":         start_date,
            "end_date":           end_date,
        })

    return records


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None,
                        help="Only scrape the first N clubs (for testing).")
    parser.add_argument("--delay", type=float, default=DELAY_SECONDS,
                        help=f"Seconds between requests (default {DELAY_SECONDS}).")
    args = parser.parse_args()

    clubs = load_mapping(MAPPING_FILE)
    if args.limit:
        clubs = clubs[: args.limit]

    all_records: list[dict] = []
    total = len(clubs)

    for i, club in enumerate(clubs, 1):
        fd_name = club["football_data_name"]
        tm_name = club["transfermarkt_name"]
        tm_id   = club["transfermarkt_id"]

        print(f"[{i}/{total}] {fd_name} (TM id={tm_id})")
        records = scrape_club(tm_id, fd_name, tm_name)
        print(f"    {len(records)} coaching stints")
        all_records.extend(records)

        if i < total:
            time.sleep(args.delay)

    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(all_records)

    print(f"\nDone — {len(all_records)} records written to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
