# Does Changing a Manager Improve Team Performance?
### Evidence from the Turkish Süper Lig, 1994–2026

**Team Brown — CEU | Course: Data Analysis with AI: Research Support**  
Duo Huang · Semih Tosun · Farangiz Jurakhonova

## 📄 [View Full Report](https://hduo1129.github.io/brown-team-daai/report.html)

---

## Research Question

Does replacing a manager mid-season causally improve team performance? And does the effect differ depending on whether the change was *anticipated* (high pre-change media pressure) or unexpected?

We answer these questions using 30 seasons of Süper Lig data (1994–2026), a difference-in-differences / event-study design, and an original LLM-based expectations measure built from Turkish football news.

---

## Key Findings

| Finding | Result |
|---------|--------|
| Average post-change effect (Base DiD) | **−0.005 ppm, p = 0.90** — effectively zero |
| Pre-trend (mean reversion) | Strong — all dm2–dm10 significant at p < 0.01 |
| Domestic vs. foreign replacement | Domestic: +0.60 ppm; Foreign: +0.46 ppm (θ not significant) |
| Anticipation hypothesis (2025–26 only) | Directional support — unexpected changes rebound more; N = 10, no statistical power |

---

## Repository Structure

```
brown-team-daai/
│
├── report.qmd                  # ← Main deliverable (Quarto source)
├── report.html                 # ← Rendered HTML report (self-contained)
│
├── data/                       # Match CSVs (turkey-data branch) — 30 seasons
│
├── managers/
│   ├── managers.csv            # 3,884 coaching stints (Transfermarkt)
│   ├── manager_profiles.csv    # 1,082 manager profiles (DOB, nationality)
│   ├── manager_characteristics.csv  # Age & experience at appointment
│   ├── team_mapping.csv        # football-data ↔ Transfermarkt name mapping (65 clubs)
│   ├── scrape_managers.py      # Scraper: manager history
│   └── scrape_manager_profiles.py   # Scraper: profile enrichment
│
├── features/
│   ├── team_home_away.csv      # Home/away PPG, win rate, GD by season × team
│   └── team_location.csv       # Team → city → Turkish regional category
│
├── news/
│   ├── collect_rss.py          # RSS collection (Fotomaç + Google News)
│   ├── filter_manager_articles.py   # Two-pass name + keyword filter
│   ├── scrape_text.py          # Full-text scraper (Fotomaç)
│   ├── classify_articles.py    # Claude Haiku classification pipeline
│   ├── classify_validate.py    # Prompt validation (10 hand-labelled articles)
│   ├── build_expectations.py   # Aggregates to (team, ISO week) panel
│   ├── prompt_classifier.md    # Full LLM prompt with scale & examples
│   ├── articles_raw.csv        # 5,464 raw RSS articles
│   ├── articles_managers.csv   # 2,524 manager-relevant articles
│   ├── articles_classified.csv # + LLM scores (0–4) and is_relevant flag
│   ├── hand_label_sample.csv   # 10 hand-labelled articles for validation
│   └── validation_results.csv  # Human vs. LLM comparison
│
├── analysis/
│   ├── build_panel_full.py     # Builds out/panel_full.csv from all seasons
│   ├── did_analysis.py         # Full econometric pipeline (M1–M7 + robustness)
│   ├── data_description.py     # Descriptive stats
│   └── expectations_descriptive.py  # News panel diagnostics
│
├── out/
│   ├── panel_full.csv          # Full (team, match) panel — all seasons
│   ├── panel_full_events.csv   # Restricted ±10 window panel
│   ├── change_events.csv       # One row per treatment event
│   ├── expectations.csv        # (team, ISO week) → avg_grade, n_news
│   └── figures/                # All output figures (fig1–fig5)
│
├── tests/
│   └── test_data.py            # 17 pytest data + code tests
│
├── PANEL.md                    # Analysis panel design decisions
├── DATA.md                     # Full data schema
├── METHODS-AI.md               # AI usage documentation (course requirement)
├── reflections.md              # Individual reflections (course requirement)
├── week01.md                   # Session 1 write-up
└── week02.md                   # Session 2 write-up
```

---

## Data Sources

| Source | What we get | Coverage |
|--------|-------------|----------|
| [football-data.co.uk](https://www.football-data.co.uk/turkeym.php) | Match results (FTHG, FTAG, FTR, odds, shots) | 1994–2026, 30 seasons |
| [Transfermarkt](https://www.transfermarkt.com) | Manager stints, profiles, nationality, age | 3,884 stints, 1,082 managers |
| Fotomaç RSS + Google News RSS | Turkish football manager news | 2025-W27 to 2026-W17 |

---

## Analysis Pipeline

### Session 1 — Data Collection & Feature Engineering
- Downloaded 30 seasons of Süper Lig match results
- Scraped Transfermarkt for all manager stints (3,884) and profiles (1,082)
- Resolved 65 club name inconsistencies between sources
- Built home/away performance features and team location table
- 17 pytest data quality tests, all passing

### Session 2 — News Collection & LLM Classification
- Collected 5,464 RSS articles across 18 teams via Fotomaç + Google News
- Filtered to 2,524 manager-relevant articles (name + keyword two-pass filter)
- Classified all articles with **Claude Haiku** (`claude-haiku-4-5-20251001`) on a 0–4 expectation-pressure scale
- Validated against 10 hand-labelled articles (≥ 80% agreement) before scaling
- Produced `out/expectations.csv`: 506 rows × (team, ISO week)

### Session 3 — Panel Construction & Econometric Analysis
- Built full (team, match) panel across all 30 seasons
- Identified 531 mid-season treatment events; defined ±10 match event window
- Estimated Base DiD (M1), preferred event-study (M2), heterogeneity (M5, M7), and anticipation models (M4a/4c)
- Pre-trend confirmed as mean reversion; `table_position` control does not resolve it
- Full results and robustness checks in [`report.html`](https://hduo1129.github.io/brown-team-daai/report.html)

---

## Econometric Specifications

**Base DiD:**
$$\text{Points}_{it} = \alpha_i + \mu_s + \beta \cdot \text{PostChange}_{it} + \gamma \cdot \text{Home}_{it} + \delta \cdot \text{OppStrength}_{it} + \varepsilon_{it}$$

**Preferred Event-Study (M2):**
$$\text{Points}_{it} = \alpha_{is} + \lambda_{sw} + \delta_o + \sum_{k \neq -1} \beta_k \cdot \mathbf{1}[\text{rw}_{it}=k] + \gamma \cdot \text{Home}_{it} + \delta \cdot \text{OppStrength}_{it} + \varepsilon_{it}$$

Fixed effects: team-season + season-matchweek + opponent. SE clustered by team.

---

## Known Limitations

1. **Parallel trends violation** — mean reversion dominates the pre-period; causal interpretation is limited
2. **2 seasons missing** (2002–03, 2006–07) — source file parse errors; 30/32 seasons covered
3. **442 unassigned matches** (2.3%) — historical clubs with no Transfermarkt data
4. **Expectations layer N = 10** — single-season sample lacks statistical power
5. **Sparse news coverage** — 67% of team-weeks have zero articles (Google News GDPR blocks full-text)
6. **Staggered treatment** — TWFE may be biased under heterogeneous effects (Callaway–Sant'Anna 2021)
