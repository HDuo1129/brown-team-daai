"""
analysis/build_panel_full.py
=============================
Build the full analysis panel: all 32 seasons (1994-2026), all teams.

Unit:     (team, match)
Outcome:  points (3/1/0), goal_diff
Treatment: manager changed mid-season (not summer re-appointment)
          Caretaker stints < 14 days excluded

Expectations variable appended ONLY for 2025-26 (our RSS window).

Outputs:
  out/panel_full.csv        — full (team, match) panel, all seasons
  out/panel_full_events.csv — restricted to ±10 match window around each change
"""
import subprocess, io
import pandas as pd
import numpy as np
from pathlib import Path

ROOT         = Path(__file__).parent.parent
EVENT_WINDOW = 10

# ── 1. Load all match seasons ─────────────────────────────────────────────────

print("Loading all 32 seasons from turkey-data branch...")

# List available season files
file_list_raw = subprocess.check_output(
    ["git", "show", "origin/turkey-data", "--name-only", "--format="],
    cwd=ROOT
).decode()
season_files = [f for f in file_list_raw.splitlines() if f.startswith("data/") and f.endswith(".csv")]

season_dfs = []
for f in sorted(season_files):
    raw = subprocess.check_output(["git", "show", f"origin/turkey-data:{f}"], cwd=ROOT)
    try:
        df = pd.read_csv(io.BytesIO(raw))
        # Try both date formats (dayfirst for DD/MM/YY and DD/MM/YYYY)
        df["match_date"] = pd.to_datetime(df["Date"], dayfirst=True, errors="coerce")
        season_label = f.replace("data/", "").replace(".csv", "")
        df["season"] = season_label
        season_dfs.append(df[["season", "match_date", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "FTR"]])
    except Exception as e:
        print(f"  WARNING: could not parse {f}: {e}")

matches_raw = pd.concat(season_dfs, ignore_index=True)
matches_raw = matches_raw.dropna(subset=["match_date", "HomeTeam", "AwayTeam", "FTR"])
print(f"  Total matches loaded: {len(matches_raw)} across {matches_raw['season'].nunique()} seasons")

# ── 2. Build long (team, match) format ────────────────────────────────────────

home = matches_raw.copy()
home = home.rename(columns={"HomeTeam": "team", "AwayTeam": "opponent", "FTHG": "gf", "FTAG": "ga"})
home["home"] = 1

away = matches_raw.copy()
away = away.rename(columns={"AwayTeam": "team", "HomeTeam": "opponent", "FTAG": "gf", "FTHG": "ga"})
away["home"] = 0

panel = pd.concat([home, away], ignore_index=True)
panel["goal_diff"] = panel["gf"] - panel["ga"]

def ftr_to_points(row):
    if (row["FTR"] == "H" and row["home"] == 1) or (row["FTR"] == "A" and row["home"] == 0):
        return 3
    elif row["FTR"] == "D":
        return 1
    else:
        return 0

panel["points"] = panel.apply(ftr_to_points, axis=1)
panel = panel.sort_values(["team", "season", "match_date"]).reset_index(drop=True)

# Match number within each (team, season)
panel["match_n"] = panel.groupby(["team", "season"]).cumcount() + 1

print(f"  Long panel: {len(panel)} (team, match) rows | {panel['team'].nunique()} unique teams")

# ── 3. Load manager data ──────────────────────────────────────────────────────

print("Loading manager stints...")
mgr = pd.read_csv(ROOT / "managers" / "managers.csv",
                  parse_dates=["start_date", "end_date"])
mgr = mgr.rename(columns={"football_data_name": "team"})

all_teams = set(panel["team"].unique())
mgr = mgr[mgr["team"].isin(all_teams)].copy()
print(f"  Manager stints covering {mgr['team'].nunique()} teams")

# ── 4. Assign manager to each (team, match) ───────────────────────────────────

print("Assigning managers to matches (this may take a moment)...")

# Build per-team lookup for speed
mgr_lookup = {}
for team, grp in mgr.groupby("team"):
    mgr_lookup[team] = grp.sort_values("start_date").reset_index(drop=True)

trainer_ids   = []
manager_names = []

for _, row in panel.iterrows():
    team = row["team"]
    date = row["match_date"]
    if team not in mgr_lookup:
        trainer_ids.append(pd.NA)
        manager_names.append(pd.NA)
        continue
    t_mgr = mgr_lookup[team]
    cands = t_mgr[
        (t_mgr["start_date"] <= date) &
        ((t_mgr["end_date"] >= date) | t_mgr["end_date"].isna())
    ]
    if cands.empty:
        trainer_ids.append(pd.NA)
        manager_names.append(pd.NA)
    else:
        best = cands.iloc[-1]
        trainer_ids.append(best["trainer_id"])
        manager_names.append(best["manager"])

panel["trainer_id"]   = trainer_ids
panel["manager_name"] = manager_names

print(f"  Unassigned matches: {panel['trainer_id'].isna().sum()}")

# ── 5. Identify mid-season treatment events ───────────────────────────────────

print("Identifying mid-season manager changes...")

# Season date bounds: infer from match data
season_bounds = (
    panel.groupby("season")["match_date"]
    .agg(season_start="min", season_end="max")
    .reset_index()
)

# For each manager stint end_date, check if it falls within any season
mgr_ended = mgr[mgr["end_date"].notna()].copy()
mgr_ended["stint_days"] = (mgr_ended["end_date"] - mgr_ended["start_date"]).dt.days

change_events = []
for _, c in mgr_ended[mgr_ended["stint_days"] >= 14].iterrows():
    team      = c["team"]
    fire_date = c["end_date"]

    # Which season does this fall in?
    season_row = season_bounds[
        (season_bounds["season_start"] <= fire_date) &
        (season_bounds["season_end"]   >= fire_date)
    ]
    if season_row.empty:
        continue
    season = season_row.iloc[0]["season"]

    t_matches = panel[
        (panel["team"] == team) &
        (panel["season"] == season)
    ].sort_values("match_date")

    if t_matches.empty:
        continue

    pre_matches  = t_matches[t_matches["match_date"] <= fire_date]
    post_matches = t_matches[t_matches["match_date"] >  fire_date]

    # Require at least 3 matches on each side within the season
    if len(pre_matches) < 3 or post_matches.empty:
        continue

    change_events.append({
        "team":           team,
        "season":         season,
        "manager_out":    c["manager"],
        "trainer_id_out": c["trainer_id"],
        "fire_date":      fire_date,
        "last_pre_n":     pre_matches["match_n"].max(),
        "first_post_n":   post_matches["match_n"].min(),
        "n_pre_avail":    len(pre_matches),
        "n_post_avail":   len(post_matches),
    })

events_df = pd.DataFrame(change_events)
print(f"  Valid mid-season changes: {len(events_df)} across {events_df['team'].nunique()} teams "
      f"and {events_df['season'].nunique()} seasons")

# ── 6. Add event_time ─────────────────────────────────────────────────────────

# Multiple changes per team-season: assign to the NEAREST change
panel["event_time"]    = np.nan
panel["change_index"]  = -1
panel["manager_out"]   = ""
panel["fire_date"]     = pd.NaT

for i, ev in events_df.iterrows():
    mask = (panel["team"] == ev["team"]) & (panel["season"] == ev["season"])
    panel.loc[mask, "event_time"]   = panel.loc[mask, "match_n"] - ev["first_post_n"]
    panel.loc[mask, "change_index"] = i
    panel.loc[mask, "manager_out"]  = ev["manager_out"]
    panel.loc[mask, "fire_date"]    = ev["fire_date"]

panel["post"] = np.where(panel["event_time"].isna(), np.nan, (panel["event_time"] >= 0).astype(float))

# ── 7. Add expectations (2025-26 only) ───────────────────────────────────────

print("Adding expectations signal for 2025-26...")
exp = pd.read_csv(ROOT / "out" / "expectations.csv")
exp["week_monday"] = pd.to_datetime(exp["date"] + "-1", format="%G-W%V-%u")
exp_lookup = {(r["team"], r["week_monday"]): r["avg_grade"] for _, r in exp.iterrows()}

panel["match_week_monday"] = panel["match_date"] - pd.to_timedelta(panel["match_date"].dt.dayofweek, unit="D")
panel["prev_week_monday"]  = panel["match_week_monday"] - pd.Timedelta(weeks=1)

panel["exp_lag1"] = panel.apply(
    lambda r: exp_lookup.get((r["team"], r["prev_week_monday"]), np.nan)
    if r["season"] == "2025-2026" else np.nan,
    axis=1
)

# For 2025-26 rows with no news that week: impute 0 (genuine zero signal)
panel.loc[(panel["season"] == "2025-2026") & panel["exp_lag1"].isna(), "exp_lag1"] = 0.0

# ── 8. Add manager characteristics ───────────────────────────────────────────

mgr_char = pd.read_csv(ROOT / "managers" / "manager_characteristics.csv")
char_cols = [c for c in mgr_char.columns
             if c in {"trainer_id", "age_at_appointment", "prior_clubs",
                      "nationality", "is_foreign"}]
if char_cols:
    panel = panel.merge(
        mgr_char[char_cols].drop_duplicates("trainer_id"),
        on="trainer_id", how="left"
    )

# ── 9. Save outputs ───────────────────────────────────────────────────────────

print("Saving...")
out_dir = ROOT / "out"
out_dir.mkdir(exist_ok=True)

panel.to_csv(out_dir / "panel_full.csv", index=False)
print(f"  out/panel_full.csv:        {len(panel)} rows")

panel_events = panel[
    panel["event_time"].notna() &
    (panel["event_time"] >= -EVENT_WINDOW) &
    (panel["event_time"] <= EVENT_WINDOW)
].copy()
panel_events.to_csv(out_dir / "panel_full_events.csv", index=False)
print(f"  out/panel_full_events.csv: {len(panel_events)} rows")

events_df.to_csv(out_dir / "change_events.csv", index=False)
print(f"  out/change_events.csv:     {len(events_df)} treatment events")

# ── 10. Summary ───────────────────────────────────────────────────────────────

print()
print("=" * 60)
print("FULL PANEL SUMMARY")
print("=" * 60)
print(f"Seasons:           {panel['season'].nunique()}")
print(f"Teams (total):     {panel['team'].nunique()}")
print(f"Matches (rows):    {len(panel)}")
print(f"Treatment events:  {len(events_df)}")
print(f"Treated teams:     {events_df['team'].nunique()}")
print(f"Event panel rows:  {len(panel_events)}")
print()
print("Changes per season (top 10):")
print(events_df["season"].value_counts().head(10).to_string())
print()
print("Checks:")
print(f"  Duplicate (team, season, match_date): {panel.duplicated(['team','season','match_date']).sum()}  ← 0 expected")
print(f"  Matches without manager:              {panel['trainer_id'].isna().sum()}")
print(f"  2025-26 rows with exp_lag1:           {(panel[panel['season']=='2025-2026']['exp_lag1'].notna()).sum()}")
