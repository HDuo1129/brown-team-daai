# Does Changing a Manager Improve Team Performance?
### Evidence from the Turkish Süper Lig, 1994–2026

**Team Brown — CEU | Course: Data Analysis with AI: Research Support**  
Duo Huang · Semih Tosun · Farangiz Jurakhonova

## 📄 [View Full Report](https://hduo1129.github.io/brown-team-daai/report.html)

---

## Overview

Mid-season manager dismissals are among the most visible and costly interventions in professional football — yet the causal evidence on whether they actually work remains mixed. Clubs fire managers hoping for an immediate performance turnaround, but the academic literature consistently finds that post-firing improvements are largely explained by **mean reversion**: teams that fire managers are typically in acute poor form, and their results would likely improve regardless of whether the manager was replaced.

This project investigates that question in the **Turkish Süper Lig** — one of Europe's most active markets for mid-season manager changes. Our dataset covers **30 seasons (1994–2026)**, **11,094 matches**, and **531 mid-season treatment events**, making it one of the most comprehensive panel studies of managerial turnover in Turkish football.

Beyond the standard "does it work?" question, we introduce a novel second layer: using LLM-classified Turkish football news to measure **pre-change media pressure**, we test whether the magnitude of the post-firing rebound depends on how *anticipated* the dismissal was. Under rational expectations, an expected firing should already be priced into team behaviour — leaving less room for a post-change improvement than a genuinely surprising one.

---

## Research Questions

1. **Does replacing a manager mid-season causally improve team performance** (measured in points per match)?
2. **Does the effect differ by manager nationality** — domestic (Turkish) vs. foreign replacements?
3. **Does anticipation matter?** Are the post-firing rebounds larger for *unexpected* dismissals (low pre-change media pressure) than expected ones?

---

## Key Findings

| Finding | Result |
|---------|--------|
| Average post-change effect (Base DiD, 30 seasons) | **−0.005 ppm, p = 0.90** — effectively zero |
| Pre-trend (mean reversion test) | Strong — all rw = −10 to −2 significant at p < 0.01 |
| Preferred spec (Team-Season + Week + Opp FE) | **+0.34 to +0.62 ppm, p < 0.001** — significant across all windows |
| Specification sensitivity | Base DiD: n.s. across all windows (±3 to ±10); Preferred spec: *** across all windows |
| Domestic vs. foreign replacement | Domestic: +0.60 ppm; Foreign: +0.46 ppm (differential θ not significant) |
| Anticipation hypothesis (2025–26 only, N = 10) | Directional — unexpected changes rebound more; no statistical power |

The headline result is that **on average, firing the manager does not measurably improve results**. The event-study reveals a strong pre-period pattern consistent with mean reversion: treated teams appear to outperform in the early pre-period relative to the firing week, simply because the firing week is a performance trough. Controlling for league standing does not resolve this pattern.

---

## Data

### Match Results
**Source:** [football-data.co.uk](https://www.football-data.co.uk/turkeym.php) — a free, publicly available archive of European football results. Files follow the URL pattern `https://www.football-data.co.uk/mmz4281/{SEASON_CODE}/T1.csv`. Downloaded manually season by season and stored on the `turkey-data` branch.

Coverage: 30 of 32 seasons (2002–03 and 2006–07 excluded due to source file parse errors). Each row is one match with full-time result, goals, and — for post-2017 seasons — shots, cards, and fouls.

| Era | Seasons | Content |
|-----|---------|---------|
| 1994/95–2000/01 | 7 seasons | Results + basic odds |
| 2001/02–2016/17 | 16 seasons | Results + full bookmaker odds |
| 2017/18–2025/26 | 7 seasons | Results + match stats (shots, cards, fouls) + extended odds |

### Manager Data
**Source:** [Transfermarkt](https://www.transfermarkt.com) — the most comprehensive structured database of football manager stints, with exact appointment and departure dates, nationalities, and career histories. Scraped programmatically via `managers/scrape_managers.py` and `managers/scrape_manager_profiles.py` (4-second delay between requests; Chrome User-Agent headers).

3,884 stints across 65 clubs. Club name inconsistencies between the two sources were resolved manually for all 65 clubs via `managers/team_mapping.csv`. Five 1990s-era clubs (e.g. A. Sebatspor, Oftasspor) have no Transfermarkt profile and are excluded from manager-level analyses.

### News & Expectations *(2025–26 season only)*
We built an original pre-change expectations measure from Turkish football news. No off-the-shelf dataset exists for this — the pipeline was designed and built from scratch for this project.

**Source 1 — Fotomaç RSS** (`fotomac.com.tr`): Turkey's leading football tabloid with team-specific RSS feeds for all Süper Lig clubs. Provides timely managerial rumour and criticism coverage in Turkish. Full article body retrievable via `trafilatura` scraping (101 articles, median 860 characters of body text).

**Source 2 — Google News RSS** (`news.google.com/rss`): Aggregates coverage from multiple Turkish and English-language outlets. Queried with 5 Turkish + 1 English search term per team (*teknik direktör, hoca ayrılık, istifa, görevden, manager*). Note: GDPR consent redirects block full-text retrieval for these articles — classification uses headline text only.

The pipeline then runs four steps:

- **Filtering**: 5,464 raw articles → 2,524 manager-relevant, via two-pass filter (manager name token matching + keyword regex with Turkish character normalisation)
- **Classification**: Each article scored 0–4 on an expectation-pressure scale using **Claude Haiku** (`claude-haiku-4-5-20251001`). The classifier was developed through an iterative human-in-the-loop validation process before any large-scale scoring was run:
  1. **Hand-labelling**: 10 articles were manually labelled by the team, deliberately spanning the full score range (confirmed resignation, fan protests, board criticism, routine quotes, appointment announcements)
  2. **Prompt v1**: Initial prompt submitted to Claude Haiku → reviewed against hand labels → identified systematic error: appointment articles (post-change) were scored 4 instead of 0
  3. **Prompt v2**: Added explicit rule — "appointment announcements score 0; they describe the post-change period, not pre-change pressure" → resubmitted → resolved appointment scoring; JSON parse failures remained
  4. **Prompt v3 (final)**: Added structured JSON output requirement and `is_relevant` flag → resubmitted → ≥ 90% score agreement (±1 tolerance), ≥ 80% `is_relevant` agreement → threshold met, scaled to all 2,524 articles

  Full prompt and validation details: [`news/prompt_classifier.md`](news/prompt_classifier.md), [`news/validation_interpretation.md`](news/validation_interpretation.md)

| Score | Label | Definition |
|-------|-------|------------|
| 0 | No signal | Routine content or post-change appointment coverage |
| 1 | Mild | Manager fielding departure questions, unresolved rumours |
| 2 | Moderate | Explicit board criticism; poor results blamed on manager |
| 3 | Strong | Fan protests, named replacements, credible board meetings |
| 4 | Confirmed | Firing or resignation explicitly confirmed |

- **Aggregation**: `out/expectations.csv` — one row per (team, ISO week) with `avg_grade` (mean normalised score over relevant articles) and `n_news`. The 1-week lagged value `exp_lag1` is used in regression to avoid same-week contamination.

---

## Empirical Strategy

### Unit of Observation
Each row is one team's performance in one match. A single fixture generates two rows (home team + away team). Treatment varies at the team-season level.

### Treatment Definition
A treatment event is a **mid-season manager dismissal** satisfying:
- Outgoing stint ≥ 14 days (excludes caretaker transitions)
- At least 3 pre-change matches in the same season
- Change falls within the season (not a summer appointment)

531 events identified across 30 seasons. `PostChange = 1` from the first match after the dismissal date.

### Event Window
±10 matches around the first post-change match (`relative_week` = 0). Never-treated team-seasons serve as the control group.

### Models

| Model | Specification | Purpose |
|-------|--------------|---------|
| M1 — Base DiD | Team FE + Season FE | Average post-change effect, all seasons |
| M2 — Event study | Team-season FE + Season-matchweek FE + Opponent FE | Preferred spec; tests parallel trends |
| M2_tp | M2 + table_position | Pre-trend diagnostic |
| M5 | M2 + PostChange × Domestic | Domestic vs. foreign heterogeneity |
| M4a | Points ~ PostChange + exp_lag1 + Home \| Team + matchweek | Continuous expectations, 2025–26 |
| M4c | Points ~ PostChange + PostChange × ExpectedChange + Home \| Team + matchweek | Binary anticipation split, 2025–26 |
| Spec × Window | 3 specs × 5 windows (±3/±5/±6/±8/±10) with binary post | Sensitivity: shows Base DiD n.s. always; preferred spec *** always |

---

## Repository Structure

```
brown-team-daai/
│
├── report.qmd                       # Main deliverable (Quarto source)
├── report.html                      # Rendered HTML report (self-contained)
│
├── data/                            # Match CSVs — turkey-data branch
│
├── managers/
│   ├── managers.csv                 # 3,884 coaching stints
│   ├── manager_profiles.csv         # 1,082 manager profiles
│   ├── manager_characteristics.csv  # Age & experience at appointment
│   ├── team_mapping.csv             # Name mapping: 65 clubs
│   ├── scrape_managers.py           # Scraper: manager stints
│   └── scrape_manager_profiles.py   # Scraper: profile enrichment
│
├── features/
│   ├── team_home_away.csv           # Home/away PPG, win rate, GD by season
│   └── team_location.csv            # Team → city → Turkish region
│
├── news/
│   ├── collect_rss.py               # RSS collection (Fotomaç + Google News)
│   ├── filter_manager_articles.py   # Two-pass relevance filter
│   ├── scrape_text.py               # Full-text scraper (Fotomaç)
│   ├── classify_articles.py         # Claude Haiku classification pipeline
│   ├── classify_validate.py         # Prompt validation (10 hand-labelled)
│   ├── build_expectations.py        # Aggregation → (team, week) panel
│   ├── prompt_classifier.md         # Full LLM prompt + scale definitions
│   ├── articles_raw.csv             # 5,464 raw RSS articles
│   ├── articles_managers.csv        # 2,524 manager-relevant articles
│   ├── articles_classified.csv      # + LLM scores and is_relevant flag
│   ├── hand_label_sample.csv        # 10 hand-labelled validation articles
│   └── validation_results.csv       # Human vs. LLM comparison
│
├── analysis/
│   ├── build_panel_full.py          # Builds out/panel_full.csv
│   ├── did_analysis.py              # Full econometric pipeline (M1–M7 + robustness)
│   ├── data_description.py          # Descriptive statistics
│   └── expectations_descriptive.py  # News panel diagnostics
│
├── out/
│   ├── panel_full.csv               # Full (team, match) panel — all seasons
│   ├── panel_full_events.csv        # Restricted ±10 window panel
│   ├── change_events.csv            # One row per treatment event
│   ├── expectations.csv             # (team, ISO week) → avg_grade, n_news
│   └── figures/                     # fig1–fig5 (event study, diagnostics, robustness)
│
├── tests/
│   └── test_data.py                 # 17 pytest data quality tests
│
├── PANEL.md                         # Panel design decisions (defended in report)
├── DATA.md                          # Full data schema for all tables
├── METHODS-AI.md                    # AI usage documentation (course requirement)
├── reflections.md                   # Individual reflections (course requirement)
├── week01.md                        # Session 1 write-up
└── week02.md                        # Session 2 write-up
```

---

## Reproducing the Analysis

All pre-processed panel data (`out/panel_full.csv`, `out/change_events.csv`, `out/expectations.csv`) and the classified news articles (`news/articles_classified.csv`) are committed to the repository. **No scraping or API calls are needed to reproduce the report.**

### Quickstart (recommended)
```bash
git clone https://github.com/HDuo1129/brown-team-daai.git
cd brown-team-daai
pip install pandas numpy matplotlib pyfixest
quarto render report.qmd       # → report.html (all figures and tables reproduced inline)
```

Or equivalently:
```bash
bash run.sh
```

Quarto 1.9+ and Python 3.12+ are required. Install Quarto from [quarto.org](https://quarto.org/docs/get-started/).

### Rebuilding the panel from raw match data (optional)
The match CSVs live on the `turkey-data` branch. Run the following only if you need to regenerate `out/panel_full.csv`:
```bash
git fetch origin turkey-data
python analysis/build_panel_full.py
python analysis/did_analysis.py   # saves standalone figures to out/figures/
```

### Re-running the news pipeline (optional)
The classified articles are committed as raw input. Re-running requires an `ANTHROPIC_API_KEY` and approximately 90 minutes of API time:
```bash
pip install anthropic feedparser trafilatura
export ANTHROPIC_API_KEY=sk-ant-...
python news/collect_rss.py
python news/filter_manager_articles.py
python news/scrape_text.py
python news/classify_validate.py   # validate on 10 hand-labelled articles first
python news/classify_articles.py
python news/build_expectations.py
```

---

## Known Limitations

1. **Parallel trends violation**: Mean reversion dominates the pre-period. Treated teams are selected on poor recent form, so the pre-period coefficients are mechanically positive relative to the firing-week trough. Controlling for league standing (`table_position`) does not resolve this.
2. **Missing seasons**: 2002–03 and 2006–07 excluded due to source CSV parse errors. 30/32 seasons covered.
3. **Unassigned matches**: 442 match-team rows (2.3%) have no Transfermarkt manager record — historical clubs no longer in the league. Excluded from manager-level analyses.
4. **Expectations layer — small sample**: Only 10 treated team-seasons in 2025–26. The anticipation analysis is exploratory only; no statistical inference should be drawn.
5. **Sparse news coverage**: 67% of team-weeks have zero articles, largely because Google News GDPR redirects block full-text retrieval. The expectations measure reflects headline-only content for 96% of articles.
6. **Staggered treatment**: Different teams are treated at different calendar times. A naive TWFE estimator may be biased under heterogeneous treatment effects (Callaway–Sant'Anna 2021). A full CS decomposition is left for future work.

---

## Project Documentation

| File | Purpose |
|------|---------|
| [`PANEL.md`](PANEL.md) | Design decisions for the analysis panel (unit, time index, treatment definition, window, imputation policy) |
| [`DATA.md`](DATA.md) | Full schema for all seven source and derived datasets |
| [`METHODS-AI.md`](METHODS-AI.md) | Documentation of AI tool usage across all three sessions (course requirement) |
| [`reflections.md`](reflections.md) | Individual reflections — one per team member (course requirement) |
| [`week01.md`](week01.md) | Session 1 write-up: data collection and feature engineering |
| [`week02.md`](week02.md) | Session 2 write-up: news collection, LLM classification, expectations panel |
