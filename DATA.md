# DATA.md — Turkish Süper Lig Dataset

Complete description of every table in this repository: source, schema, row count, and known quality issues.

---

## Table of Contents

1. [Match Results](#1-match-results)
2. [Club Mapping](#2-club-mapping)
3. [Manager Stints](#3-manager-stints)
4. [Manager Profiles](#4-manager-profiles)
5. [Manager Characteristics](#5-manager-characteristics)
6. [Team Home/Away Performance](#6-team-homeaway-performance)
7. [Team Location](#7-team-location)
8. [News Articles (raw)](#8-news-articles-raw)
9. [News Articles (classified)](#9-news-articles-classified)
10. [Expectations Panel](#10-expectations-panel)

---

## 1. Match Results

**File:** `data/*.csv` — one file per season, on the `turkey-data` branch  
**Source:** [football-data.co.uk](https://www.football-data.co.uk/turkeym.php)  
**Coverage:** 32 seasons, 1994/95 – 2025/26  
**Rows:** ~9,500 matches total

### Schema

| Column | Type | Description | Available |
|--------|------|-------------|-----------|
| `Date` | string | Match date — `DD/MM/YY` (older) or `DD/MM/YYYY` (modern) | All seasons |
| `HomeTeam` | string | Home club name (football-data.co.uk naming) | All seasons |
| `AwayTeam` | string | Away club name | All seasons |
| `FTHG` | int | Full-time home goals | All seasons |
| `FTAG` | int | Full-time away goals | All seasons |
| `FTR` | string | Full-time result: H / D / A | All seasons |
| `HTHG` | int | Half-time home goals | 1997/98+ |
| `HTAG` | int | Half-time away goals | 1997/98+ |
| `HTR` | string | Half-time result: H / D / A | 1997/98+ |
| `HS` / `AS` | int | Shots (home / away) | 2017/18+ |
| `HST` / `AST` | int | Shots on target | 2017/18+ |
| `HF` / `AF` | int | Fouls committed | 2017/18+ |
| `HC` / `AC` | int | Corners | 2017/18+ |
| `HY` / `AY` | int | Yellow cards | 2017/18+ |
| `HR` / `AR` | int | Red cards | 2017/18+ |
| `B365H/D/A` | float | Bet365 odds | 2001/02+ |

### Known Issues

- **Mixed date format:** Seasons 1994–2005 and 2007–2017 use `DD/MM/YY` (2-digit year); seasons 2006–2007 and 2018–2026 use `DD/MM/YYYY`. Must handle both when parsing.
- **Missing match stats:** Shots, fouls, cards, corners only available from 2017/18 onwards.
- **No betting odds:** Earliest 3 seasons (1994–1997) have results only.
- **Team name inconsistency:** 65 distinct name variants across seasons — see `managers/team_mapping.csv` for the full disambiguation.

---

## 2. Club Mapping

**File:** `managers/team_mapping.csv`  
**Source:** Manually compiled  
**Rows:** 65 clubs

### Schema

| Column | Type | Description |
|--------|------|-------------|
| `football_data_name` | string | Exact club name string used in match CSVs |
| `transfermarkt_name` | string | Official name on Transfermarkt |
| `transfermarkt_id` | string | Numeric Transfermarkt club ID (`NEEDS_MANUAL` if unknown) |
| `transfermarkt_trainer_url` | string | URL to the manager history page |
| `seasons_in_data` | string | Season range where this name variant appears |
| `notes` | string | Disambiguation notes |

### Known Issues

- 5 clubs marked `NEEDS_MANUAL` (no confirmed Transfermarkt profile): `A. Sebatspor`, `Oftasspor`, `P. Ofisi`, `Sekerspor`, `Siirt Jet-PA` — all 1990s-era clubs.
- `Ankaraspor` and `Osmanlispor` share TM ID 2944 (same legal entity, renamed).
- `Kayseri` (1994–98) maps to Erciyesspor (TM 6894), not Kayserispor (TM 3205).

---

## 3. Manager Stints

**File:** `managers/managers.csv`  
**Source:** Scraped from Transfermarkt via `managers/scrape_managers.py`  
**Rows:** 3,885 coaching stints across 60 clubs

### Schema

| Column | Type | Description |
|--------|------|-------------|
| `football_data_name` | string | Club name (matches match CSV naming) |
| `transfermarkt_name` | string | Official TM club name |
| `manager` | string | Manager full name |
| `trainer_id` | string | Transfermarkt numeric manager ID |
| `trainer_slug` | string | Transfermarkt URL slug for manager |
| `nationality` | string | Manager nationality |
| `start_date` | string | Appointment date (YYYY-MM-DD) |
| `end_date` | string | Departure date (YYYY-MM-DD), empty = still in charge |

### Known Issues

- 5 clubs have no TM profile — zero manager stints for those clubs.
- Date precision: stints from the 1990s–early 2000s sometimes have month-level precision (day set to 01).
- Same manager may appear multiple times for the same club (multiple spells).

---

## 4. Manager Profiles

**File:** `managers/manager_profiles.csv`  
**Source:** Scraped from Transfermarkt individual profile pages via `managers/scrape_manager_profiles.py`  
**Rows:** 1,082 unique managers

### Schema

| Column | Type | Description |
|--------|------|-------------|
| `trainer_id` | string | Transfermarkt numeric manager ID (primary key) |
| `trainer_slug` | string | URL slug |
| `manager` | string | Full name |
| `nationality` | string | Nationality |
| `date_of_birth` | string | DOB (YYYY-MM-DD), empty if unknown |
| `place_of_birth` | string | City of birth |
| `citizenship` | string | Citizenship country |

### Known Issues

- ~5% of managers have no DOB on Transfermarkt (mostly older or lesser-known coaches).
- ~4% missing citizenship.
- `place_of_birth` is a free-text city name — not standardized.

---

## 5. Manager Characteristics

**File:** `managers/manager_characteristics.csv`  
**Source:** Computed from `managers.csv` + `manager_profiles.csv`  
**Rows:** 3,885 (one per coaching stint)

### Schema

| Column | Type | Description |
|--------|------|-------------|
| `football_data_name` | string | Club name |
| `transfermarkt_name` | string | Official TM club name |
| `manager` | string | Manager full name |
| `trainer_id` | string | TM manager ID |
| `nationality` | string | Nationality |
| `date_of_birth` | string | DOB (YYYY-MM-DD) |
| `start_date` | string | Appointment date |
| `end_date` | string | Departure date |
| `age_at_appointment` | float | Age in years at `start_date` |
| `experience_clubs_before` | int | # of clubs managed before this stint |
| `experience_years_before` | float | Years since first management job |

### Known Issues

- `age_at_appointment` is empty for ~4% of stints (DOB missing from profile).
- `experience_clubs_before` counts completed stints only (ended before `start_date`); ongoing overlapping stints are excluded.
- Early career data on Transfermarkt may be incomplete for older managers.

---

## 6. Team Home/Away Performance

**File:** `features/team_home_away.csv`  
**Source:** Computed from all match CSVs  
**Rows:** 584 (season × team combinations)

### Schema

| Column | Type | Description |
|--------|------|-------------|
| `season` | string | Season label e.g. `2023-24` |
| `team` | string | Club name |
| `home_games` | int | Matches played at home |
| `home_wins` | int | Home wins |
| `home_draws` | int | Home draws |
| `home_losses` | int | Home losses |
| `home_goals_for` | int | Goals scored at home |
| `home_goals_against` | int | Goals conceded at home |
| `home_goal_diff` | int | Home goal difference |
| `home_points` | int | Home points (W=3, D=1, L=0) |
| `home_points_per_game` | float | Home PPG (rounded 3 dp) |
| `home_win_rate` | float | Home win % (rounded 3 dp) |
| `away_*` | — | Mirror of all home columns for away matches |
| `home_away_gap` | float | `home_ppg − away_ppg` |

### Known Issues

- Relegation/promotion means not every team appears in every season.
- A handful of matches in older seasons have null `FTHG`/`FTAG` — these rows are skipped during aggregation.

---

## 7. Team Location

**File:** `features/team_location.csv`  
**Source:** Manually compiled  
**Rows:** 65 teams

### Schema

| Column | Type | Description |
|--------|------|-------------|
| `football_data_name` | string | Club name (matches match CSV naming) |
| `city` | string | City the club is based in |
| `province` | string | Turkish province (il) |
| `region` | string | Turkish geographic region |

### Region values

`Marmara`, `Aegean`, `Mediterranean`, `Central Anatolia`, `Black Sea`, `Eastern Anatolia`, `Southeastern Anatolia`

### Known Issues

- Location reflects the club's primary home city. Two clubs (Buyuksehyr, Karagumruk) have relocated within Istanbul over time — both mapped to Istanbul.
- `Bodrumspor` is listed under Mugla province / Aegean region (Bodrum is technically on the Aegean coast despite being in Mugla).

---

## 8. News Articles (raw)

**File:** `news/articles_managers.csv`
**Source:** Google News RSS, queried per team and matched manager name (Season 2025/26)
**Script:** `news/collect_rss.py` → `news/filter_manager_articles.py`
**Rows:** 2,524 articles

### Schema

| Column | Type | Description |
|--------|------|-------------|
| `news_uid` | string | SHA-1 hex digest of URL (primary key) |
| `source` | string | Feed source (`google_news`) |
| `team` | string | Süper Lig club name (Transfermarkt naming) |
| `date` | string | Publication date (YYYY-MM-DD) |
| `title` | string | Article headline |
| `url` | string | Google News redirect URL |
| `query` | string | RSS query string used to find this article |
| `matched_manager` | string | Manager name that triggered the match (empty if keyword-only) |
| `match_type` | string | How article was matched: `name`, `keyword`, or `name+keyword` |

**Coverage:** 2025-07-01 to 2026-04-21 | 18 clubs

### Known Issues

- 101 of 2,524 articles have full body text scraped (`news/articles_text.csv`); the rest are title-only because Google News redirects blocked full-text extraction.
- Articles matched by keyword only (`match_type=keyword`) may include false positives (articles mentioning "teknik direktör" in a non-job-security context).
- No articles from the 2025/26 summer window before 2025-07-01.

---

## 9. News Articles (classified)

**File:** `news/articles_classified.csv`
**Source:** `news/articles_managers.csv` + Anthropic Claude Haiku API
**Script:** `news/classify_articles.py`
**Rows:** one per article classified (up to 2,524)

### Schema

| Column | Type | Description |
|--------|------|-------------|
| `news_uid` | string | Primary key — matches `articles_managers.csv` |
| `team` | string | Club name |
| `date` | string | Publication date (YYYY-MM-DD) |
| `score` | int | Raw expectation score 0–4 (see scale below) |
| `score_norm` | float | Normalised score: 0→0.0, 1→0.25, 2→0.5, 3→0.75, 4→1.0 |
| `is_relevant` | bool | True if article is about manager job security |
| `reason` | string | One-sentence LLM explanation of the score |

### Score scale

| Score | Label | Definition |
|-------|-------|------------|
| 0 | No signal | Routine content, player news, or post-change appointment |
| 1 | Mild signal | Manager fielding departure questions; unresolved rumour |
| 2 | Moderate signal | Explicit criticism; board dissatisfaction mentioned |
| 3 | Strong signal | Fan protests; named replacement; credible board meeting report |
| 4 | Confirmed change | Firing, resignation, or termination confirmed |

### Known Issues

- Classification is based on headline only for 2,423 articles (body unavailable); 101 articles use body text up to 800 characters.
- Model: `claude-haiku-4-5-20251001` — fast and cheap but may miss nuance in Turkish-language headlines without translation.
- Validation: 10 hand-labelled articles; see `news/validation_interpretation.md` for agreement rates.

---

## 10. Expectations Panel

**File:** `out/expectations.csv`
**Source:** Aggregated from `news/articles_classified.csv`
**Script:** `news/build_expectations.py`
**Rows:** one per (team, gameweek)

### Schema

| Column | Type | Description |
|--------|------|-------------|
| `team` | string | Club name |
| `gameweek` | string | ISO calendar week (e.g. `2025-W42`) |
| `n_news` | int | Total articles in that (team, week) |
| `avg_grade` | float | Mean `score_norm` across **relevant** articles (0.0–1.0); 0 if no relevant articles |
| `n_relevant` | int | Count of articles scored `is_relevant=True` |

### Usage in Session 3

Merge onto the match + manager-change panel by team and the gameweek containing the match date. Use **lagged** values of `avg_grade` (the week before the match) as the expectation signal.

### Known Issues

- Weeks with zero relevant articles are included with `avg_grade=0` and `n_relevant=0`.
- Coverage is 2025-W27 to 2026-W16 (one season). Earlier seasons have no news data.
