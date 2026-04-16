"""
scrape_manager_profiles.py
==========================
For every unique manager in managers.csv, fetches their Transfermarkt
profile page to extract date of birth and full career history as a coach.

Then builds manager_characteristics.csv by joining profile data back to
each stint in managers.csv, computing at the moment of appointment:
  - age_at_appointment   (years)
  - experience_clubs     (# of clubs managed before this stint)
  - experience_games     (# of matches managed before this stint)
  - experience_wins      (# of wins before this stint)
  - experience_winrate   (win % before this stint, rounded 2 dp)
  - experience_years     (years since first management job)

Output files
------------
  managers/manager_profiles.csv        -- one row per unique manager
  managers/manager_characteristics.csv -- managers.csv + characteristics columns

Usage
-----
    pip install beautifulsoup4
    python managers/scrape_manager_profiles.py
    python managers/scrape_manager_profiles.py --delay 4
    python managers/scrape_manager_profiles.py --limit 20   # test
"""

import csv
import ssl
import time
import urllib.request
import argparse
from datetime import datetime, date
from pathlib import Path

try:
    from bs4 import BeautifulSoup
except ImportError:
    raise SystemExit("Install beautifulsoup4 first:  pip install beautifulsoup4")

# ---------------------------------------------------------------------------
STINTS_FILE      = Path(__file__).parent / "managers.csv"
PROFILES_FILE    = Path(__file__).parent / "manager_profiles.csv"
CHARS_FILE       = Path(__file__).parent / "manager_characteristics.csv"
DELAY_SECONDS    = 3

TM_PROFILE_URL   = "https://www.transfermarkt.com/{slug}/profil/trainer/{id}"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode    = ssl.CERT_NONE

PROFILE_COLS = [
    "trainer_id", "trainer_slug", "manager", "nationality",
    "date_of_birth", "place_of_birth", "citizenship",
]

CHARS_COLS = [
    "football_data_name", "transfermarkt_name",
    "manager", "trainer_id", "nationality",
    "date_of_birth",
    "start_date", "end_date",
    "age_at_appointment",
    "experience_clubs_before",
    "experience_years_before",
]

# ---------------------------------------------------------------------------

def fetch_html(url: str) -> str | None:
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, context=SSL_CTX, timeout=20) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception as exc:
        print(f"    FETCH ERROR: {exc}")
        return None


def parse_date(raw: str) -> date | None:
    raw = raw.strip()
    if not raw:
        return None
    # Transfermarkt profile pages show birth date as e.g. "Oct 19, 1973"
    for fmt in ("%b %d, %Y", "%d/%m/%Y", "%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def date_to_str(d: date | None) -> str:
    return d.strftime("%Y-%m-%d") if d else ""


def years_between(d1: date, d2: date) -> float:
    return (d2 - d1).days / 365.25


# ---------------------------------------------------------------------------
# Profile scraping
# ---------------------------------------------------------------------------

def scrape_profile(trainer_id: str, trainer_slug: str) -> dict:
    """
    Scrape a manager's Transfermarkt profile page.

    Confirmed page structure:
      Personal info — table.auflistung:
        "Date of birth/Age:"  → "04/09/1953 (72)"   strip the (age)
        "Place of Birth:"     → city string
        "Citizenship:"        → country string

      Career history — table.items (rows have NO odd/even class):
        Col 0: club badge (img)
        Col 1: "ClubName Role"  text
        Col 2: "SS/SS (DD/MM/YYYY)"  appointment date inside parens
        Col 3: "SS/SS (DD/MM/YYYY)"  end date inside parens (empty if current)

    Returns a dict with dob and career list [{from_date, to_date}].
    """
    import re as _re

    url  = TM_PROFILE_URL.format(slug=trainer_slug or "x", id=trainer_id)
    html = fetch_html(url)
    if html is None:
        return {}

    soup = BeautifulSoup(html, "html.parser")

    profile: dict = {
        "trainer_id":     trainer_id,
        "trainer_slug":   trainer_slug,
        "date_of_birth":  "",
        "place_of_birth": "",
        "citizenship":    "",
        "career":         [],
    }

    # ---- Personal info ----
    # TM uses <th> for labels and <td> for values in the auflistung table
    for row in soup.select("table.auflistung tr"):
        th = row.find("th")
        td = row.find("td")
        if not th or not td:
            continue
        label = th.get_text(strip=True).rstrip(":").lower()
        value = td.get_text(" ", strip=True)

        if "date of birth" in label:
            # "04/09/1953 (72)" → take the part before "("
            dob_raw = value.split("(")[0].strip()
            d = parse_date(dob_raw)
            if d:
                profile["date_of_birth"] = date_to_str(d)
        elif "place of birth" in label:
            profile["place_of_birth"] = value
        elif "citizenship" in label:
            profile["citizenship"] = value

    # ---- Career history table ----
    # Rows have no odd/even class on profile pages — use all <tr> with 4+ cells
    table = soup.find("table", class_="items")
    if table:
        DATE_RE = _re.compile(r"\((\d{2}/\d{2}/\d{4})\)")
        for row in table.find_all("tr"):
            cells = row.find_all("td", recursive=False)
            if len(cells) < 3:
                continue  # skip header

            col2 = cells[2].get_text(" ", strip=True) if len(cells) > 2 else ""
            col3 = cells[3].get_text(" ", strip=True) if len(cells) > 3 else ""

            # Extract date from inside parentheses: "24/25 (27/12/2024)"
            m_from = DATE_RE.search(col2)
            m_to   = DATE_RE.search(col3)
            from_d = parse_date(m_from.group(1)) if m_from else None
            to_d   = parse_date(m_to.group(1))   if m_to   else None

            if from_d:
                profile["career"].append({
                    "from_date": date_to_str(from_d),
                    "to_date":   date_to_str(to_d),
                })

    return profile


# ---------------------------------------------------------------------------
# Characteristics computation
# ---------------------------------------------------------------------------

def compute_characteristics(stints: list[dict], profiles: dict[str, dict]) -> list[dict]:
    """
    For each stint, compute at the moment of appointment:
      age_at_appointment      -- years old when taking the job
      experience_clubs_before -- # of OTHER clubs managed before this start_date
      experience_years_before -- years since first management job
    """
    rows = []
    for stint in stints:
        tid       = stint.get("trainer_id", "")
        start_raw = stint.get("start_date", "")
        start_d   = parse_date(start_raw)
        profile   = profiles.get(tid, {})
        dob       = parse_date(profile.get("date_of_birth", ""))
        career    = profile.get("career", [])

        # Age at appointment
        age = round(years_between(dob, start_d), 1) if (dob and start_d) else ""

        # Prior clubs = stints that ended strictly before this start_date
        first_job_d  = None
        prior_clubs  = 0
        for c in career:
            c_from = parse_date(c["from_date"])
            c_to   = parse_date(c["to_date"])
            if not c_from:
                continue
            if first_job_d is None or c_from < first_job_d:
                first_job_d = c_from
            if c_to and start_d and c_to < start_d:
                prior_clubs += 1

        exp_years = round(years_between(first_job_d, start_d), 1) if (first_job_d and start_d) else ""

        rows.append({
            "football_data_name":      stint["football_data_name"],
            "transfermarkt_name":      stint["transfermarkt_name"],
            "manager":                 stint["manager"],
            "trainer_id":              tid,
            "nationality":             stint["nationality"],
            "date_of_birth":           profile.get("date_of_birth", ""),
            "start_date":              start_raw,
            "end_date":                stint.get("end_date", ""),
            "age_at_appointment":      age,
            "experience_clubs_before": prior_clubs,
            "experience_years_before": exp_years,
        })
    return rows


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--delay", type=float, default=DELAY_SECONDS)
    parser.add_argument("--limit", type=int, default=None,
                        help="Limit profile scrapes to first N unique managers (for testing).")
    args = parser.parse_args()

    # Load stints
    with open(STINTS_FILE, encoding="utf-8") as f:
        stints = list(csv.DictReader(f))
    print(f"Loaded {len(stints)} stints for {len(set(s['football_data_name'] for s in stints))} clubs.")

    # Build list of unique (trainer_id, trainer_slug, manager) to scrape
    seen: dict[str, tuple] = {}
    for s in stints:
        tid = s.get("trainer_id", "")
        if tid and tid not in seen:
            seen[tid] = (s.get("trainer_slug", ""), s.get("manager", ""), s.get("nationality",""))
    unique = [(tid, slug, name, nat) for tid, (slug, name, nat) in seen.items()]
    print(f"Unique managers with trainer_id: {len(unique)}")

    if args.limit:
        unique = unique[: args.limit]

    # Scrape profiles
    profiles: dict[str, dict] = {}
    total = len(unique)
    for i, (tid, slug, name, nat) in enumerate(unique, 1):
        print(f"[{i}/{total}] {name} (id={tid})")
        p = scrape_profile(tid, slug)
        if p:
            p["manager"]     = name
            p["nationality"] = nat
            profiles[tid] = p
        else:
            profiles[tid] = {"trainer_id": tid, "trainer_slug": slug,
                             "manager": name, "nationality": nat,
                             "date_of_birth": "", "place_of_birth": "", "citizenship": "", "career": []}
        if i < total:
            time.sleep(args.delay)

    # Write profiles CSV
    with open(PROFILES_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=PROFILE_COLS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(profiles.values())
    print(f"\nWrote {len(profiles)} profiles → {PROFILES_FILE}")

    # Compute and write characteristics
    chars = compute_characteristics(stints, profiles)
    with open(CHARS_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CHARS_COLS)
        writer.writeheader()
        writer.writerows(chars)
    print(f"Wrote {len(chars)} characteristic rows → {CHARS_FILE}")


if __name__ == "__main__":
    main()
