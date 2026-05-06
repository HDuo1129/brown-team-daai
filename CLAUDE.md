# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Turkish Süper Lig manager-change study (1994–2026). The main deliverable is `report.html`, rendered from `report.qmd` (Quarto + Python). All econometric analysis runs inside the `.qmd` at render time — there is no separate "run analysis" step for the report.

## Commands

### Full pipeline (data → analysis → report)
```bash
# 1. Rebuild the analysis panel (requires match CSVs on the turkey-data branch)
python analysis/build_panel_full.py

# 2. Run standalone econometric analysis + save figures to out/figures/
python analysis/did_analysis.py

# 3. Render the self-contained HTML report
quarto render report.qmd
```

### Tests
```bash
pytest tests/test_data.py -v             # 17 structural data quality tests
python tests/test_data.py --describe     # coverage statistics (no pytest needed)
```

### News pipeline (2025-26 only, run in order)
```bash
python news/collect_rss.py               # → news/articles_raw.csv
python news/filter_manager_articles.py   # → news/articles_managers.csv
python news/scrape_text.py               # → news/articles_text.csv (Fotomaç full text)
python news/classify_articles.py         # → news/articles_classified.csv
python news/build_expectations.py        # → out/expectations.csv
```

## Architecture

### Match data lives on a separate git branch
Raw match CSVs are on `origin/turkey-data` (not `main`). `build_panel_full.py` reads them via `git show origin/turkey-data:data/<file>.csv` using `subprocess`. Never commit match CSVs to `main`.

### Two-stage panel construction
1. `analysis/build_panel_full.py` — joins match results (from `turkey-data` branch) with manager stints (`managers/managers.csv`) to produce `out/panel_full.csv` (all seasons, all teams) and `out/panel_full_events.csv` (restricted to ±10 match window around each treatment event).
2. `analysis/did_analysis.py` — reads the `out/` CSVs and runs all models (M1–M7 + robustness), saving figures to `out/figures/`.
3. `report.qmd` — re-runs all regressions inline at render time; it does **not** load pre-saved model objects. Figures are regenerated from scratch on each render.

### Key identifiers and joins
- **Club names**: 65 historical name variants across sources. `managers/team_mapping.csv` maps both `football_data_name` (football-data.co.uk) and `transfermarkt_name` to a canonical name. Always join through this mapping.
- **Manager key**: `trainer_id` (Transfermarkt numeric ID) — unique across stints and managers.
- **Team-season key**: constructed as `team + "__" + season` (e.g. `"Galatasaray__2024-25"`). Used as the FE absorber in the preferred specification.

### Treatment definition (see PANEL.md for full rationale)
A mid-season change is included only if: (a) the outgoing stint ≥ 14 days (caretaker exclusion), (b) ≥ 3 pre-change matches exist in the same season, (c) the change falls within the season (not a summer appointment). `PostChange = 1` from the first match after `end_date`. 531 events across 30 seasons.

### Econometric specifications
| Label | Formula (pyfixest feols) |
|-------|--------------------------|
| Base DiD (M1) | `points ~ PostChange + home \| team + season` |
| Preferred (M2) | `points ~ post + home + opponent_strength \| team_season + season_week + opponent` |
| Event study | `points ~ i(relative_week, ref=-1) + home + opponent_strength \| team_season + season_week + opponent` |

The preferred spec uses `team_season` FE (not `team`) because season FE is too coarse to absorb within-season mean reversion. In-game controls (shots, cards, fouls) are post-treatment mechanisms and must **not** be added to causal specifications.

### Expectations layer
`out/expectations.csv` covers 2025-26 only. It is merged onto the panel via (team, ISO week). The variable used in regressions is `exp_lag1` — a 1-week lag to avoid same-week contamination. The `expected_change` binary threshold is computed dynamically as the median of `pre_avg_grade` across treated team-seasons (N=10); it is **not** hardcoded.

### Known data gaps
- 2002-03 and 2006-07 seasons excluded (CSV parse errors in source files)
- 442 match-team rows (2.3%) have no Transfermarkt manager record — excluded from manager-level analyses
- `news/classify_articles.py` docstring references Groq/LLaMA (legacy draft); production classification used `claude-haiku-4-5-20251001` via the Anthropic API
