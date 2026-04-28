"""
analysis/estimate_did.py
Turkish Süper Lig — Manager Change & Performance
DiD / event-study estimation pipeline

Requirements:
    pip install pyfixest pandas matplotlib

pyfixest uses nearly identical formula syntax to R fixest:
    pf.feols("y ~ x | fe1^fe2 + fe3", data=df, vcov={"CRV1": "team"})
"""

# ── 0. IMPORTS AND SETUP ──────────────────────────────────────────────────────
from pathlib import Path
import re
import warnings
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import pyfixest as pf

warnings.filterwarnings("ignore")

ROOT = Path(__file__).parent.parent
OUT  = ROOT / "out"
OUT.mkdir(exist_ok=True)

# ── 1. LOAD DATA ──────────────────────────────────────────────────────────────
panel    = pd.read_csv(ROOT / "out/panel_full.csv",
                       parse_dates=["match_date", "fire_date"])
changes  = pd.read_csv(ROOT / "out/change_events.csv",
                       parse_dates=["fire_date"])
exp_raw  = pd.read_csv(ROOT / "out/expectations.csv")
team_ha  = pd.read_csv(ROOT / "features/team_home_away.csv")
mgr_char = pd.read_csv(ROOT / "managers/manager_characteristics.csv",
                        parse_dates=["start_date", "end_date"])

mgr_char = mgr_char.rename(columns={"football_data_name": "team"})

# Goals are stored as floats; convert to nullable integer
panel["gf"] = pd.to_numeric(panel["gf"], errors="coerce").astype("Int64")
panel["ga"] = pd.to_numeric(panel["ga"], errors="coerce").astype("Int64")


# ── 2. FEATURE ENGINEERING ────────────────────────────────────────────────────

# ── 2.1  Opponent strength: cumulative points of opponent BEFORE this match ────
# One row per (team, match) → cumsum within (team, season) is correct.
panel = panel.sort_values(["team", "season", "match_date"]).reset_index(drop=True)
panel["cum_pts_before"] = (
    panel.groupby(["team", "season"])["points"].cumsum() - panel["points"]
)
opp_lookup = (
    panel[["team", "season", "match_date", "cum_pts_before"]]
    .rename(columns={"team": "opponent", "cum_pts_before": "opponent_strength"})
)
panel = panel.merge(opp_lookup, on=["opponent", "season", "match_date"], how="left")

# ── 2.2  Previous-season team quality ─────────────────────────────────────────
def season_year(s: str) -> int:
    return int(str(s)[:4])

team_ha["ppg"]  = (team_ha["home_points"] + team_ha["away_points"]) / \
                  (team_ha["home_games"]   + team_ha["away_games"])
team_ha["year"] = team_ha["season"].apply(season_year)
panel["year"]   = panel["season"].apply(season_year)

# Shift by 1 so that season Y maps to season Y+1 as "previous season"
prev_q = (
    team_ha[["team", "year", "ppg", "home_away_gap"]]
    .rename(columns={"ppg": "prev_season_ppg", "home_away_gap": "prev_home_away_gap"})
    .assign(year=lambda d: d["year"] + 1)
)
panel = panel.merge(prev_q, on=["team", "year"], how="left")
# NOTE: prev_season_ppg and prev_home_away_gap are constant within a (team, season).
# They are collinear with team×season FE → absorbed without identification.
# Use them only in Model 8e which replaces team×season FE with team + season FE.

# ── 2.3  is_foreign: current manager is non-Turkish ───────────────────────────
# Turkish managers have nationality "Türkiye" in this dataset.
TURKISH_RE = re.compile(r"t[üu]rkiye|turkey|t[üu]rk$", re.IGNORECASE)

def is_foreign_flag(nat):
    if pd.isna(nat):
        return pd.NA
    return int(not bool(TURKISH_RE.search(str(nat))))

panel["is_foreign"] = panel["nationality"].apply(is_foreign_flag).astype("Int64")

# ── 2.4  First change per team-season ─────────────────────────────────────────
# The Python build script assigns event_time relative to the LAST change for
# team-seasons with multiple changes. We always use the FIRST change.
changes = changes.sort_values(["team", "season", "fire_date"])
first_ch = (
    changes
    .groupby(["team", "season"], as_index=False)
    .first()
    [["team", "season", "fire_date", "first_post_n"]]
)

# ── 2.5  Recalculate event_time relative to FIRST change ──────────────────────
panel = panel.drop(columns=["event_time"], errors="ignore")   # reset Python version
panel = panel.merge(
    first_ch[["team", "season", "first_post_n"]],
    on=["team", "season"], how="left"
)
panel["event_time"] = np.where(
    panel["first_post_n"].notna(),
    panel["match_n"] - panel["first_post_n"],
    np.nan
)

# ── 2.6  PostChange binary ────────────────────────────────────────────────────
# = 1 for post-period of treated team-seasons; = 0 everywhere else
panel["treated_ts"]  = panel["first_post_n"].notna()
panel["post_change"] = np.where(
    panel["treated_ts"],
    (panel["event_time"] >= 0).astype(int),
    0
).astype(int)

# ── 2.7  NewManagerDomestic + incoming manager characteristics ─────────────────
# Incoming manager = the manager whose start_date is the earliest one AFTER fire_date.
incoming = (
    first_ch[["team", "season", "fire_date"]]
    .merge(
        mgr_char[["team", "start_date", "nationality",
                   "age_at_appointment",
                   "experience_clubs_before",
                   "experience_years_before"]]
        .rename(columns={
            "nationality":              "new_nationality",
            "age_at_appointment":       "new_age",
            "experience_clubs_before":  "new_exp_clubs",
            "experience_years_before":  "new_exp_years",
        }),
        on="team", how="left"
    )
)
incoming = incoming[incoming["start_date"] > incoming["fire_date"]]
incoming = (
    incoming
    .sort_values("start_date")
    .groupby(["team", "season"], as_index=False)
    .first()
)
incoming["new_mgr_domestic"] = (
    incoming["new_nationality"]
    .apply(lambda x: int(bool(TURKISH_RE.search(str(x)))) if pd.notna(x) else pd.NA)
    .astype("Int64")
)

panel = panel.merge(
    incoming[["team", "season", "new_mgr_domestic",
              "new_age", "new_exp_clubs", "new_exp_years"]],
    on=["team", "season"], how="left"
)

# ── 2.8  expected_change (2025-26 only) ───────────────────────────────────────
# = 1 if mean(avg_grade) >= 0.5 in the 4 ISO weeks immediately before firing
exp_raw["week_monday"] = pd.to_datetime(
    exp_raw["date"] + "-1", format="%G-W%V-%u"
)

ec = (
    first_ch.loc[first_ch["season"] == "2025-2026", ["team", "season", "fire_date"]]
    .merge(exp_raw[["team", "week_monday", "avg_grade"]], on="team", how="left")
)
ec = ec[
    (ec["week_monday"] < ec["fire_date"]) &
    (ec["week_monday"] >= ec["fire_date"] - pd.Timedelta(weeks=5))
]
ec = (
    ec.sort_values("week_monday")
    .groupby(["team", "season"])
    .apply(lambda g: g.tail(4)["avg_grade"].mean(), include_groups=False)
    .reset_index(name="pre_avg")
)
ec["expected_change"] = (ec["pre_avg"] >= 0.5).astype(int)

panel = panel.merge(ec[["team", "season", "expected_change"]],
                    on=["team", "season"], how="left")

# exp_lag1 is in panel for 2025-26 rows only; set to NaN for all other seasons
panel.loc[panel["season"] != "2025-2026", "exp_lag1"] = np.nan

# ── 2.9  Auxiliary outcomes and IDs ───────────────────────────────────────────
panel["win"]   = (panel["points"] == 3).astype(int)
panel["ts_id"] = panel["team"] + " | " + panel["season"]

# FE columns must be string dtype for pyfixest
for col in ["team", "season", "opponent"]:
    panel[col] = panel[col].astype(str)
panel["match_n"] = panel["match_n"].astype(int)


# ── 3. BUILD ANALYSIS PANELS ──────────────────────────────────────────────────
treated_ts_ids = (first_ch["team"] + " | " + first_ch["season"]).tolist()
panel["control_ts"] = ~panel["ts_id"].isin(treated_ts_ids)

# Event panel: treated ±10 window  +  ALL matches from untreated team-seasons.
# Control rows have event_time = NaN; pyfixest i() excludes NaN rows from the
# dummy coefficients but keeps them for FE estimation.
treated_win = panel[
    panel["event_time"].notna() &
    (panel["event_time"] >= -10) &
    (panel["event_time"] <= 10)
].copy()
control_all = panel[panel["control_ts"]].copy()
event_panel = pd.concat([treated_win, control_all], ignore_index=True)


# ── HELPERS ───────────────────────────────────────────────────────────────────

def mk_ep(w: int) -> pd.DataFrame:
    """Event panel with treated ±w window + all control observations."""
    return pd.concat([
        panel[panel["event_time"].notna() &
              (panel["event_time"] >= -w) & (panel["event_time"] <= w)],
        panel[panel["control_ts"]]
    ], ignore_index=True)


def extract_es(model, label: str, ref_k: int = -1) -> pd.DataFrame:
    """
    Extract event-study coefficients from a pyfixest feols model.
    Returns a tidy DataFrame with columns: k, Estimate, Std. Error, ci_lo, ci_hi, label.

    pyfixest names i(event_time) terms as 'event_time[k]'. The regex below is
    intentionally broad to handle minor naming changes across pyfixest versions.
    """
    tidy = model.tidy().reset_index()
    # Column holding term names is "index" after reset_index, or "Coefficient"
    name_col = "Coefficient" if "Coefficient" in tidy.columns else "index"
    tidy = tidy.rename(columns={name_col: "term"})

    es = tidy[tidy["term"].str.contains("event_time", case=False, na=False)].copy()

    def parse_k(term_str: str):
        m = re.search(r"(-?\d+)\]?$", term_str)
        return int(m.group(1)) if m else None

    es["k"] = es["term"].apply(parse_k)
    es = es.dropna(subset=["k"])
    es["k"] = es["k"].astype(int)

    # Add reference row (β = 0 by construction)
    ref_row = pd.DataFrame({
        "term": ["ref"],
        "Estimate": [0.0],
        "Std. Error": [0.0],
        "k": [ref_k]
    })
    es = pd.concat([es, ref_row], ignore_index=True)
    es["ci_lo"] = es["Estimate"] - 1.96 * es["Std. Error"]
    es["ci_hi"] = es["Estimate"] + 1.96 * es["Std. Error"]
    es["label"] = label
    return es.sort_values("k").reset_index(drop=True)


# ── 4. MODEL 1: BASE DiD ──────────────────────────────────────────────────────
# Y_isw = α_i + μ_s + β PostChange + γ₁ home + γ₂ opponent_strength + ε
# Team + season FE; team-clustered SE throughout.

m1_pts = pf.feols("points    ~ post_change + home + opponent_strength | team + season",
                   data=panel, vcov={"CRV1": "team"})
m1_win = pf.feols("win        ~ post_change + home + opponent_strength | team + season",
                   data=panel, vcov={"CRV1": "team"})
m1_gd  = pf.feols("goal_diff  ~ post_change + home + opponent_strength | team + season",
                   data=panel, vcov={"CRV1": "team"})
m1_gf  = pf.feols("gf         ~ post_change + home + opponent_strength | team + season",
                   data=panel, vcov={"CRV1": "team"})
m1_ga  = pf.feols("ga         ~ post_change + home + opponent_strength | team + season",
                   data=panel, vcov={"CRV1": "team"})

print("\n── Model 1: Base DiD ──")
pf.etable([m1_pts, m1_win, m1_gd, m1_gf, m1_ga],
          labels={"Points": "points", "Win": "win", "Goal diff": "goal_diff",
                  "Goals for": "gf", "Goals against": "ga"})


# ── 5. MODEL 2: PREFERRED EVENT-STUDY ─────────────────────────────────────────
# Y_isw = α_{is} + λ_{sw} + δ_o
#       + Σ_{k≠-1} β_k 1[event_time=k]
#       + γ₁ home + γ₂ opponent_strength + ε
# FE: team×season | season×match_n | opponent
# Event window: -10 to +10, reference = -1

m2 = pf.feols(
    "points ~ i(event_time, ref=-1) + home + opponent_strength"
    " | team^season + season^match_n + opponent",
    data=event_panel, vcov={"CRV1": "team"}
)
print("\n── Model 2: Preferred event-study ──")
m2.summary()
m2.iplot(title="Event-study: manager change effect on points per match (ref = -1)",
         xlabel="Matchweeks relative to first manager change",
         ylabel="Coefficient (points per match)")


# ── 6. MODEL 3: EXTENDED — INCOMING MANAGER CHARACTERISTICS ──────────────────
# CAUTION: new_age, new_exp_clubs, new_exp_years are post-treatment by construction
# (defined only for the post-change spell; NaN in pre-period).
# They capture within-treated correlation, not a clean causal effect.
# Prefer Section 9 (heterogeneity interactions) for the rigorous analysis.

m3 = pf.feols(
    "points ~ i(event_time, ref=-1) + home + opponent_strength"
    " + new_age + new_exp_clubs + new_exp_years"
    " | team^season + season^match_n + opponent",
    data=event_panel.dropna(subset=["new_age"]),
    vcov={"CRV1": "team"}
)

print("\n── Models 2-3: Preferred vs extended ──")
pf.etable([m2, m3],
          labels={"Baseline": "m2",
                  "+ Incoming mgr controls (post-treatment)": "m3"})


# ── 7. MODEL 4: ANTICIPATION / EXPECTATION (2025-26 ONLY) ────────────────────
# Expectation variables are available only for 2025-26. Do NOT include in
# the main 30-season specification.

panel_26 = panel[(panel["season"] == "2025-2026") & panel["post_change"].notna()].copy()

# 4a. Continuous expectation signal (lagged 1 ISO week)
m4a = pf.feols(
    "points ~ post_change + exp_lag1 + home + opponent_strength | team + match_n",
    data=panel_26, vcov={"CRV1": "team"}
)

# 4b. Binary expected_change indicator
m4b = pf.feols(
    "points ~ post_change + expected_change + home + opponent_strength | team + match_n",
    data=panel_26.dropna(subset=["expected_change"]),
    vcov={"CRV1": "team"}
)

# 4c. Interaction: PostChange × expected_change
# β        = effect of an UNEXPECTED manager change (expected_change = 0)
# θ        = differential for an EXPECTED change
# β + θ    = total effect of an EXPECTED manager change
m4c = pf.feols(
    "points ~ post_change * expected_change + home + opponent_strength | team + match_n",
    data=panel_26.dropna(subset=["expected_change"]),
    vcov={"CRV1": "team"}
)

coef_4c = m4c.coef()
b4  = coef_4c["post_change"]
th4 = coef_4c["post_change:expected_change"]
print(f"\nModel 4c — β (unexpected) = {b4:.3f} | θ = {th4:.3f} | β+θ (expected) = {b4+th4:.3f}")

print("\n── Model 4: Anticipation effects (2025-26 only) ──")
pf.etable([m4a, m4b, m4c],
          labels={"Continuous exp_lag1": "m4a",
                  "Binary expected_change": "m4b",
                  "Interaction": "m4c"})


# ── 8. MODEL 5: DOMESTIC MANAGER HETEROGENEITY ────────────────────────────────
# β        = effect of a change where the INCOMING manager is foreign
# θ        = additional effect when the incoming manager is domestic/Turkish
# β + θ    = total effect when the incoming manager is domestic

m5 = pf.feols(
    "points ~ post_change + post_change:new_mgr_domestic + home + opponent_strength"
    " | team^season + season^match_n + opponent",
    data=event_panel.dropna(subset=["new_mgr_domestic"]),
    vcov={"CRV1": "team"}
)

coef_5 = m5.coef()
b5  = coef_5["post_change"]
th5 = coef_5["post_change:new_mgr_domestic"]
print(f"\nModel 5 — β (foreign new mgr) = {b5:.3f} | θ = {th5:.3f} | β+θ (domestic) = {b5+th5:.3f}")

print("\n── Model 5: Domestic/foreign incoming manager heterogeneity ──")
pf.etable([m5])


# ── 9. MODEL 6: OTHER MANAGER CHARACTERISTIC HETEROGENEITY ───────────────────
m6_age = pf.feols(
    "points ~ post_change + post_change:new_age + home + opponent_strength"
    " | team^season + season^match_n + opponent",
    data=event_panel.dropna(subset=["new_age"]), vcov={"CRV1": "team"}
)
m6_for = pf.feols(
    "points ~ post_change + post_change:is_foreign + home + opponent_strength"
    " | team^season + season^match_n + opponent",
    data=event_panel.dropna(subset=["is_foreign"]), vcov={"CRV1": "team"}
)
m6_ec = pf.feols(
    "points ~ post_change + post_change:new_exp_clubs + home + opponent_strength"
    " | team^season + season^match_n + opponent",
    data=event_panel.dropna(subset=["new_exp_clubs"]), vcov={"CRV1": "team"}
)
m6_ey = pf.feols(
    "points ~ post_change + post_change:new_exp_years + home + opponent_strength"
    " | team^season + season^match_n + opponent",
    data=event_panel.dropna(subset=["new_exp_years"]), vcov={"CRV1": "team"}
)

print("\n── Model 6: Manager characteristic interactions ──")
pf.etable([m6_age, m6_for, m6_ec, m6_ey],
          labels={"× Age": "m6_age", "× Foreign": "m6_for",
                  "× Exp clubs": "m6_ec", "× Exp years": "m6_ey"})


# ── 10. MODEL 7: DOMESTIC vs FOREIGN EVENT-STUDY ──────────────────────────────

# Approach A: Interacted model.
# i(event_time, ref=-1) terms            → foreign manager path (new_mgr_domestic = 0)
# i(event_time, new_mgr_domestic, ref=-1)→ DIFFERENTIAL for domestic path
# Domestic path = sum of both sets.
ep_nat = event_panel.dropna(subset=["new_mgr_domestic"])
m7_int = pf.feols(
    "points ~ i(event_time, ref=-1) + i(event_time, new_mgr_domestic, ref=-1)"
    " + home + opponent_strength"
    " | team^season + season^match_n + opponent",
    data=ep_nat, vcov={"CRV1": "team"}
)

# Approach B: Two separate event-studies (cleaner plots, same identification).
m7_for = pf.feols(
    "points ~ i(event_time, ref=-1) + home + opponent_strength"
    " | team^season + season^match_n + opponent",
    data=ep_nat[ep_nat["new_mgr_domestic"] == 0],
    vcov={"CRV1": "team"}
)
m7_dom = pf.feols(
    "points ~ i(event_time, ref=-1) + home + opponent_strength"
    " | team^season + season^match_n + opponent",
    data=ep_nat[ep_nat["new_mgr_domestic"] == 1],
    vcov={"CRV1": "team"}
)


# ── 11. MODEL 8: ROBUSTNESS ───────────────────────────────────────────────────

## 8a. Single-change team-seasons only -----------------------------------------
single_ts = (
    changes.groupby(["team", "season"]).size().reset_index(name="n")
    .query("n == 1")
    .apply(lambda r: f"{r.team} | {r.season}", axis=1)
    .tolist()
)
ep_single = event_panel[
    event_panel["control_ts"] | event_panel["ts_id"].isin(single_ts)
]
m8a = pf.feols(
    "points ~ i(event_time, ref=-1) + home + opponent_strength"
    " | team^season + season^match_n + opponent",
    data=ep_single, vcov={"CRV1": "team"}
)

## 8b. Alternative outcomes ----------------------------------------------------
ES_FMT = "i(event_time, ref=-1) + home + opponent_strength | team^season + season^match_n + opponent"
m8b_win = pf.feols(f"win       ~ {ES_FMT}", data=event_panel, vcov={"CRV1": "team"})
m8b_gd  = pf.feols(f"goal_diff ~ {ES_FMT}", data=event_panel, vcov={"CRV1": "team"})
m8b_gf  = pf.feols(f"gf        ~ {ES_FMT}", data=event_panel, vcov={"CRV1": "team"})
m8b_ga  = pf.feols(f"ga        ~ {ES_FMT}", data=event_panel, vcov={"CRV1": "team"})

## 8c. Alternative event windows -----------------------------------------------
m8c_6 = pf.feols(f"points ~ {ES_FMT}", data=mk_ep(6),  vcov={"CRV1": "team"})
m8c_8 = pf.feols(f"points ~ {ES_FMT}", data=mk_ep(8),  vcov={"CRV1": "team"})

print("\n── Robustness: event window width ──")
pf.etable([m8c_6, m8c_8, m2],
          labels={"±6": "m8c_6", "±8": "m8c_8", "±10 (main)": "m2"})

## 8d. Placebo treatment for control team-seasons ------------------------------
rng             = np.random.default_rng(42)
ctrl_ts_list    = panel.loc[panel["control_ts"], "ts_id"].unique()
fake_post_n     = rng.integers(10, 26, size=len(ctrl_ts_list))   # uniform [10, 25]
fake_fire_map   = dict(zip(ctrl_ts_list, fake_post_n))

pan_plac = panel.copy()
ctrl_mask = pan_plac["ts_id"].isin(ctrl_ts_list)
pan_plac.loc[ctrl_mask, "event_time"] = (
    pan_plac.loc[ctrl_mask, "match_n"] -
    pan_plac.loc[ctrl_mask, "ts_id"].map(fake_fire_map)
)
ep_plac = pan_plac[
    pan_plac["event_time"].notna() &
    (pan_plac["event_time"] >= -10) &
    (pan_plac["event_time"] <= 10)
]
m8d_plac = pf.feols(
    f"points ~ {ES_FMT}", data=ep_plac, vcov={"CRV1": "team"}
)
# Expect: flat pre and post coefficients (falsification).

## 8e. FE spec comparison: team + season FE allows quality controls ------------
# prev_season_ppg and prev_home_away_gap are constant within a (team, season).
# They are absorbed by team×season FE in Model 2 (collinear → unidentified).
# Replacing team×season FE with team + season FE breaks the collinearity.
ep_qual = event_panel.dropna(subset=["prev_season_ppg"])
m8e = pf.feols(
    "points ~ i(event_time, ref=-1) + home + opponent_strength"
    " + prev_season_ppg + prev_home_away_gap"
    " | team + season + opponent",
    data=ep_qual, vcov={"CRV1": "team"}
)

print("\n── Robustness: FE specification comparison ──")
pf.etable([m2, m8e],
          labels={"team×season + season×week FE (preferred)": "m2",
                  "team + season FE + quality controls": "m8e"})
print("Note: prev_season_ppg / prev_home_away_gap absorbed in col.1; identified in col.2.")

## 8f. Mechanism analysis: in-game stats (2017-18 onward) ---------------------
# HS and HST are NOT in panel_full.csv (build_panel_full.py excludes them).
# Load them from the turkey-data branch raw CSVs and join before running these models.
#
# import subprocess, io
# def load_shots(season_label):
#     raw = subprocess.check_output(
#         ["git", "show", f"origin/turkey-data:data/{season_label}.csv"], cwd=ROOT
#     )
#     df = pd.read_csv(io.BytesIO(raw))
#     if "HS" not in df.columns:
#         return None
#     df["match_date"] = pd.to_datetime(df["Date"], dayfirst=True, errors="coerce")
#     home = df[["match_date","HomeTeam","AwayTeam","HS","HST"]].rename(
#         columns={"HomeTeam":"team","AwayTeam":"opponent","HS":"shots","HST":"sot"})
#     away = df[["match_date","HomeTeam","AwayTeam","AS","AST"]].rename(
#         columns={"AwayTeam":"team","HomeTeam":"opponent","AS":"shots","AST":"sot"})
#     return pd.concat([home, away])
#
# seasons_2017 = [s for s in panel["season"].unique() if season_year(s) >= 2017]
# shots_panel  = pd.concat([load_shots(s) for s in seasons_2017 if load_shots(s) is not None])
# ep_mech = event_panel[event_panel["season"].apply(season_year) >= 2017].merge(
#     shots_panel, on=["team","opponent","match_date"], how="left")
# m8f_shots = pf.feols(f"shots ~ {ES_FMT}", data=ep_mech, vcov={"CRV1":"team"})
# m8f_sot   = pf.feols(f"sot   ~ {ES_FMT}", data=ep_mech, vcov={"CRV1":"team"})
#
# LABEL AS DESCRIPTIVE/MECHANISM ONLY — shots are a potential mechanism, not a
# causal control. Including them in the main specification would over-control
# and block the treatment effect.


# ── 12. SUN & ABRAHAM (STAGGERED DiD) ────────────────────────────────────────
# sunab() implements Sun & Abraham (2021): each cohort is compared only to
# never-treated units, avoiding contaminated comparisons between differently-timed
# treated units that bias standard TWFE under heterogeneous treatment effects.
#
# Cohort: first_post_n (matchweek of first post-change match, 1-34).
# Period: match_n (1-34 within season).
# Never-treated: cohort = np.inf.
#
# Assumption: cohorts defined by within-season timing. Season + season×week FEs
# absorb cross-season baseline differences. For a fully cross-season staggered
# estimator, use the `csdid` Python package (Callaway & Sant'Anna).

panel["cohort_sa"] = np.where(
    panel["first_post_n"].notna(),
    panel["first_post_n"].astype(float),
    np.inf
)

m_sunab = pf.feols(
    "points ~ sunab(cohort_sa, match_n) + home + opponent_strength"
    " | team^season + season^match_n + opponent",
    data=panel, vcov={"CRV1": "team"}
)

print("\n── Sun & Abraham: ATT aggregate ──")
m_sunab.aggregate("ATT")
m_sunab.iplot(
    title="Sun & Abraham event-study (staggered DiD, within-season cohorts)",
    xlabel="Matchweeks relative to first manager change",
    ylabel="Points per match"
)

print("\n── TWFE vs Sun-Abraham ──")
pf.etable([m2, m_sunab],
          labels={"TWFE event-study": "m2", "Sun & Abraham (2021)": "m_sunab"})
print("SA estimator weights cohort-specific ATTs by cohort size.")
print("Cohort = first post-change matchweek within season.")
print("For cross-season staggering, use Callaway-Sant'Anna (csdid package).")


# ── 13. PUBLICATION-QUALITY PLOTS ─────────────────────────────────────────────

def plot_es(dfs: list[tuple], title: str, subtitle: str,
            savepath: Path, colors: list[str] | None = None):
    """
    Plot one or more event-study coefficient paths on the same axes.

    Parameters
    ----------
    dfs      : list of (DataFrame from extract_es, color_hex) tuples
    title    : figure title
    subtitle : figure subtitle (displayed below title)
    savepath : output path without extension (.pdf and .png are saved)
    colors   : optional list of hex colors (overrides per-df colors)
    """
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.axhline(0,    color="grey",  linestyle="--", linewidth=0.8, zorder=1)
    ax.axvline(-0.5, color="tomato", linestyle="--", linewidth=0.8, zorder=1)

    default_colors = ["#2980B9", "#C0392B", "#27AE60", "#8E44AD"]
    handles = []

    for idx, (df, *rest) in enumerate(dfs):
        color = (rest[0] if rest else None) or default_colors[idx % len(default_colors)]
        ax.fill_between(df["k"], df["ci_lo"], df["ci_hi"],
                        alpha=0.15, color=color, zorder=2)
        ax.plot(df["k"], df["Estimate"], color=color, linewidth=1.0, zorder=3)
        ax.scatter(df["k"], df["Estimate"], color=color, s=30, zorder=4)
        handles.append(mpatches.Patch(color=color, label=df["label"].iloc[0]))

    ax.set_xticks(range(-10, 11))
    ax.set_xlabel("Matchweeks relative to first manager change", fontsize=11)
    ax.set_ylabel("Points per match (coefficient)", fontsize=11)
    ax.set_title(title, fontsize=12, fontweight="bold", pad=6)
    ax.text(0.5, 1.01, subtitle, transform=ax.transAxes,
            ha="center", va="bottom", fontsize=8.5, color="grey")
    if len(dfs) > 1:
        ax.legend(handles=handles, loc="lower right", fontsize=9, framealpha=0.9)
    ax.grid(axis="y", alpha=0.3)
    ax.spines[["top", "right"]].set_visible(False)

    fig.tight_layout()
    fig.savefig(savepath.with_suffix(".pdf"), bbox_inches="tight")
    fig.savefig(savepath.with_suffix(".png"), dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved {savepath.with_suffix('.png')}")


# Figure 1: Main event-study
es_main = extract_es(m2, "All manager changes")
plot_es(
    [(es_main, "#2980B9")],
    title    = "Manager change and points per match — Turkish Süper Lig (1994–2026)",
    subtitle = "team-season + season-week + opponent FE | 95% CI | team-clustered SE | ref = -1",
    savepath = OUT / "fig1_event_study_main"
)

# Figure 2: Domestic vs foreign incoming manager
es_dom = extract_es(m7_dom, "New manager: domestic (Turkish)")
es_for = extract_es(m7_for, "New manager: foreign")
plot_es(
    [(es_dom, "#C0392B"), (es_for, "#2980B9")],
    title    = "Manager change by nationality of incoming manager",
    subtitle = "Separate event-studies | 95% CI | team-clustered SE | ref = -1",
    savepath = OUT / "fig2_domestic_vs_foreign"
)

# Figure 3: Real treatment vs placebo
es_real = extract_es(m2,       "Real treatment")
es_plac = extract_es(m8d_plac, "Placebo (fake treatment)")
plot_es(
    [(es_real, "#2980B9"), (es_plac, "#95A5A6")],
    title    = "Real treatment vs placebo check",
    subtitle = "Placebo assigns random fire week to never-treated team-seasons | ref = -1",
    savepath = OUT / "fig3_placebo"
)

print("\nDone. All models estimated. Figures saved to out/")
