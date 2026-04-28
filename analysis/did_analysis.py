"""
analysis/did_analysis.py
=========================
Event-study DiD: Does changing a manager improve team performance?
Turkish Süper Lig, 1994–2026

METHODOLOGICAL NOTES
- Unit: team-season (treatment resets across seasons → no cross-season contamination)
- Team-season FE absorb all time-invariant team-season quality
- Season-week FE absorb common shocks within each matchweek of a season
- Opponent FE control for fixture strength beyond the running points tally
- Standard TWFE can be biased under staggered, heterogeneous treatment;
  see robustness checks
- In-game controls (shots, cards) are post-treatment mechanisms — NOT used in
  the main causal specification
- Expectation variables (exp_lag1, expected_change) are 2025-26 only and
  are analysed in a separate subsample model

Usage:
    python analysis/did_analysis.py
"""
import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import pyfixest as pf
from pathlib import Path

ROOT    = Path(__file__).parent.parent
OUT_DIR = ROOT / "out"
(OUT_DIR / "tables").mkdir(parents=True, exist_ok=True)
(OUT_DIR / "figures").mkdir(parents=True, exist_ok=True)

EVENT_WIN = 10          # ±10 matchweeks around the change
THRESHOLD  = 0.5        # avg_grade cut-off for expected_change

# ── 1. Load data ──────────────────────────────────────────────────────────────
print("Loading data...")
panel    = pd.read_csv(ROOT / "out" / "panel_full.csv",  parse_dates=["match_date"])
changes  = pd.read_csv(ROOT / "out" / "change_events.csv")
mgr_char = pd.read_csv(ROOT / "managers" / "manager_characteristics.csv",
                        parse_dates=["start_date", "end_date"])
team_ha  = pd.read_csv(ROOT / "features" / "team_home_away.csv")
team_loc = pd.read_csv(ROOT / "features" / "team_location.csv")

# ── 2. Clean panel (drop Python-computed event vars; recompute cleanly) ───────
drop_cols = [c for c in ["event_time","change_index","fire_date",
                          "manager_out","post"] if c in panel.columns]
panel = panel.drop(columns=drop_cols)

# ── 3. Team-season identifier ─────────────────────────────────────────────────
panel["team_season"]   = panel["team"] + "__" + panel["season"]
changes["team_season"] = changes["team"] + "__" + changes["season"]

# ── 4. First in-season manager change per team-season ────────────────────────
first_ch = (
    changes.sort_values("first_post_n")
    .groupby("team_season", as_index=False)
    .first()[["team_season", "first_post_n"]]
)

# ── 5. Merge treatment timing ─────────────────────────────────────────────────
panel = panel.merge(first_ch, on="team_season", how="left")

panel["PostChange"]    = ((panel["first_post_n"].notna()) &
                          (panel["match_n"] >= panel["first_post_n"])).astype(int)
panel["relative_week"] = np.where(
    panel["first_post_n"].notna(),
    panel["match_n"] - panel["first_post_n"],
    np.nan
)

# ── 6. Build the event panel ──────────────────────────────────────────────────
# Keep: treated observations within ±10 window  OR  all never-treated controls
mask_treated = panel["relative_week"].notna() & \
               panel["relative_week"].between(-EVENT_WIN, EVENT_WIN)
mask_control = panel["relative_week"].isna()
panel_ev = panel[mask_treated | mask_control].copy()

# For pyfixest event-study: never-treated → rw = -999 (stays out of i() dummies)
panel_ev["rw"] = panel_ev["relative_week"].fillna(-999).astype(int)

# Season-week FE
panel_ev["season_week"] = (panel_ev["season"] + "_W" +
                            panel_ev["match_n"].astype(str).str.zfill(2))

# ── 7. Opponent strength ──────────────────────────────────────────────────────
# Cumulative league points BEFORE each match (lagged running total per team-season)
# Join on (opponent, season, match_date) — match_n differs across teams for the
# same fixture, so match_date is the safe key.
panel_sorted = panel.sort_values(["team", "season", "match_date"])
panel_sorted["cum_pts_before"] = (
    panel_sorted.groupby(["team", "season"])["points"]
    .cumsum()
    .shift(1, fill_value=0)
)
opp_str = panel_sorted[["team", "season", "match_date", "cum_pts_before"]].rename(
    columns={"team": "opponent", "cum_pts_before": "opponent_strength"}
)
panel_ev = panel_ev.merge(opp_str, on=["opponent", "season", "match_date"], how="left")

# ── 8. is_foreign (current manager nationality) ───────────────────────────────
TURKISH = {"Türkiye", "Turkey", "Turkish", "Türk", "Turkiye"}
panel_ev["is_foreign"] = (~panel_ev["nationality"].isin(TURKISH) &
                           panel_ev["nationality"].notna()).astype(int)

# ── 9. NewManagerDomestic (nationality of the INCOMING manager) ───────────────
new_mgr = (
    panel_ev[panel_ev["PostChange"] == 1]
    .sort_values("relative_week")
    .groupby("team_season")["nationality"]
    .first()
    .reset_index()
    .rename(columns={"nationality": "new_mgr_nat"})
)
panel_ev = panel_ev.merge(new_mgr, on="team_season", how="left")
panel_ev["NewManagerDomestic"] = panel_ev["new_mgr_nat"].isin(TURKISH).astype(int)
panel_ev.loc[panel_ev["new_mgr_nat"].isna(), "NewManagerDomestic"] = np.nan

# ── 10. Manager experience (join per stint: trainer_id × team) ────────────────
mgr_xp = (
    mgr_char[["trainer_id", "football_data_name",
               "experience_clubs_before", "experience_years_before"]]
    .rename(columns={"football_data_name": "team"})
    .drop_duplicates(subset=["trainer_id", "team"])
)
panel_ev = panel_ev.merge(mgr_xp, on=["trainer_id", "team"], how="left")

# ── 11. Previous-season team stats ───────────────────────────────────────────
# NOTE: constant within team-season → collinear with team-season FE.
# Useful only when using team + season FE instead (models m3_alt, m_r_twfe).
team_ha["ppg"] = (
    (team_ha["home_points"] + team_ha["away_points"]) /
    (team_ha["home_games"]  + team_ha["away_games"])
)
# Build "season this follows" key, e.g. "2019-2020" → used by "2020-2021"
team_ha["next_season"] = team_ha["season"].str[:4].astype(int).add(1).astype(str) + \
                          "-" + team_ha["season"].str[:4].astype(int).add(2).astype(str)
prev_stats = team_ha[["team", "next_season", "ppg", "home_away_gap"]].rename(
    columns={"next_season": "season",
             "ppg":         "prev_season_ppg",
             "home_away_gap": "prev_home_away_gap"}
)
panel_ev = panel_ev.merge(prev_stats, on=["team", "season"], how="left")

# ── 12. Geographic region ─────────────────────────────────────────────────────
panel_ev = panel_ev.merge(
    team_loc[["football_data_name", "region"]].rename(
        columns={"football_data_name": "team"}),
    on="team", how="left"
)

# ── 13. expected_change (2025-26 only) ───────────────────────────────────────
# mean exp_lag1 in the four pre-change matchweeks; binary ≥ THRESHOLD
exp_thr = (
    panel_ev[
        (panel_ev["season"] == "2025-2026") &
        panel_ev["relative_week"].notna() &
        panel_ev["relative_week"].between(-4, -1)
    ]
    .groupby("team_season")["exp_lag1"]
    .mean()
    .rename("pre_avg_grade")
    .reset_index()
)
exp_thr["expected_change"] = (exp_thr["pre_avg_grade"] >= THRESHOLD).astype(int)
panel_ev = panel_ev.merge(exp_thr[["team_season", "expected_change"]],
                           on="team_season", how="left")

# ── 14. Additional outcomes ───────────────────────────────────────────────────
panel_ev["win"]  = (panel_ev["points"] == 3).astype(int)
panel_ev["loss"] = (panel_ev["points"] == 0).astype(int)

# ── 15. Explicit event-time dummies ──────────────────────────────────────────
# Using C(rw_factor) with NaN drops never-treated rows, which breaks season-week
# FE identification.  Instead, create 0/1 dummies: control units get 0 on all
# dummies (contribute to FE identification without firing any treatment dummy).
RW_VALS = [k for k in range(-EVENT_WIN, EVENT_WIN + 1) if k != -1]

def rw_colname(k):
    """Convert event-time int to a valid column name (no leading minus)."""
    return f"dm{abs(k)}" if k < 0 else f"dp{k}"

for k in RW_VALS:
    panel_ev[rw_colname(k)] = (panel_ev["rw"] == k).astype(int)
ES_TERMS = " + ".join(rw_colname(k) for k in RW_VALS)

# ── 16. Encode FE columns as strings ─────────────────────────────────────────
for col in ["team_season", "season_week", "opponent", "team", "season"]:
    panel_ev[col] = panel_ev[col].astype(str)

n_treated = panel_ev[panel_ev["relative_week"].notna()]["team_season"].nunique()
n_control = panel_ev[panel_ev["relative_week"].isna()]["team_season"].nunique()
print(f"Panel ready: {len(panel_ev):,} rows | "
      f"{n_treated} treated team-seasons | {n_control} control team-seasons")

# =============================================================================
# HELPER: event-study coefficient extractor
# =============================================================================
def get_es_coefs(fit):
    """Return DataFrame of event-study coefficients (dm/dp dummies) from a pyfixest fit."""
    coef = fit.coef(); se = fit.se()
    rows = []
    for col in coef.index:
        if col.startswith("dm"):
            rw = -int(col[2:])
        elif col.startswith("dp"):
            rw = int(col[2:])
        else:
            continue
        rows.append({"rw": rw, "estimate": coef[col], "se": se[col]})
    rows.append({"rw": -1, "estimate": 0.0, "se": 0.0})   # reference
    return pd.DataFrame(rows).sort_values("rw")

# =============================================================================
# MODEL 1 — Base DiD
# Y = α_i + μ_s + β PostChange + γ home + γ opp_strength + ε
# =============================================================================
print("\nFitting Model 1 — Base DiD...")
m1 = pf.feols(
    "points ~ PostChange + home + opponent_strength | team + season",
    data    = panel_ev[panel_ev["PostChange"].notna()],
    vcov    = {"CRV1": "team"}
)
print(m1.summary())

# =============================================================================
# MODEL 2 — Preferred Event-Study
# Y = α_is + λ_sw + δ_o + Σ β_k C(rw)[T.k] + γ home + γ opp_strength + ε
# Reference period: rw = -1.  rw = -999 for never-treated → no dummy fires.
# =============================================================================
print("\nFitting Model 2 — Preferred Event-Study...")
m2 = pf.feols(
    f"points ~ {ES_TERMS} + home + opponent_strength"
    " | team_season + season_week + opponent",
    data    = panel_ev,
    vcov    = {"CRV1": "team"}
)
print(m2.summary())

# =============================================================================
# MODEL 3 — Extended Controls
# prev_season_ppg / prev_home_away_gap are constant within team-season,
# so they are collinear with team-season FE and dropped in m3_ts.
# m3_alt uses team + season FE to retain their identification.
# =============================================================================
print("\nFitting Model 3 — Extended Controls...")
m3_ts = pf.feols(
    f"points ~ {ES_TERMS} + home + opponent_strength"
    " + prev_season_ppg + prev_home_away_gap"
    " | team_season + season_week + opponent",
    data  = panel_ev,
    vcov  = {"CRV1": "team"}
)
m3_alt = pf.feols(
    "points ~ PostChange + home + opponent_strength"
    " + prev_season_ppg + prev_home_away_gap"
    " | team + season + opponent",
    data  = panel_ev[panel_ev["PostChange"].notna()],
    vcov  = {"CRV1": "team"}
)

# =============================================================================
# MODEL 4 — Anticipation Model (2025-26 only)
# β = average effect; in m4c: β = unexpected effect, β+θ = expected effect
# =============================================================================
print("\nFitting Model 4 — Anticipation (2025-26)...")
p26 = panel_ev[panel_ev["season"] == "2025-2026"].copy()

m4a = pf.feols(
    "points ~ PostChange + exp_lag1 + home + opponent_strength | team + match_n",
    data  = p26[p26["PostChange"].notna() & p26["exp_lag1"].notna()],
    vcov  = {"CRV1": "team"}
)
m4b = pf.feols(
    "points ~ PostChange + expected_change + home + opponent_strength | team + match_n",
    data  = p26[p26["PostChange"].notna() & p26["expected_change"].notna()],
    vcov  = {"CRV1": "team"}
)
m4c = pf.feols(
    "points ~ PostChange + PostChange:expected_change + home + opponent_strength | team + match_n",
    data  = p26[p26["PostChange"].notna() & p26["expected_change"].notna()],
    vcov  = {"CRV1": "team"}
)
beta   = m4c.coef()["PostChange"]
theta  = m4c.coef()["PostChange:expected_change"]
print(f"  β (unexpected): {beta:.4f} | θ: {theta:.4f} | β+θ (expected): {beta+theta:.4f}")

# =============================================================================
# MODEL 5 — Domestic Manager Heterogeneity
# β = effect of foreign replacement; β+θ = effect of domestic replacement
# =============================================================================
print("\nFitting Model 5 — Domestic vs Foreign Heterogeneity...")
d5 = panel_ev[panel_ev["NewManagerDomestic"].notna()].copy()
d5["NMD"] = d5["NewManagerDomestic"].astype(float)
m5 = pf.feols(
    "points ~ PostChange + PostChange:NMD + home + opponent_strength"
    " | team_season + season_week + opponent",
    data  = d5,
    vcov  = {"CRV1": "team"}
)
b = m5.coef()["PostChange"]
t = m5.coef()["PostChange:NMD"]
print(f"  β (foreign): {b:.4f} | θ (domestic Δ): {t:.4f} | β+θ (domestic): {b+t:.4f}")

# =============================================================================
# MODEL 6 — Other Manager-Characteristic Heterogeneity
# =============================================================================
print("\nFitting Model 6 — Other heterogeneity...")

def het_model(interact_var, data=panel_ev):
    d = data[data[interact_var].notna()].copy()
    d["_x"] = d[interact_var].astype(float)
    return pf.feols(
        "points ~ PostChange + PostChange:_x + home + opponent_strength"
        " | team_season + season_week + opponent",
        data=d, vcov={"CRV1": "team"}
    )

m6_for   = het_model("is_foreign")
m6_age   = het_model("age_at_appointment")
m6_clubs = het_model("experience_clubs_before")
m6_yrs   = het_model("experience_years_before")

# =============================================================================
# MODEL 7 — Domestic vs Foreign: Separate Event-Studies
# =============================================================================
print("\nFitting Model 7 — Separate event-studies by manager origin...")

def ev_model(data_mask):
    d = panel_ev[data_mask].copy()
    return pf.feols(
        f"points ~ {ES_TERMS} + home + opponent_strength"
        " | team_season + season_week + opponent",
        data=d, vcov={"CRV1": "team"}
    )

no_change = panel_ev["relative_week"].isna()
m7_dom = ev_model(no_change | (panel_ev["NewManagerDomestic"] == 1))
m7_for = ev_model(no_change | (panel_ev["NewManagerDomestic"] == 0))

# =============================================================================
# ROBUSTNESS CHECKS
# =============================================================================
print("\nFitting robustness checks...")

# R1: team-seasons with exactly one change
n_ch      = changes.groupby("team_season").size().rename("n_changes").reset_index()
single_ts = set(n_ch[n_ch["n_changes"] == 1]["team_season"])
m_r1 = pf.feols(
    f"points ~ {ES_TERMS} + home + opponent_strength"
    " | team_season + season_week + opponent",
    data  = panel_ev[no_change | panel_ev["team_season"].isin(single_ts)],
    vcov  = {"CRV1": "team"}
)

# R2: alternative outcomes
m_r_out = {}
for y in ["win", "goal_diff", "gf", "ga"]:
    m_r_out[y] = pf.feols(
        f"{y} ~ {ES_TERMS} + home + opponent_strength"
        " | team_season + season_week + opponent",
        data=panel_ev, vcov={"CRV1": "team"}
    )

# R3: narrower windows
def window_model(w):
    terms_w = " + ".join(rw_colname(k) for k in range(-w, w+1) if k != -1)
    d = panel_ev[no_change | panel_ev["relative_week"].between(-w, w)].copy()
    return pf.feols(
        f"points ~ {terms_w} + home + opponent_strength"
        " | team_season + season_week + opponent",
        data=d, vcov={"CRV1": "team"}
    )

m_r6 = window_model(6)
m_r8 = window_model(8)

# R4: TWFE (team + season FE) vs preferred — compare coefficients
m_r_twfe = pf.feols(
    "points ~ PostChange + home + opponent_strength"
    " + prev_season_ppg + prev_home_away_gap | team + season",
    data  = panel_ev[panel_ev["PostChange"].notna()],
    vcov  = {"CRV1": "team"}
)

print("All models estimated.\n")

# =============================================================================
# TABLES (pyfixest etable)
# =============================================================================
print("Saving tables...")

pf.etable([m1, m2, m3_ts, m3_alt],
          labels={"PostChange": "Post Change",
                  "home": "Home",
                  "opponent_strength": "Opp. Strength (cum pts)",
                  "prev_season_ppg": "Prev Season PPG",
                  "prev_home_away_gap": "Prev Home-Away Gap"},
          type="tex",
          file=str(OUT_DIR / "tables" / "table1_main.tex"))

pf.etable([m5, m6_for, m6_age, m6_clubs, m6_yrs],
          type="tex",
          file=str(OUT_DIR / "tables" / "table2_heterogeneity.tex"))

pf.etable([m4a, m4b, m4c],
          type="tex",
          file=str(OUT_DIR / "tables" / "table3_anticipation.tex"))

pf.etable([m2, m_r1, m_r6, m_r8, m_r_twfe],
          type="tex",
          file=str(OUT_DIR / "tables" / "table4_robustness.tex"))

pf.etable([m2, m_r_out["win"], m_r_out["goal_diff"],
                m_r_out["gf"], m_r_out["ga"]],
          type="tex",
          file=str(OUT_DIR / "tables" / "table5_outcomes.tex"))

print("Tables saved to out/tables/")

# =============================================================================
# FIGURES
# =============================================================================
print("Saving figures...")

def plot_es(fit, title, path, window=EVENT_WIN):
    """Plot event-study coefficients with 95% CI from a pyfixest model."""
    df  = get_es_coefs(fit)
    df  = df[df["rw"].between(-window, window)]
    rws = df["rw"].tolist()
    est = df["estimate"].tolist()
    err = (df["se"] * 1.96).tolist()

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.axhline(0, color="grey", lw=0.8, ls="--")
    ax.axvline(-0.5, color="grey", lw=0.8, ls="--")
    ax.errorbar(rws, est, yerr=err, fmt="o-", color="#2166ac",
                capsize=3, lw=1.4, ms=4, elinewidth=0.9)
    ax.set_xlabel("Matchweeks Relative to Manager Change", fontsize=11)
    ax.set_ylabel("Effect on Points per Match", fontsize=11)
    ax.set_title(title, fontsize=12)
    ax.xaxis.set_major_locator(mticker.MultipleLocator(2))
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"  Saved: {path}")

# Figure 1: Main event-study
plot_es(m2,
        "Event-Study: Effect of Manager Change on Points per Match\n"
        "(Team-season FE + Season-week FE + Opponent FE, clustered by team)",
        OUT_DIR / "figures" / "fig1_event_study_main.png")

# Figure 2: Domestic vs Foreign
def extract_es_df(fit, label):
    df = get_es_coefs(fit)
    df["group"] = label
    return df

es_dom = extract_es_df(m7_dom, "Domestic (Turkish) manager")
es_for = extract_es_df(m7_for, "Foreign manager")
es_df  = pd.concat([es_dom, es_for]).sort_values(["group", "rw"])

fig, ax = plt.subplots(figsize=(10, 5.5))
colors = {"Domestic (Turkish) manager": "#2166ac", "Foreign manager": "#d6604d"}
for grp, gdf in es_df.groupby("group"):
    gdf = gdf.sort_values("rw")
    ax.fill_between(gdf["rw"],
                    gdf["estimate"] - 1.96 * gdf["se"],
                    gdf["estimate"] + 1.96 * gdf["se"],
                    alpha=0.12, color=colors[grp])
    ax.plot(gdf["rw"], gdf["estimate"], "o-", label=grp,
            color=colors[grp], lw=1.6, ms=4.5)
ax.axhline(0, color="grey", lw=0.8, ls="--")
ax.axvline(-0.5, color="grey", lw=0.8, ls="--")
ax.set_xlabel("Matchweeks Relative to Manager Change", fontsize=11)
ax.set_ylabel("Effect on Points per Match", fontsize=11)
ax.set_title("Manager Change: Domestic vs Foreign New Manager\n"
             "95% CI, SEs clustered at team level", fontsize=12)
ax.xaxis.set_major_locator(mticker.MultipleLocator(2))
ax.legend(fontsize=10)
fig.tight_layout()
fig.savefig(OUT_DIR / "figures" / "fig2_domestic_foreign.png", dpi=150)
plt.close(fig)
print(f"  Saved: {OUT_DIR / 'figures' / 'fig2_domestic_foreign.png'}")

# Figure 3: Alternative outcomes
fig, axes = plt.subplots(2, 2, figsize=(12, 8), sharex=True)
for ax, (y, label) in zip(axes.flat,
                           [("win","Win rate"),("goal_diff","Goal diff"),
                            ("gf","Goals for"),("ga","Goals against")]):
    df  = get_es_coefs(m_r_out[y])
    rws = df["rw"].tolist()
    est = df["estimate"].tolist()
    err = (df["se"] * 1.96).tolist()
    ax.axhline(0, color="grey", lw=0.7, ls="--")
    ax.axvline(-0.5, color="grey", lw=0.7, ls="--")
    ax.errorbar(rws, est, yerr=err, fmt="o-", color="#4dac26",
                capsize=2, lw=1.2, ms=3)
    ax.set_title(label, fontsize=11)
    ax.xaxis.set_major_locator(mticker.MultipleLocator(4))
fig.suptitle("Event-Study: Alternative Outcomes (preferred FE)", fontsize=12)
fig.tight_layout()
fig.savefig(OUT_DIR / "figures" / "fig3_alt_outcomes.png", dpi=150)
plt.close(fig)
print(f"  Saved: {OUT_DIR / 'figures' / 'fig3_alt_outcomes.png'}")

# Figure 4: Event-window robustness
fig, ax = plt.subplots(figsize=(10, 5))
for fit, label, color, win in [
    (m2,    "±10 (preferred)", "#2166ac", 10),
    (m_r8,  "±8",              "#4dac26", 8),
    (m_r6,  "±6",              "#d6604d", 6),
]:
    df  = get_es_coefs(fit)
    df  = df[df["rw"].between(-win, win)]
    rws = df["rw"].tolist()
    est = df["estimate"].tolist()
    err = (df["se"] * 1.96).tolist()
    ax.errorbar(rws, est, yerr=err, fmt="o-", label=label,
                color=color, capsize=2, lw=1.3, ms=3.5, alpha=0.85)
ax.axhline(0, color="grey", lw=0.8, ls="--")
ax.axvline(-0.5, color="grey", lw=0.8, ls="--")
ax.set_xlabel("Matchweeks Relative to Manager Change", fontsize=11)
ax.set_ylabel("Effect on Points per Match", fontsize=11)
ax.set_title("Robustness: Alternative Event Windows", fontsize=12)
ax.xaxis.set_major_locator(mticker.MultipleLocator(2))
ax.legend(fontsize=10)
fig.tight_layout()
fig.savefig(OUT_DIR / "figures" / "fig4_robustness_windows.png", dpi=150)
plt.close(fig)
print(f"  Saved: {OUT_DIR / 'figures' / 'fig4_robustness_windows.png'}")

print("\n=== Done. Tables → out/tables/   Figures → out/figures/ ===")
