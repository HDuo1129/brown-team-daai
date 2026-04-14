# Turkey Süper Lig Dataset

Match-level data and manager history for the Turkish Süper Lig (T1), sourced from [football-data.co.uk](https://www.football-data.co.uk/turkeym.php) and [Transfermarkt](https://www.transfermarkt.com).

---

## Repository structure

```
brown-team-daai/
├── data/                   # Match CSV files (one per season) — see turkey-data branch
│   ├── 1994-1995.csv
│   ├── ...
│   └── 2025-2026.csv
├── managers/               # Manager data collection
│   ├── team_mapping.csv    # football-data ↔ Transfermarkt mapping for all 65 clubs
│   ├── scrape_managers.py  # Script to scrape manager history from Transfermarkt
│   └── managers.csv        # Output of the script (generated, not committed)
└── README.md
```

> **Note:** The match CSV files live on the `turkey-data` branch. This `main` branch contains documentation and collection scripts.

---

## 1. Match Data

### Source

**football-data.co.uk** — `https://www.football-data.co.uk/turkeym.php`

All files follow the URL pattern:
```
https://www.football-data.co.uk/mmz4281/{SEASON_CODE}/T1.csv
```
e.g. `mmz4281/2526/T1.csv` for the 2025/26 season.

### Coverage

| Era | Seasons | Content |
|-----|---------|---------|
| 1994/95 – 1996/97 | 3 seasons | Full-time results only |
| 1997/98 – 2000/01 | 4 seasons | Results + basic betting odds |
| 2001/02 – 2016/17 | 16 seasons | Results + full bookmaker odds (B365, BW, IW, PS, WH, VC …) |
| 2017/18 – 2025/26 | 9 seasons | Results + match stats (shots, fouls, cards) + extended odds (Asian handicap, O/U 2.5) |

### Key columns

| Column | Description |
|--------|-------------|
| `Date` | Match date (DD/MM/YYYY) |
| `HomeTeam` / `AwayTeam` | Club names as used on football-data.co.uk |
| `FTHG` / `FTAG` | Full-time home / away goals |
| `FTR` | Full-time result: H / D / A |
| `HTHG` / `HTAG` / `HTR` | Half-time equivalents |
| `HS` / `AS` | Home / away shots (modern seasons) |
| `HST` / `AST` | Home / away shots on target (modern seasons) |
| `B365H/D/A` | Bet365 odds — home win / draw / away win |

Full column reference: [football-data.co.uk notes](https://www.football-data.co.uk/notes.txt)

---

## 2. Manager Data

### Purpose

To enrich each match row with the manager in charge of each club on that date, enabling analysis of managerial impact on results, home/away performance, tactical trends, etc.

### Source

**Transfermarkt** — manager history pages at:
```
https://www.transfermarkt.com/{club-slug}/trainer/verein/{club-id}
```

Transfermarkt records: manager name, nationality, exact appointment and departure dates, and win/draw/loss statistics per spell.

### Files

#### `managers/team_mapping.csv`

Maps every club name used in football-data.co.uk to its Transfermarkt equivalent.

| Column | Description |
|--------|-------------|
| `football_data_name` | Exact team name string in the CSV files |
| `transfermarkt_name` | Official name on Transfermarkt |
| `transfermarkt_id` | Numeric club ID (`NEEDS_MANUAL` = no confirmed TM profile) |
| `transfermarkt_trainer_url` | Direct URL to the manager history page |
| `seasons_in_data` | Season range where this name variant appears (if restricted) |
| `notes` | Name disambiguation and historical notes |

**Important naming ambiguities handled:**

| football-data name | Situation |
|--------------------|-----------|
| `Ankaraspor` | Appears 2004–2009; Transfermarkt tracks this lineage under ID 2944 (same entity later renamed Osmanlıspor, then SB Ankaraspor) |
| `Osmanlispor` | 2015–2018 era of the same club (TM ID 2944) |
| `Antalya` | 1994–95 only; same club as `Antalyaspor` (TM ID 589) |
| `Kayseri` | 1994–98; refers to Kayseri Erciyesspor (TM ID 6894), not Kayserispor |
| `Erzurum` / `Erzurumspor` | Old Erzurumspor club (TM ID 1766) |
| `Erzurum BB` | 2018–2021; BB Erzurumspor / Erzurumspor FK (TM ID 39722) |
| `Malatyaspor` | 2001–2006; the original Malatyaspor (TM ID 1264), distinct from Yeni Malatyaspor |
| `Yeni Malatyaspor` | 2017–2022; separate club founded 2000 (TM ID 19789) |
| `Buyuksehyr` | Istanbul Büyükşehir Belediyespor → now Başakşehir FK (TM ID 6890) |
| `Gaziantep` | Gaziantep FK, founded 2011 (TM ID 2832), distinct from defunct Gaziantepspor |
| `Gaziantepspor` | Original club, dissolved 2020 (TM ID 524) |
| `A. Sebatspor`, `Oftasspor`, `Sekerspor`, `Siirt Jet-PA`, `P. Ofisi` | Very old 1990s clubs with no confirmed Transfermarkt profile (`NEEDS_MANUAL`) |

#### `managers/scrape_managers.py`

Scrapes all coaching spells from Transfermarkt for every club in `team_mapping.csv` (skipping `NEEDS_MANUAL` entries) and writes `managers.csv`.

**Requirements:**
```bash
pip install beautifulsoup4
```

**Run:**
```bash
# Full scrape (all clubs, ~4 s delay between requests)
python managers/scrape_managers.py

# Test run — first 5 clubs only
python managers/scrape_managers.py --limit 5

# Adjust delay
python managers/scrape_managers.py --delay 6
```

**Output — `managers/managers.csv`:**

| Column | Description |
|--------|-------------|
| `football_data_name` | Club name as in match CSVs |
| `transfermarkt_name` | Official TM name |
| `manager` | Manager full name |
| `nationality` | Manager nationality |
| `start_date` | Appointment date (YYYY-MM-DD) |
| `end_date` | Departure date (YYYY-MM-DD), empty if still in charge |

### Joining managers to match data

```python
import pandas as pd
import glob

# Load all match files
dfs = [pd.read_csv(f, encoding='latin-1') for f in sorted(glob.glob('data/*.csv'))]
matches = pd.concat(dfs, ignore_index=True)
matches['Date'] = pd.to_datetime(matches['Date'], dayfirst=True)

# Load manager data
mgr = pd.read_csv('managers/managers.csv', parse_dates=['start_date', 'end_date'])

def get_manager(team_name: str, match_date: pd.Timestamp) -> str:
    """Return the manager in charge of team_name on match_date."""
    club_spells = mgr[mgr['football_data_name'] == team_name]
    in_charge = club_spells[
        (club_spells['start_date'] <= match_date) &
        (club_spells['end_date'].isna() | (club_spells['end_date'] >= match_date))
    ]
    if in_charge.empty:
        return ''
    return in_charge.iloc[-1]['manager']

matches['HomeManager'] = matches.apply(
    lambda r: get_manager(r['HomeTeam'], r['Date']), axis=1
)
matches['AwayManager'] = matches.apply(
    lambda r: get_manager(r['AwayTeam'], r['Date']), axis=1
)
```

### Limitations

- Transfermarkt may block automated requests (HTTP 403). Running with `--delay 6` or higher reduces this risk.
- For the 5 very old clubs (`A. Sebatspor`, `Oftasspor`, `Sekerspor`, `Siirt Jet-PA`, `P. Ofisi`) no Transfermarkt profile was found. Manager data for matches involving these clubs (all in the 1994–1998 era) will require manual collection from Wikipedia or contemporary sources.
- Date precision for spells in the 1990s–early 2000s may be month-level rather than day-level on Transfermarkt.
