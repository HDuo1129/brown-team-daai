# DATA.md — Turkey Capstone

## Snapshot

- Scrape/build date: 2026-04-14
- League: Turkish Super Lig
- Match seasons covered: 2013/14 to 2024/25
- Match rows: 3,974
- Teams observed in match results: 41
- Manager spell rows: 601
- Teams covered in manager_spells: 10
- Unique managers in manager_chars: 345
- Team-season rows: 225

## Sources

### Match results

Source: football-data.co.uk CSV files

- `https://www.football-data.co.uk/mmz4281/1314/T1.csv`
- `https://www.football-data.co.uk/mmz4281/1415/T1.csv`
- `https://www.football-data.co.uk/mmz4281/1516/T1.csv`
- `https://www.football-data.co.uk/mmz4281/1617/T1.csv`
- `https://www.football-data.co.uk/mmz4281/1718/T1.csv`
- `https://www.football-data.co.uk/mmz4281/1819/T1.csv`
- `https://www.football-data.co.uk/mmz4281/1920/T1.csv`
- `https://www.football-data.co.uk/mmz4281/2021/T1.csv`
- `https://www.football-data.co.uk/mmz4281/2122/T1.csv`
- `https://www.football-data.co.uk/mmz4281/2223/T1.csv`
- `https://www.football-data.co.uk/mmz4281/2324/T1.csv`
- `https://www.football-data.co.uk/mmz4281/2425/T1.csv`

### Manager spells

Source target: Transfermarkt club staff-history pages

- `https://www.transfermarkt.com/galatasaray/mitarbeiterhistorie/verein/141/personalie_id/0/plus/1`
- `https://www.transfermarkt.com/fenerbahce-istanbul/mitarbeiterhistorie/verein/36/personalie_id/0/plus/1`
- `https://www.transfermarkt.com/besiktas-jk/mitarbeiterhistorie/verein/114/personalie_id/0/plus/1`
- `https://www.transfermarkt.com/trabzonspor/mitarbeiterhistorie/verein/449/personalie_id/0/plus/1`
- `https://www.transfermarkt.com/istanbul-basaksehir-fk/mitarbeiterhistorie/verein/6890/personalie_id/0/plus/1`
- `https://www.transfermarkt.com/sivasspor/mitarbeiterhistorie/verein/2381/personalie_id/0/plus/1`
- `https://www.transfermarkt.com/konyaspor/mitarbeiterhistorie/verein/2293/personalie_id/0/plus/1`
- `https://www.transfermarkt.com/antalyaspor/mitarbeiterhistorie/verein/589/personalie_id/0/plus/1`
- `https://www.transfermarkt.com/kasimpasa/mitarbeiterhistorie/verein/10484/personalie_id/0/plus/1`
- `https://www.transfermarkt.com/gaziantep-fk/mitarbeiterhistorie/verein/2832/personalie_id/0/plus/1`

Note: in the current environment, manager profile and team-season scraping can fail because Transfermarkt layout/network access is unstable. The repo therefore includes reproducible fallback builders for `manager_chars` and `team_seasons`.

## Tables

### matches_raw

Rows: 3,974  
Seasons covered: 2013/14 to 2024/25  
Teams covered: 41

| Column | Type | Description |
|---|---|---|
| match_id | str | PK: `{season}_{week}_{game_n}` |
| season | str | e.g. `2023/24` |
| match_date | date | ISO 8601 |
| home_team | str | Standardised team name |
| away_team | str | Standardised team name |
| home_goals | float/int | Full-time home goals |
| away_goals | float/int | Full-time away goals |
| league | str | `Super Lig` |

Known issues:
- Match counts vary by season because league size changed over time.
- Some team names still reflect source naming conventions and rely on `data/team_names.csv` for canonicalisation.

### manager_spells

Rows: 601  
Teams covered: 10  
Observed manager changes: 591

| Column | Type | Description |
|---|---|---|
| spell_id | int | PK |
| team | str | Standardised team name |
| manager_name | str | Cleaned manager name |
| start_date | date | First date in spell |
| end_date | date | Last date in spell |
| departure_reason | str | Currently mostly missing |
| is_caretaker | bool | Caretaker/interim flag |

Known issues:
- Coverage is incomplete relative to the 41 teams in `matches_raw`; the current scrape covers 10 clubs.
- `departure_reason` is not reliably scraped yet.
- Live Transfermarkt layouts can change, so this table may rely on cached/fallback raw output when scraping fails.

### manager_chars

Rows: 345

| Column | Type | Description |
|---|---|---|
| manager_name | str | PK |
| nationality | str | Current fallback value is often `Unknown` |
| is_foreign | bool | True if non-Turkish, else False, else null |
| birth_date | date | Extracted when available |
| played_professionally | bool | Currently unavailable in fallback build |
| prior_clubs_count | int | Derived from observed spells |
| career_win_rate | float | Currently unavailable in fallback build |

Known issues:
- This dataset is currently built reproducibly from `manager_spells` when profile scraping is unavailable.
- `nationality`, `played_professionally`, and `career_win_rate` are incomplete under the fallback path.

### team_seasons

Rows: 225  
Seasons covered: 12  
Teams covered: 41

| Column | Type | Description |
|---|---|---|
| team | str | PK component |
| season | str | PK component |
| prev_season_position | int | Derived from prior-season standings where available |
| squad_market_value_eur | float | Currently unavailable in fallback build |

Known issues:
- This table is currently derived from match results when Transfermarkt team-season scraping is unavailable.
- `squad_market_value_eur` is missing in the derived fallback dataset.

### matches_clean

Rows: 3,974  
Description: de-duplicated match results with canonical team names applied where mappings exist.

### manager_clean

Rows: 601  
Description: cleaned manager spells used for joining managers to matches by date.

### manager_chars_clean

Rows: 345  
Description: processed manager-characteristics table used for later analysis controls.

### team_seasons_clean

Rows: 225  
Description: processed team-season covariate table.

### manager_panel

Rows: 7,948  
Description: one row per match-team observation with goals, points, and assigned manager.

Known issues:
- `manager_name` is still missing for many clubs because manager_spells coverage is incomplete.

### analysis_panel

Rows: 3,974  
Description: match-level joined panel with `home_manager`, `away_manager`, `home_points`, and `away_points`.

Known issues:
- Missing home-manager assignments: 2,321
- Missing away-manager assignments: 2,322
- Missing assignments are driven by incomplete manager-spell coverage, not by duplicate or broken joins.

## Team name standardisation

Canonical team aliases are stored in [data/team_names.csv](/Users/feya/Downloads/brown-team-daai/data/team_names.csv).

## Quality checks

Validation is run through [validation.py](/Users/feya/Downloads/brown-team-daai/validation.py) and currently checks:

- required schema columns
- duplicate primary keys
- missing critical values
- malformed manager names containing embedded dates

Latest validation result:

- all raw and processed tables currently pass the implemented validation checks
- remaining data limitations are documented above rather than hidden
