# Week 01 — Data Collection & Feature Engineering

**Repository:** https://github.com/FarangizJ/brown-team-daai

---

## My Contributions

This week I designed and built the complete data infrastructure for the Turkish Süper Lig analytics project from scratch.

**Data sourcing & research design**
- Identified [football-data.co.uk](https://www.football-data.co.uk/turkeym.php) as the source for all 32 seasons of historical match results (1994–2026), evaluated its coverage gaps across eras, and structured the download
- Chose [Transfermarkt](https://www.transfermarkt.com) over alternatives for manager data due to its structured dates, consistent IDs, and coverage depth
- Researched and manually resolved all 65 club name mismatches between the two sources, producing `team_mapping.csv`

**Feature engineering decisions**
- Defined the home/away performance schema: which metrics matter (PPG, win rate, goal difference, home_away_gap) and how to compute them consistently across seasons with varying column availability
- Designed the geographic lookup table (`team_location.csv`), mapping all 65 clubs to Turkish regional categories for spatial analysis

---

## What We Did

This week we built the foundational dataset for analysing the Turkish Süper Lig (T1), covering all 32 seasons from 1994/95 through 2025/26.

### 1. Match Data (branch: `turkey-data`)

Downloaded 32 season CSV files from [football-data.co.uk](https://www.football-data.co.uk/turkeym.php), one file per season.

- **Coverage:** 1994/95 – 2025/26 (all available seasons)
- **Location:** `data/` folder on the `turkey-data` branch
- **Key columns:** `Date`, `HomeTeam`, `AwayTeam`, `FTHG`, `FTAG`, `FTR`, half-time scores, shots, cards, and bookmaker odds (for modern seasons)

### 2. Manager Data (`managers/`)

Scraped coaching history and manager profiles from [Transfermarkt](https://www.transfermarkt.com) for all 65 clubs that have appeared in the dataset.

| File | Description | Rows |
|------|-------------|------|
| `managers/team_mapping.csv` | Maps football-data club names → Transfermarkt IDs | 65 clubs |
| `managers/managers.csv` | All coaching spells with start/end dates | 3,885 stints |
| `managers/manager_profiles.csv` | Date of birth, place of birth, citizenship | 1,082 managers |
| `managers/manager_characteristics.csv` | Age at appointment, clubs managed before, years of experience | 3,885 rows |

Scripts:
- `managers/scrape_managers.py` — scrapes club-level coaching history
- `managers/scrape_manager_profiles.py` — scrapes individual manager profiles and computes experience metrics

### 3. Team Features (`features/`)

Built two team-level lookup tables to support future modelling.

| File | Description | Rows |
|------|-------------|------|
| `features/team_home_away.csv` | Per-season home/away performance: W/D/L, goals, PPG, win rate, home_away_gap | 584 (season × team) |
| `features/team_location.csv` | Each team's city, province, and Turkish geographic region | 65 teams |

---

## Where to Find Everything

```
brown-team-daai/                   ← main branch
├── data/                          # ← turkey-data branch (separate, not merged — by design)
├── managers/
│   ├── team_mapping.csv           # Club name mapping (football-data ↔ Transfermarkt)
│   ├── managers.csv               # All coaching stints (3,885 rows)
│   ├── manager_profiles.csv       # Manager DOB, birthplace, citizenship
│   ├── manager_characteristics.csv# Age & experience at time of appointment
│   ├── scrape_managers.py         # Scraping script
│   └── scrape_manager_profiles.py # Profile enrichment script
├── features/
│   ├── team_home_away.csv         # Home/away performance by season
│   └── team_location.csv          # Team → city → region lookup
└── README.md                      # Full documentation and join examples
```

---

## Data Sources

| Source | URL |
|--------|-----|
| Match results | https://www.football-data.co.uk/turkeym.php |
| Manager history | https://www.transfermarkt.com (manager history pages) |
| Manager profiles | https://www.transfermarkt.com (individual trainer profile pages) |

---

## Known Limitations

- **5 historical clubs** (A. Sebatspor, Oftasspor, Sekerspor, Siirt Jet-PA, P. Ofisi) have no Transfermarkt profile — manager data for these clubs (all 1994–1998 era) is missing.
- **Date precision** for manager stints in the 1990s–early 2000s is sometimes month-level rather than day-level on Transfermarkt.

---

## Next Steps

- Match dataset and build panel dataset to start analysis.