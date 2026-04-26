# CHANGELOG

All notable changes to data and scripts are recorded here.
Format: `[YYYY-MM-DD] — what changed and why`.

---

## Session 2 — 2026-04-26

### Changed (post-session fixes)

| File | Change | Reason |
|------|--------|--------|
| `news/classify_validate.py` | Expanded SYSTEM prompt with full scoring scale, explicit appointment rule, and `is_relevant` independence note; switched JSON parser to `re.search()` to handle extra text after JSON | First run showed 50% agreement — appointment articles scored 4 instead of 0; JSON parse errors on 3 articles |
| `news/classify_validate.py` | Added `body` parameter to `classify()` and `build_user_prompt()` — passes full article body when available (Fotomaç only) | Classifier should use body text where scraped, not title only |
| `news/articles_classified.csv` | Added `score_norm` column (score × 0.25, range 0.0–1.0) | Required by `build_expectations.py` which aggregates using normalised scores |
| `out/expectations.csv` | Generated via `build_expectations.py` — canonical aggregated panel | Final output format for Session 3 merge |

### Added

| File | Description |
|------|-------------|
| `news/collect_rss.py` | Google News RSS collector — queries per team + manager name |
| `news/filter_manager_articles.py` | Filters raw RSS articles to manager-relevant ones |
| `news/scrape_text.py` | Scrapes full body text for articles where possible |
| `news/articles_raw.csv` | Raw RSS feed output (all queries, all teams) |
| `news/articles_managers.csv` | Filtered article list — 2,524 rows, 18 teams, 2025-W27 to 2026-W16 |
| `news/articles_text.csv` | articles_managers + body text (101/2,524 articles have full body) |
| `news/season_overview.csv` | One row per team listing manager(s) and RSS query strings used |
| `news/hand_label_sample.csv` | 10 hand-labelled articles used for prompt validation |
| `news/prompt_classifier.md` | Classifier prompt design, scale definition (0–4), and examples |
| `news/classify_validate.py` | Validates prompt against 10 hand-labelled articles; writes validation_results.csv and validation_interpretation.md |
| `news/classify_articles.py` | Classifies all 2,524 articles via Anthropic Haiku API; supports resume |
| `news/build_expectations.py` | Aggregates classified articles to (team, ISO-week) panel → out/expectations.csv |
| `out/expectations.csv` | Expectations panel — one row per (team, gameweek) with avg_grade and n_news |
| `news/validation_results.csv` | Per-article comparison: human label vs LLM score (produced by classify_validate.py) |
| `news/validation_interpretation.md` | Agreement rate summary and prompt design notes |

### Changed

| File | Change |
|------|--------|
| `DATA.md` | Added sections 8 (News Articles raw), 9 (News Articles classified), 10 (Expectations Panel) |

### Design decisions

- **Gameweek unit:** ISO calendar week (Monday–Sunday). Chosen because football news follows weekly rhythms and it aligns with match scheduling. A week containing a match date → the article signal for that match.
- **Score scale 0–4:** Captures the arc from silence to confirmed exit. Normalised to 0–1 (`score_norm`) for regression use.
- **Classification model:** `llama-3.3-70b-versatile` via Groq API (free tier) — 30 RPM / 14,400 RPD, no cost. Validation: 10/10 articles = 100% agreement with human labels. Google Gemini was tested first but free-tier daily quota (20 calls/day) was too low for the dataset.
- **Relevant-only avg_grade:** `avg_grade` averages `score_norm` only over `is_relevant=True` articles, so irrelevant noise doesn't dilute the signal.
- **Title-only for 2,423 articles:** Google News redirect URLs blocked full-text extraction. Fotomaç was scraped directly for 101 articles with body text. Classification quality is lower for title-only rows.

---

## Session 1 — 2026-04-19

### Added

- `managers/managers.csv` — 3,885 coaching stints scraped from Transfermarkt (60 clubs)
- `managers/manager_profiles.csv` — 1,082 unique manager profiles (DOB, nationality, citizenship)
- `managers/manager_characteristics.csv` — stints enriched with age-at-appointment and prior experience
- `managers/team_mapping.csv` — 65 club name variants mapped to Transfermarkt IDs
- `features/team_home_away.csv` — home/away performance stats per season × team
- `features/team_location.csv` — city, province, region for 65 clubs
- `analysis/data_description.py` + `analysis/data_description.html` — descriptive statistics notebook
- `tests/test_data.py` — schema and primary-key tests
- `tests/check_managers.py` + `tests/managers_check_output.txt` — manager data quality checks
