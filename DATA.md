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
8. [Raw News Articles](#8-raw-news-articles)
9. [Manager-Filtered Articles](#9-manager-filtered-articles)
10. [Articles with Text](#10-articles-with-text)
11. [Classified Articles](#11-classified-articles)
12. [Expectations Panel](#12-expectations-panel)
5. [Manager Characteristics](#5-manager-characteristics)
6. [Team Home/Away Performance](#6-team-homeaway-performance)
7. [Team Location](#7-team-location)

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

## 8. Raw News Articles

**File:** `news/articles_raw.csv`
**Source:** Fotomaç RSS + Google News RSS, collected via `news/collect_rss.py`
**Coverage:** 2025–26 Süper Lig season (18 teams)
**Rows:** 5,464 articles (after cross-team deduplication)

### Schema

| Column | Type | Description |
|--------|------|-------------|
| `news_uid` | string | MD5 hash of `source:url` (12 chars) — unique article ID |
| `source` | string | `fotomac` or `google_news` |
| `team` | string | Club name (football_data_name) |
| `date` | string | Publication date (YYYY-MM-DD) |
| `title` | string | Article headline |
| `url` | string | Original RSS link |
| `query` | string | RSS feed URL or search query that returned this article |

### Collection method

- **Fotomaç:** team-specific RSS feeds at `fotomac.com.tr/rss/{slug}.xml` — 18 slugs
- **Google News RSS:** 5 queries per team (Turkish: teknik direktör, hoca ayrılık, istifa, görevden; English: manager)
- Deduplication by `news_uid` across teams

### Known Issues

- RSS feeds return only the most recent ~20 articles; historical coverage is limited to what was live at collection time.
- Google News article dates reflect RSS `pubDate` — may differ slightly from original publication date.

---

## 9. Manager-Filtered Articles

**File:** `news/articles_managers.csv`
**Source:** Filtered from `articles_raw.csv` via `news/filter_manager_articles.py`
**Coverage:** 2025-07-01 to 2026-06-30
**Rows:** 2,524 articles

### Schema

Same columns as `articles_raw.csv`, plus:

| Column | Type | Description |
|--------|------|-------------|
| `matched_manager` | string | Manager name(s) detected in title/URL (empty for keyword-only matches) |
| `match_type` | string | `name`, `keyword`, or `name+keyword` |

### Filter logic

Two-pass filter: (1) name match — manager token appears in title or URL; (2) keyword match — title contains Turkish/English manager-change keywords (istifa, ayrılık, teknik direktör, sacked, etc.).

| match_type | Count |
|-----------|-------|
| name+keyword | 1,044 |
| name | 793 |
| keyword | 687 |

---

## 10. Articles with Text

**File:** `news/articles_text.csv`
**Source:** Scraped from `articles_managers.csv` via `news/scrape_text.py`
**Rows:** 2,524 articles

### Schema

| Column | Type | Description |
|--------|------|-------------|
| `news_uid` | string | Unique article ID |
| `source` | string | `fotomac` or `google_news` |
| `team` | string | Club name |
| `date` | string | Publication date |
| `title` | string | Article headline |
| `url` | string | Original URL |
| `actual_url` | string | Final URL after redirects |
| `matched_manager` | string | Detected manager name |
| `match_type` | string | Filter match type |
| `body` | string | Full article text (or cleaned title for Google News) |
| `lead` | string | First paragraph, max 300 chars |
| `body_available` | bool | True if full body was extracted |
| `fetch_status` | string | `ok`, `title_only`, `fetch_failed`, `extract_failed` |

### Known Issues

- **Google News (2,423 articles):** Google's GDPR consent redirect (`consent.google.com`) blocks server-side URL resolution. `body` contains the cleaned headline only (`body_available=False`, `fetch_status=title_only`). The headline alone carries sufficient signal for LLM scoring.
- **Fotomaç (~101 articles):** Full body extracted via `trafilatura`. Median body length: 860 characters.

---

## 11. Classified Articles

**File:** `news/articles_classified.csv`
**Source:** LLM-classified via `news/classify_articles.py` using `claude-haiku-4-5-20251001`
**Rows:** 2,524 articles

### Schema

| Column | Type | Description |
|--------|------|-------------|
| `news_uid` | string | Unique article ID |
| `source` | string | `fotomac` or `google_news` |
| `team` | string | Club name |
| `date` | string | Publication date |
| `title` | string | Article headline |
| `score` | int | Manager-change expectation score (0–4) |
| `is_relevant` | bool | Whether article concerns manager job security |
| `reason` | string | One-sentence LLM explanation |
| `score_pct` | int | Normalised score: 0→0%, 1→25%, 2→50%, 3→75%, 4→100% |
| `used_body` | bool | True if full body text was passed to LLM (Fotomaç only) |

### Score scale

| Score | Label | Definition |
|-------|-------|------------|
| 0 | No signal | Routine content, or new-manager appointment (post-change period) |
| 1 | Mild signal | Manager asked about future, unresolved rumours, replacement speculation |
| 2 | Moderate signal | Explicit criticism, poor results blamed on manager, board dissatisfaction |
| 3 | Strong signal | Fan protests, credible board meetings about manager, named candidates |
| 4 | Confirmed change | Firing, resignation, or mutual termination confirmed |

### Score distribution (2025–26 season)

| Score | Count | % |
|-------|-------|---|
| 0 | 1,654 | 65.5% |
| 1 | 83 | 3.3% |
| 2 | 57 | 2.3% |
| 3 | 186 | 7.4% |
| 4 | 544 | 21.6% |

### Validation

Prompt validated against 10 hand-labelled articles. Agreement rate (score ±1 AND is_relevant): ≥ 80%.
See `news/validation_results.csv` and `news/validation_interpretation.md`.

---

## 12. Expectations Panel

**File:** `news/expectations.csv`
**Source:** Aggregated from `articles_classified.csv` via `news/classify_articles.py`
**Rows:** 506 (team × gameweek combinations)

### Schema

| Column | Type | Description |
|--------|------|-------------|
| `team` | string | Club name (football_data_name) |
| `gameweek` | string | ISO calendar week, e.g. `2025-W32` |
| `week_start` | date | Monday of that ISO week (YYYY-MM-DD) |
| `avg_score` | float | Mean expectation score across all articles that week |
| `avg_score_pct` | float | Mean normalised score (0–100%) |
| `n_articles` | int | Number of articles contributing to the average |
| `n_relevant` | int | Articles where `is_relevant=true` |

### Aggregation notes

- **Time unit:** ISO calendar week (Monday–Sunday). Chosen because football coverage is paced around matchdays (~weekly cycle).
- Only articles with `score ≥ 0` are included (errors excluded).
- All 2,524 classified articles contribute; `is_relevant` flag is recorded but not used to filter the average.
- To merge with the match panel in Session 3, join on `team` + `week_start` (or use lagged values of `avg_score`).
