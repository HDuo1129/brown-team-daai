# Project Plan — Turkish Süper Lig Manager Analysis

## Research Question

Does managerial change affect team performance in the Turkish Süper Lig, and do manager characteristics (nationality, age, experience) predict post-appointment outcomes?

---

## Data Sources

| Source | URL | What we get |
|--------|-----|-------------|
| football-data.co.uk | https://www.football-data.co.uk/turkeym.php | Match results, 1994–2026 |
| Transfermarkt | https://www.transfermarkt.com | Manager history, profiles, DOB, career stats |

---

## Datasets & Primary Keys

| Dataset | File | Primary Key | Rows |
|---------|------|-------------|------|
| Match results | `data/*.csv` (turkey-data branch) | `Date + HomeTeam + AwayTeam` | ~9,500 matches |
| Club → TM mapping | `managers/team_mapping.csv` | `football_data_name` | 65 clubs |
| Manager stints | `managers/managers.csv` | `football_data_name + start_date` | 3,885 |
| Manager profiles | `managers/manager_profiles.csv` | `trainer_id` | 1,082 |
| Manager characteristics | `managers/manager_characteristics.csv` | `football_data_name + start_date` | 3,885 |
| Home/away performance | `features/team_home_away.csv` | `season + team` | 584 |
| Team location | `features/team_location.csv` | `football_data_name` | 65 |

---

## Join Logic

```
match row
  └── HomeTeam / AwayTeam + Date
        └── managers.csv (football_data_name, start_date ≤ Date ≤ end_date)
              └── manager_characteristics.csv (trainer_id)
                    └── manager_profiles.csv (trainer_id)
  └── HomeTeam + season
        └── team_home_away.csv (team + season)
        └── team_location.csv (football_data_name)
```

Key join note: match CSV dates use `DD/MM/YY` (1994–2005, 2007–2017) and `DD/MM/YYYY` (2006–2007, 2018–2026). Both formats must be handled when joining to manager stints.

---

## Tests Planned

### Data tests (`tests/test_data.py`)
- No duplicate matches (same date + home + away)
- All `FTR` values in {H, D, A}
- Goals are non-negative integers
- Manager `end_date` ≥ `start_date` where both present
- No manager stints with `start_date` after today
- All `football_data_name` values in manager stints exist in team_mapping

### Data-describe checks
- Coverage: % of matches with a matched manager on each side
- Missing values per column for each dataset
- Season-by-season match counts
- Manager stint length distribution

### Code tests
- `parse_date()` handles all known formats and returns correct output
- `scrape_club()` returns a list (not None) for a known club ID

---

## Task Ownership

| Task | Owner |
|------|-------|
| Data collection strategy & source evaluation | Duo Huang |
| Club name mapping (65 clubs, all ambiguities) | Duo Huang |
| Match data download script | Duo Huang |
| Transfermarkt scraping (managers + profiles) | Duo Huang |
| Feature engineering (home/away stats, location table) | Duo Huang |
| Data tests & quality checks | Duo Huang |
| Data description & exhibits | Duo Huang |

---

## Known Gaps & Mitigations

| Gap | Impact | Mitigation |
|-----|--------|------------|
| 5 clubs with no TM profile | Missing managers for ~1994–1998 era matches | Accept as limitation; document clearly |
| Mixed date formats in match CSVs | Join failures if not handled | Add `%d/%m/%y` format to join logic |
| TM date precision (1990s stints often month-level) | Incorrect manager assignment near change dates | Flag stints where precision is uncertain |
| Transfermarkt may block scraper | Incomplete data | Use 4s delay + Chrome User-Agent headers |
