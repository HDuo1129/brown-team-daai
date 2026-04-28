# PANEL.md — Analysis Panel Design Decisions

All decisions recorded here must be defended in the presentation slides.

---

## 1. Unit of Observation

**Choice: `(team, match)`**

Each row is one team's performance in one league match. A single fixture generates two rows — one for the home team and one for the away team.

- Match results (points, goal difference) are the natural unit of football performance.
- Match-level granularity preserves the exact timing of each change relative to results.
- Each team plays ~34 matches per season → sufficient pre/post observations around each change.

---

## 2. Time Index

Two parallel indices are used:

| Index | Definition | Purpose |
|-------|-----------|---------|
| `match_date` | Calendar date of the match | Joining to expectations (ISO week) and manager stints |
| `event_time` | Match number relative to first match under new manager (0 = first post-change match, −1 = last pre-change match) | Event-study specification |
| `match_n` | Match sequence within the season for that team (1, 2, …, 34) | Within-season position control |

---

## 3. Entity Keys

| Entity | Key | Source |
|--------|-----|--------|
| Team | `football_data_name` / `team` | Consistent across `managers.csv`, `out/expectations.csv`, and `data/*.csv` — no mapping required for the 18 Süper Lig teams |
| Manager | `trainer_id` (Transfermarkt numeric ID) | `managers.csv` — unique across stints and managers |

---

## 4. Treatment Definition

**Treatment = a mid-season manager change.**

- A change is identified by the `end_date` of the outgoing manager's stint in `managers.csv`.
- `post = 1` starting from the first match played **after** the `end_date`.
- **Caretaker exclusion**: stints shorter than 14 days are excluded as caretaker appointments. These are organisational transitions, not strategic decisions whose effect we want to measure.
- **Summer appointments** (where a manager is replaced before the season starts) are not counted as treatment events — there is no within-season pre-period.
- **Minimum pre-period**: at least 3 matches under the outgoing manager must exist in the same season; otherwise the event is dropped (cannot estimate a pre-trend).

---

## 5. Pre / Post Window

**Choice: ±10 matches**

- 10 matches ≈ 10–12 weeks, covering roughly one-third of a season.
- Wide enough to see performance dynamics; narrow enough to avoid cross-season contamination.
- Teams with multiple changes in the same season: each change is treated as a separate event; matches are assigned to the nearest change event.
- The **restricted event panel** (`out/panel_full_events.csv`) keeps only rows within this window for the DiD and event-study regressions.

---

## 6. Missing Expectations Coverage Policy

Expectations data (`out/expectations.csv`) covers **only the 2025-26 season** (RSS window: 2025-W27 to 2026-W17).

| Situation | Treatment |
|-----------|-----------|
| 2025-26 match week where the team had ≥ 1 article | Use observed `avg_grade` (lagged 1 week) |
| 2025-26 match week where the team had 0 articles | Impute `exp_lag1 = 0.0` — zero news = genuine absence of pressure signal |
| Any match from seasons 1994–2025 | `exp_lag1 = NaN` — no RSS data exists; these rows enter the base DiD only |

**Lag**: the expectations variable is lagged by 1 ISO week relative to the match date (i.e., the signal from the week *before* the match). This avoids using same-week articles that may already report the firing.

**No median imputation for pre-RSS weeks**: the absence of data before 2025-W27 is structural (coverage gap), not random. Imputing with the 2025-26 median would inject look-ahead information.

---

## 7. Two-Layer Analysis Structure

| Layer | Sample | N changes | Expectation var? |
|-------|--------|-----------|-----------------|
| Base DiD | All seasons 1994–2026 (30 seasons) | 531 | No |
| Expectations heterogeneity | 2025-26 only (18 SL teams) | 20 | Yes (`exp_lag1`) |

The base DiD estimates the **average effect** of a mid-season manager change on points per match. The expectations layer tests whether that effect differs between **expected** (high pre-change `avg_grade`) and **unexpected** changes.

---

## 8. Outputs

| File | Description |
|------|-------------|
| `out/panel_full.csv` | Full (team, match) panel, all seasons, all teams |
| `out/panel_full_events.csv` | Restricted to ±10 match window around each change |
| `out/change_events.csv` | One row per treatment event with fire date and match positions |
| `out/panel.csv` | 2025-26 only panel (single-season version, kept for reference) |

---

## 9. Known Limitations

- **2 seasons missing** (2002-03, 2006-07): CSV parse errors in source files; 30/32 seasons covered.
- **442 unassigned matches** (2.3%): historical clubs with no Transfermarkt manager data — treated as missing and excluded from manager-level analyses.
- **5 control teams in 2025-26**: Alanyaspor, Galatasaray, Goztep, Kocaelispor, Trabzonspor. Small control group limits power for the single-season expectations analysis.
- **Staggered treatment**: different teams are treated at different calendar times within and across seasons. A naive two-way fixed effects estimator may be biased under heterogeneous treatment effects (Callaway–Sant'Anna 2021). We address this in the econometric specification.
