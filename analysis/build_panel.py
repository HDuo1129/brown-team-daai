"""
analysis/build_panel.py
========================
Build the analysis panel for the DiD estimation.

Design decisions (see PANEL.md):
  - Unit:          (team, match)
  - Treatment:     mid-season manager change (end_date within the 2025-26 season)
  - Event window:  ±10 matches around the change
  - Outcome:       points (3/1/0), goal_diff
  - Expectations:  avg_grade lagged 1 ISO week (to avoid same-week leakage)
  - Caretaker:     stints with < 14 days gap to next manager excluded as "gap" rows
  - Missing exp:   weeks with no articles → avg_grade = 0.0 (genuine low-signal)

Outputs:
  out/panel.csv        — full (team, match) panel, all 18 teams, all matches
  out/panel_events.csv — restricted to ±10 match window around each change
"""
import subprocess, io, sys
import pandas as pd
import numpy as np
from pathlib import Path

ROOT = Path(__file__).parent.parent

SEASON_START = pd.Timestamp("2025-08-01")
SEASON_END   = pd.Timestamp("2026-06-30")
EVENT_WINDOW = 10   # matches before and after change

# ── 1. Load match data (from turkey-data branch) ──────────────────────────────

print("Loading 2025-26 match data...")
raw = subprocess.check_output(
    ["git", "show", "origin/turkey-data:data/2025-2026.csv"],
    cwd=ROOT
)
matches_raw = pd.read_csv(io.BytesIO(raw))
matches_raw["match_date"] = pd.to_datetime(matches_raw["Date"], dayfirst=True)

# Build long format: one row per (team, match)
home = matches_raw[["match_date", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "FTR"]].copy()
home = home.rename(columns={
    "HomeTeam": "team", "AwayTeam": "opponent",
    "FTHG": "gf", "FTAG": "ga"
})
home["home"] = 1

away = matches_raw[["match_date", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "FTR"]].copy()
away = away.rename(columns={
    "AwayTeam": "team", "HomeTeam": "opponent",
    "FTAG": "gf", "FTHG": "ga"
})
away["home"] = 0

panel = pd.concat([home, away], ignore_index=True)
panel["goal_diff"] = panel["gf"] - panel["ga"]

# Points
def ftr_to_points(row):
    if (row["FTR"] == "H" and row["home"] == 1) or (row["FTR"] == "A" and row["home"] == 0):
        return 3
    elif row["FTR"] == "D":
        return 1
    else:
        return 0

panel["points"] = panel.apply(ftr_to_points, axis=1)
panel = panel.sort_values(["team", "match_date"]).reset_index(drop=True)

# Match sequence number within season (per team)
panel["match_n"] = panel.groupby("team").cumcount() + 1

print(f"  Long panel: {len(panel)} rows | {panel['team'].nunique()} teams")

# ── 2. Assign manager to each match ───────────────────────────────────────────

print("Assigning managers to matches...")
mgr = pd.read_csv(ROOT / "managers" / "managers.csv",
                  parse_dates=["start_date", "end_date"])
mgr = mgr.rename(columns={"football_data_name": "team"})

# Keep only 18 SL teams
SL_TEAMS = set(panel["team"].unique())
mgr = mgr[mgr["team"].isin(SL_TEAMS)].copy()

# For each (team, match_date), find the manager whose stint covers that date
def get_manager(team, date, mgr_df):
    candidates = mgr_df[
        (mgr_df["team"] == team) &
        (mgr_df["start_date"] <= date) &
        ((mgr_df["end_date"] >= date) | mgr_df["end_date"].isna())
    ]
    if len(candidates) == 0:
        return pd.NA, pd.NA
    # Take the most recent start_date if multiple
    row = candidates.sort_values("start_date").iloc[-1]
    return row["trainer_id"], row["manager"]

# Build lookup: group by team for speed
mgr_result = []
for team, grp in panel.groupby("team"):
    t_mgr = mgr[mgr["team"] == team].sort_values("start_date")
    for _, match_row in grp.iterrows():
        date = match_row["match_date"]
        candidates = t_mgr[
            (t_mgr["start_date"] <= date) &
            ((t_mgr["end_date"] >= date) | t_mgr["end_date"].isna())
        ]
        if len(candidates) == 0:
            mgr_result.append((pd.NA, pd.NA))
        else:
            row = candidates.iloc[-1]
            mgr_result.append((row["trainer_id"], row["manager"]))

panel["trainer_id"], panel["manager_name"] = zip(*mgr_result)
unassigned = panel["trainer_id"].isna().sum()
print(f"  Matches without manager assigned: {unassigned}")

# ── 3. Identify mid-season treatment events ───────────────────────────────────

print("Identifying mid-season manager changes...")

# A change is "mid-season" if the outgoing manager's end_date is within season matches
mid_changes = mgr[
    mgr["end_date"].notna() &
    (mgr["end_date"] >= SEASON_START) &
    (mgr["end_date"] <= SEASON_END)
].copy()

# Exclude caretaker stints: stints shorter than 14 days
mid_changes["stint_days"] = (mid_changes["end_date"] - mid_changes["start_date"]).dt.days
mid_changes = mid_changes[mid_changes["stint_days"] >= 14].copy()

# For each change, find the match numbers immediately before and after
change_events = []
for _, c in mid_changes.iterrows():
    team      = c["team"]
    fire_date = c["end_date"]
    t_matches = panel[panel["team"] == team].sort_values("match_date")

    # Last match under this manager = last match on or before fire_date
    pre_matches  = t_matches[t_matches["match_date"] <= fire_date]
    post_matches = t_matches[t_matches["match_date"] > fire_date]

    if pre_matches.empty or post_matches.empty:
        continue   # change happened before/after all recorded matches

    last_pre_n  = pre_matches["match_n"].max()
    first_post_n = post_matches["match_n"].min()

    change_events.append({
        "team":         team,
        "manager_out":  c["manager"],
        "trainer_id_out": c["trainer_id"],
        "fire_date":    fire_date,
        "last_pre_n":   last_pre_n,
        "first_post_n": first_post_n,
    })

events_df = pd.DataFrame(change_events)
print(f"  Valid mid-season changes: {len(events_df)} across {events_df['team'].nunique()} teams")

# ── 4. Add event_time to panel ────────────────────────────────────────────────

# For each match, compute event_time relative to the nearest change for that team
# event_time = match_n - first_post_n  (negative = pre, ≥0 = post)
panel["event_time"]   = np.nan
panel["change_index"] = -1   # which change event this match belongs to

for i, ev in events_df.iterrows():
    team_mask = panel["team"] == ev["team"]
    panel.loc[team_mask, "event_time"] = (
        panel.loc[team_mask, "match_n"] - ev["first_post_n"]
    )
    panel.loc[team_mask, "change_index"] = i

panel["post"] = (panel["event_time"] >= 0).astype(float)
panel.loc[panel["event_time"].isna(), "post"] = np.nan

# ── 5. Add expectations (lagged 1 ISO week) ───────────────────────────────────

print("Joining expectations (lagged 1 week)...")
exp = pd.read_csv(ROOT / "out" / "expectations.csv")

# Parse ISO week → Monday date
exp["week_monday"] = pd.to_datetime(
    exp["date"] + "-1", format="%G-W%V-%u"
)

# For each match, look up avg_grade from the PREVIOUS week
panel["match_week_monday"] = panel["match_date"] - pd.to_timedelta(
    panel["match_date"].dt.dayofweek, unit="D"
)
panel["prev_week_monday"] = panel["match_week_monday"] - pd.Timedelta(weeks=1)

# Build lookup dict: (team, monday) → avg_grade
exp_lookup = {
    (row["team"], row["week_monday"]): row["avg_grade"]
    for _, row in exp.iterrows()
}

panel["exp_lag1"] = panel.apply(
    lambda r: exp_lookup.get((r["team"], r["prev_week_monday"]), 0.0),
    axis=1
)

# Coverage check
covered = (panel["exp_lag1"] > 0).sum()
print(f"  Matches with non-zero lagged expectation: {covered} / {len(panel)}")

# ── 6. Add manager characteristics ────────────────────────────────────────────

print("Adding manager characteristics...")
mgr_char = pd.read_csv(ROOT / "managers" / "manager_characteristics.csv")

# Keep relevant columns
char_cols = [c for c in mgr_char.columns
             if c in {"trainer_id", "age_at_appointment", "prior_clubs",
                       "nationality", "is_foreign"}]
if char_cols:
    panel = panel.merge(
        mgr_char[char_cols].drop_duplicates("trainer_id"),
        on="trainer_id", how="left"
    )

# ── 7. Save outputs ───────────────────────────────────────────────────────────

print("Saving outputs...")
out_dir = ROOT / "out"
out_dir.mkdir(exist_ok=True)

panel.to_csv(out_dir / "panel.csv", index=False)
print(f"  out/panel.csv: {len(panel)} rows")

# Restricted event panel: only rows within ±EVENT_WINDOW of a change
panel_events = panel[
    panel["event_time"].notna() &
    (panel["event_time"] >= -EVENT_WINDOW) &
    (panel["event_time"] <= EVENT_WINDOW)
].copy()
panel_events.to_csv(out_dir / "panel_events.csv", index=False)
print(f"  out/panel_events.csv: {len(panel_events)} rows "
      f"| {panel_events['team'].nunique()} teams "
      f"| {events_df['team'].nunique()} treatment units")

# ── 8. Quick sanity checks ────────────────────────────────────────────────────

print()
print("=" * 60)
print("PANEL SUMMARY")
print("=" * 60)
print(f"Full panel:    {len(panel)} (team, match) rows")
print(f"Event panel:   {len(panel_events)} rows within ±{EVENT_WINDOW} match window")
print(f"Treated teams: {events_df['team'].nunique()}")
print(f"Changes:       {len(events_df)}")
print()
print("Points distribution:")
print(panel["points"].value_counts().sort_index().to_string())
print()
print("avg goal_diff:", round(panel["goal_diff"].mean(), 3))
print()
print("Treatment events:")
print(events_df[["team", "manager_out", "fire_date", "last_pre_n", "first_post_n"]]
      .to_string(index=False))

print()
print("Checks:")
dupes = panel.duplicated(["team", "match_date"]).sum()
print(f"  Duplicate (team, match_date): {dupes}  ← should be 0")
print(f"  Matches with NA manager:      {panel['trainer_id'].isna().sum()}")
print(f"  event_time range: {panel['event_time'].min():.0f} to {panel['event_time'].max():.0f}")

if __name__ == "__main__":
    pass
