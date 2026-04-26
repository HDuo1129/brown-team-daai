# Week 02 — News Collection, LLM Classification & Expectations Panel

**Repository:** https://github.com/FarangizJ/brown-team-daai

---

## TL;DR

- Collected 5,464 news articles from Fotomaç RSS and Google News RSS across all 18 Süper Lig teams
- Filtered to 2,524 manager-relevant articles using a two-pass name + keyword filter
- Classified all 2,524 articles with `claude-haiku-4-5-20251001` on a 0–4 expectation score scale
- Validated the prompt against 10 hand-labelled articles — achieved ≥ 80% agreement before scaling
- Produced `out/expectations.csv`: one row per (team, ISO week) with `avg_grade` and `n_news`

---

## My Contributions

**Source selection & collection**
- Identified Fotomaç (Turkish football tabloid) and Google News RSS as the two sources, covering both local-language tabloid coverage and multi-outlet aggregation
- Built `news/collect_rss.py` with 5 Turkish + 1 English query per team (teknik direktör, hoca ayrılık, istifa, görevden, manager), 18 team-specific Fotomaç feeds, and cross-team deduplication via MD5 hash

**Filtering & text scraping**
- Designed two-pass manager filter (`news/filter_manager_articles.py`): name-token matching with Turkish character normalization + keyword regex
- Attempted full-text extraction for all articles — Fotomaç scraped with `trafilatura` (101 articles, median 860 chars); Google News redirects blocked by GDPR consent page, falling back to cleaned headline

**Prompt engineering & validation**
- Designed 0–4 expectation score scale; hand-labelled 10 articles spanning the full range (confirmed resignation, fan protests, routine quotes, appointment announcements)
- Iteratively revised the SYSTEM prompt through two rounds of validation to resolve appointment-scoring errors and JSON parse failures; final agreement ≥ 80%

**Classification & aggregation**
- Built `news/classify_articles.py` with resumable checkpointing (every 100 articles), rate-limit retry logic, and body-text support for Fotomaç articles
- Aggregated to ISO-week panel via `news/build_expectations.py`

---

## What We Built

| Dataset | File | Rows | Description |
|---------|------|------|-------------|
| Raw articles | `news/articles_raw.csv` | 5,464 | All RSS articles, all teams |
| Manager-filtered articles | `news/articles_managers.csv` | 2,524 | Name + keyword matched |
| Articles with text | `news/articles_text.csv` | 2,524 | + body/lead/fetch_status |
| Classified articles | `news/articles_classified.csv` | 2,524 | + score, is_relevant, reason, score_norm |
| Expectations panel | `out/expectations.csv` | 506 | One row per (team, ISO week) |
| Validation results | `news/validation_results.csv` | 10 | Human vs LLM comparison |
| Validation note | `news/validation_interpretation.md` | — | Agreement rate, disagreements, design decisions |
| Classifier prompt | `news/prompt_classifier.md` | — | Full prompt with scale, examples, output format |

---

## Expectations Panel Format

`out/expectations.csv` — one row per (team, ISO week):

| Column | Type | Description |
|--------|------|-------------|
| `team` | string | Club name (matches `managers/managers.csv`) |
| `date` | string | ISO calendar week, e.g. `2025-W32` |
| `n_news` | int | Total articles that week |
| `avg_grade` | float | Mean normalised score (0.0–1.0) over relevant articles |
| `n_relevant` | int | Articles where `is_relevant=true` |

**How to join to the Session 1 panel:**
```python
import pandas as pd
matches  = pd.read_csv("data/2025-26.csv")     # match panel (football_data_name = team)
exp      = pd.read_csv("out/expectations.csv") # expectations panel

# add ISO week to match panel
matches["date"] = pd.to_datetime(matches["Date"], dayfirst=True)
iso = matches["date"].dt.isocalendar()
matches["exp_date"] = iso["year"].astype(str) + "-W" + iso["week"].astype(str).str.zfill(2)

# merge (use lagged avg_grade in Session 3)
merged = matches.merge(exp, left_on=["HomeTeam", "exp_date"],
                             right_on=["team", "date"], how="left")
```

---

## Where to Find Everything

```
brown-team-daai/
├── news/
│   ├── collect_rss.py              # RSS collector (Fotomaç + Google News)
│   ├── filter_manager_articles.py  # Two-pass manager filter
│   ├── scrape_text.py              # Full-text scraper (Fotomaç) + title fallback
│   ├── classify_validate.py        # Prompt validation against 10 hand-labelled articles
│   ├── classify_articles.py        # Full classification pipeline (2,524 articles)
│   ├── build_expectations.py       # Aggregates to (team, week) panel
│   ├── prompt_classifier.md        # Classifier prompt (scale, examples, output format)
│   ├── hand_label_sample.csv       # 10 articles used for validation
│   ├── articles_raw.csv            # 5,464 raw articles
│   ├── articles_managers.csv       # 2,524 manager-filtered articles
│   ├── articles_text.csv           # + body text
│   ├── articles_classified.csv     # + LLM scores
│   ├── validation_results.csv      # Human vs LLM per article
│   └── validation_interpretation.md# Validation summary
├── out/
│   └── expectations.csv            # Final panel: team × week → avg_grade, n_news
├── DATA.md                         # Updated with sections 8–12 (new news tables)
└── CHANGELOG.md                    # Documents all changes from Session 1 baseline
```

---

## Prompt Design & Validation

**Score scale (0–4):**

| Score | Label | Definition |
|-------|-------|------------|
| 0 | No signal | Routine content, or new-manager appointment (post-change) |
| 1 | Mild signal | Manager fielding departure questions, unresolved rumours |
| 2 | Moderate signal | Explicit board criticism, poor results blamed on manager |
| 3 | Strong signal | Fan protests, named replacements, credible board meetings |
| 4 | Confirmed change | Firing or resignation explicitly confirmed |

**Validation (10 hand-labelled articles):**

| Metric | Result |
|--------|--------|
| Articles hand-labelled | 10 |
| Score agreement (±1 tolerance) | ≥ 90% |
| is_relevant agreement | ≥ 80% |
| Both agree | ≥ 80% ✅ |

Key prompt decisions:
- **Appointment articles score 0** — they describe the post-change period, not pre-change expectation
- **`is_relevant` is independent of score** — an appointment profile (score=0) can be is_relevant=true
- **±1 tolerance** for agreement rate — adjacent scores reflect genuine ambiguity, not failure

Full prompt → [`news/prompt_classifier.md`](news/prompt_classifier.md)
Full validation note → [`news/validation_interpretation.md`](news/validation_interpretation.md)

---

## Score Distribution (2,524 articles)

| Score | Count | % | Meaning |
|-------|-------|---|---------|
| 0 | 1,654 | 65.5% | No signal (routine / appointment) |
| 1 | 83 | 3.3% | Mild |
| 2 | 57 | 2.3% | Moderate |
| 3 | 186 | 7.4% | Strong |
| 4 | 544 | 21.6% | Confirmed change |

---

## Known Limitations

- **Google News body text unavailable** — GDPR consent redirect blocks server-side resolution for 2,423/2,524 articles; classification uses headline only for these
- **RSS coverage window** — feeds return only recent articles; historical pre-season coverage may be sparse for some teams
- **Score 4 articles (21.6%)** include both firing events and the flurry of follow-up articles immediately after — `is_relevant` flag and lag window in Session 3 will help isolate pre-change signal

---

## Next Steps (Session 3)

- Join `out/expectations.csv` to the match + manager-change panel on `(team, date)`
- Use **lagged** `avg_grade` as the expectation moderator in the DiD model
- Investigate whether high pre-change expectation attenuates the performance effect of a manager change
