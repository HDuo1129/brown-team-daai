# Week 01 — Data Collection & Feature Engineering

**Repository:** https://github.com/FarangizJ/brown-team-daai

---

## TL;DR

- Built a complete match + manager + feature dataset for the Turkish Süper Lig (1994–2026)
- 11,094 matches across 32 seasons, 3,884 coaching stints, 1,082 manager profiles
- Resolved 65 club name inconsistencies between two data sources
- All datasets pass core quality checks (details → `tests/managers_check_output.txt`)

---

## My Contributions

**Data sourcing & research design**
- Identified [football-data.co.uk](https://www.football-data.co.uk/turkeym.php) as the source for all 32 seasons of match results, evaluated coverage gaps across eras, and structured the download
- Chose [Transfermarkt](https://www.transfermarkt.com) over alternatives for manager data due to its structured dates, consistent IDs, and coverage depth
- Researched and manually resolved all 65 club name mismatches between the two sources, producing `team_mapping.csv`
- Built the core content and structure of the GitHub repository

**Feature engineering decisions**
- Defined the home/away performance schema: which metrics matter (PPG, win rate, goal difference, home_away_gap) and how to compute them consistently across seasons
- Designed the geographic lookup table (`team_location.csv`), mapping all 65 clubs to Turkish regional categories for spatial analysis

---

## What We Built

| Dataset | File | Rows |
|---------|------|------|
| Match results | `data/*.csv` (turkey-data branch) | ~11,094 matches, 32 seasons |
| Club name mapping | `managers/team_mapping.csv` | 65 clubs |
| Manager stints | `managers/managers.csv` | 3,884 coaching spells |
| Manager profiles | `managers/manager_profiles.csv` | 1,082 managers (95% DOB coverage) |
| Manager characteristics | `managers/manager_characteristics.csv` | Age & experience at appointment |
| Home/away performance | `features/team_home_away.csv` | 584 rows (season × team) |
| Team locations | `features/team_location.csv` | 65 teams → city, province, region |

---

## Where to Find Everything

```
brown-team-daai/                      ← main branch
├── managers/
│   ├── team_mapping.csv              # Club name mapping
│   ├── managers.csv                  # All coaching stints
│   ├── manager_profiles.csv          # DOB, birthplace, citizenship
│   ├── manager_characteristics.csv   # Age & experience at appointment
│   ├── scrape_managers.py            # Scraping script
│   └── scrape_manager_profiles.py    # Profile enrichment script
├── features/
│   ├── team_home_away.csv            # Home/away performance by season
│   └── team_location.csv             # Team → city → region lookup
├── tests/
│   ├── test_data.py                  # 17 pytest data + code tests (all passing)
│   ├── check_managers.py             # Detailed manager QA script
│   └── managers_check_output.txt     # Full QA output
├── analysis/
│   ├── data_description.py           # Generates HTML report
│   └── data_description.html         # Descriptive stats + 7 exhibits
├── DATA.md                           # Full schema for all 7 tables
├── PLAN.md                           # Sources, keys, join logic, ownership
└── data/                             # ← turkey-data branch: 32 season CSVs
```

---

## Quality Assurance — Summary

All datasets pass core quality checks:

| Check | Result |
|-------|--------|
| Duplicate rows | ✅ None |
| Missing critical fields | ✅ None |
| Date format consistency | ✅ All YYYY-MM-DD |
| Club names consistent across files | ✅ Pass |
| FTR values valid (H/D/A only) | ✅ Pass |

Known issues (documented, tolerated):
- 2 Transfermarkt date-order errors (<0.1% of stints)
- 5 historical clubs have no manager data — no Transfermarkt profile exists

Full test output → [`tests/managers_check_output.txt`](tests/managers_check_output.txt)
Full pytest suite → [`tests/test_data.py`](tests/test_data.py) (17 tests, all passing)

---

## Known Limitations

- **5 clubs** (A. Sebatspor, Oftasspor, Sekerspor, Siirt Jet-PA, P. Ofisi) have no manager data — all are 1990s-era clubs with no Transfermarkt profile
- **Mixed date format** in match CSVs (DD/MM/YY for older seasons) requires dual-format parsing when joining to manager stints
- **Match stats** (shots, cards, fouls) only available from 2017/18 onwards

---

## Next Steps

- Join manager data to match-level data and build panel dataset for analysis
