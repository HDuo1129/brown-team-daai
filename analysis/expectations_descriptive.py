"""
analysis/expectations_descriptive.py
======================================
Descriptive analysis of the expectations signal around manager changes.

Questions answered:
1. What share of changes were "expected" (high avg_grade before)?
2. Were there cases where expectation was high but the manager was NOT fired?
3. How does the avg_grade evolve around the change date (event study view)?

Usage:
    python analysis/expectations_descriptive.py
"""
import pandas as pd
import numpy as np
from pathlib import Path

ROOT = Path(__file__).parent.parent

# ── Load data ─────────────────────────────────────────────────────────────────

exp = pd.read_csv(ROOT / "out" / "expectations.csv")
mgr = pd.read_csv(ROOT / "managers" / "managers.csv",
                  parse_dates=["start_date", "end_date"])

# Focus: the 18 Süper Lig teams we have expectation data for
SL_TEAMS = set(exp["team"].unique())

# Filter managers to the 2025-26 season window and only SL teams
SEASON_START = pd.Timestamp("2025-07-01")
SEASON_END   = pd.Timestamp("2026-06-30")

changes = mgr[
    mgr["football_data_name"].isin(SL_TEAMS) &
    mgr["end_date"].notna() &
    (mgr["end_date"] >= SEASON_START) &
    (mgr["end_date"] <= SEASON_END)
].copy()
changes = changes.rename(columns={"football_data_name": "team"})
changes["change_week"] = changes["end_date"].dt.isocalendar().apply(
    lambda r: f"{int(r['year'])}-W{int(r['week']):02d}", axis=1
)

print(f"Manager changes in 2025-26 (SL teams with expectation data): {len(changes)}")
print(f"Teams affected: {changes['team'].nunique()}")
print()

# ── Pre-change expectation window ─────────────────────────────────────────────
# For each change, compute avg_grade in the 4 weeks BEFORE the change week

def get_pre_change_score(team, change_week, exp_df, n_weeks=4):
    """Return mean avg_grade for [change_week-n_weeks, change_week-1]."""
    # Parse change_week to a date
    change_date = pd.to_datetime(change_week + "-1", format="%G-W%V-%u")
    cutoff_start = change_date - pd.Timedelta(weeks=n_weeks)

    # Filter exp rows for this team
    t = exp_df[exp_df["team"] == team].copy()
    t["week_date"] = pd.to_datetime(t["date"] + "-1", format="%G-W%V-%u")

    pre = t[(t["week_date"] >= cutoff_start) & (t["week_date"] < change_date)]
    if pre.empty:
        return np.nan
    return pre["avg_grade"].mean()


changes["pre_avg_grade"] = changes.apply(
    lambda r: get_pre_change_score(r["team"], r["change_week"], exp), axis=1
)

# ── Define "expected" threshold ───────────────────────────────────────────────
# avg_grade ≥ 0.5 in the 4 weeks before change → "expected" change
THRESHOLD = 0.5
changes["expected"] = changes["pre_avg_grade"] >= THRESHOLD

# ── Summary stats ─────────────────────────────────────────────────────────────

valid = changes.dropna(subset=["pre_avg_grade"])
n_total   = len(valid)
n_expected  = valid["expected"].sum()
n_unexpected = n_total - n_expected

print("=" * 60)
print("1. SHARE OF CHANGES THAT WERE EXPECTED")
print("=" * 60)
print(f"  Changes with expectation data (≥1 article in prior 4 weeks): {n_total}")
print(f"  Expected   (pre avg_grade ≥ {THRESHOLD}): {n_expected}  ({n_expected/n_total*100:.0f}%)")
print(f"  Unexpected (pre avg_grade <  {THRESHOLD}): {n_unexpected}  ({n_unexpected/n_total*100:.0f}%)")
print()

print("Distribution of pre-change avg_grade:")
print(valid["pre_avg_grade"].describe().round(3).to_string())
print()

print("Changes by team:")
print(valid[["team", "manager", "end_date", "pre_avg_grade", "expected"]]
      .sort_values("pre_avg_grade", ascending=False)
      .to_string(index=False))
print()

# ── High expectation but NO firing ────────────────────────────────────────────
# Find weeks where avg_grade is high but the team did NOT change manager that week

print("=" * 60)
print("2. HIGH-EXPECTATION WEEKS WITH NO FIRING")
print("=" * 60)

change_keys = set(zip(changes["team"], changes["change_week"]))
high_exp = exp[exp["avg_grade"] >= THRESHOLD].copy()
high_exp["was_fired"] = high_exp.apply(
    lambda r: (r["team"], r["date"]) in change_keys, axis=1
)

n_high      = len(high_exp)
n_fired     = high_exp["was_fired"].sum()
n_not_fired = n_high - n_fired

print(f"  Weeks with avg_grade ≥ {THRESHOLD}: {n_high}")
print(f"  Of those: firing happened that week: {n_fired}")
print(f"  Of those: no firing (high signal, no action): {n_not_fired}  ({n_not_fired/n_high*100:.0f}%)")
print()

print("High-expectation weeks with no firing (first 20):")
print(high_exp[~high_exp["was_fired"]][["team", "date", "avg_grade", "n_relevant"]]
      .sort_values("avg_grade", ascending=False)
      .head(20)
      .to_string(index=False))
print()

# ── Event-study view ──────────────────────────────────────────────────────────
# For each change, compute avg_grade in event time: t-6 to t+4

def event_window(team, change_week, exp_df, pre=6, post=4):
    change_date = pd.to_datetime(change_week + "-1", format="%G-W%V-%u")
    t = exp_df[exp_df["team"] == team].copy()
    t["week_date"] = pd.to_datetime(t["date"] + "-1", format="%G-W%V-%u")
    rows = []
    for offset in range(-pre, post + 1):
        w_date = change_date + pd.Timedelta(weeks=offset)
        row_match = t[t["week_date"] == w_date]
        rows.append({
            "event_time": offset,
            "avg_grade": row_match["avg_grade"].values[0] if not row_match.empty else np.nan,
            "n_news": row_match["n_news"].values[0] if not row_match.empty else 0,
        })
    return rows


print("=" * 60)
print("3. AVERAGE avg_grade AROUND CHANGE (event study, all changes)")
print("=" * 60)

all_event = []
for _, row in valid.iterrows():
    for e in event_window(row["team"], row["change_week"], exp):
        e["change_id"] = f"{row['team']}_{row['change_week']}"
        e["expected"] = row["expected"]
        all_event.append(e)

ev = pd.DataFrame(all_event)
ev_mean = ev.groupby("event_time")["avg_grade"].agg(["mean", "count"]).round(3)
ev_mean.columns = ["mean_avg_grade", "n_obs"]
print(ev_mean.to_string())
print()

print("Event study by EXPECTED vs UNEXPECTED changes:")
ev_split = (ev.groupby(["event_time", "expected"])["avg_grade"]
              .mean()
              .round(3)
              .unstack("expected")
              .rename(columns={False: "unexpected", True: "expected"}))
print(ev_split.to_string())
print()

# ── Anticipation check ────────────────────────────────────────────────────────
print("=" * 60)
print("4. ANTICIPATION: does pre-change avg_grade rise before firing?")
print("=" * 60)
pre_trend = ev[ev["event_time"] < 0].groupby("event_time")["avg_grade"].mean().round(3)
print("Mean avg_grade in weeks before change:")
print(pre_trend.to_string())
print()
print("If avg_grade rises as event_time approaches 0, there is anticipation.")

print()
print("Done. Use these outputs to build the presentation slides.")
