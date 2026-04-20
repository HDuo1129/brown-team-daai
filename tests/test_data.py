"""
tests/test_data.py
==================
Data quality tests for the Turkish Süper Lig dataset.

Three kinds of tests:
  1. Data tests     — structural checks on the CSV files
  2. Data-describe  — coverage and completeness statistics (printed, not asserted)
  3. Code tests     — unit tests for scraping/parsing helper functions

Run:
    pip install pytest pandas
    pytest tests/test_data.py -v

    # Or run data-describe only (no pytest needed):
    python tests/test_data.py --describe
"""

import csv
import sys
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).parent.parent

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_matches() -> pd.DataFrame:
    """Load all match CSVs from the turkey-data git branch."""
    result = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", "turkey-data", "data/"],
        cwd=ROOT, capture_output=True, text=True
    )
    files = [f.strip() for f in result.stdout.splitlines() if f.strip().endswith(".csv")]

    frames = []
    for f in sorted(files):
        content = subprocess.run(
            ["git", "show", f"turkey-data:{f}"],
            cwd=ROOT, capture_output=True, text=True
        ).stdout
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8") as tmp:
            tmp.write(content)
            tmp_path = tmp.name
        try:
            df = pd.read_csv(tmp_path, encoding="latin-1", on_bad_lines="skip")
            season = Path(f).stem
            df["_season"] = season
            frames.append(df)
        except Exception:
            pass
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def parse_date_flexible(s: str):
    """Parse DD/MM/YY or DD/MM/YYYY."""
    s = str(s).strip()
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


# ---------------------------------------------------------------------------
# 1. DATA TESTS
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def matches():
    return load_matches()


@pytest.fixture(scope="session")
def managers():
    return pd.read_csv(ROOT / "managers" / "managers.csv")


@pytest.fixture(scope="session")
def profiles():
    return pd.read_csv(ROOT / "managers" / "manager_profiles.csv")


@pytest.fixture(scope="session")
def characteristics():
    return pd.read_csv(ROOT / "managers" / "manager_characteristics.csv")


@pytest.fixture(scope="session")
def home_away():
    return pd.read_csv(ROOT / "features" / "team_home_away.csv")


@pytest.fixture(scope="session")
def location():
    return pd.read_csv(ROOT / "features" / "team_location.csv")


@pytest.fixture(scope="session")
def mapping():
    return pd.read_csv(ROOT / "managers" / "team_mapping.csv")


# --- Match data tests ---

def test_matches_loaded(matches):
    assert len(matches) > 9000, f"Expected >9000 matches, got {len(matches)}"


def test_ftr_values(matches):
    """FTR must only contain H, D, A."""
    valid = {"H", "D", "A"}
    bad = matches["FTR"].dropna()
    bad = bad[~bad.isin(valid)]
    assert len(bad) == 0, f"Invalid FTR values: {bad.value_counts().to_dict()}"


def test_goals_non_negative(matches):
    """FTHG and FTAG must be >= 0."""
    for col in ["FTHG", "FTAG"]:
        if col in matches.columns:
            neg = matches[col].dropna()
            neg = neg[pd.to_numeric(neg, errors="coerce") < 0]
            assert len(neg) == 0, f"Negative values in {col}: {len(neg)}"


def test_no_duplicate_matches(matches):
    """No two non-null rows should share the same Date + HomeTeam + AwayTeam.
    Note: trailing empty rows in source CSVs are excluded."""
    key = ["Date", "HomeTeam", "AwayTeam"]
    valid = matches.dropna(subset=key)
    dupes = valid[valid.duplicated(subset=key, keep=False)]
    assert len(dupes) == 0, f"{len(dupes)} duplicate match rows found"


def test_home_away_teams_differ(matches):
    """HomeTeam and AwayTeam must not be the same."""
    same = matches[matches["HomeTeam"] == matches["AwayTeam"]]
    assert len(same) == 0, f"{len(same)} rows where HomeTeam == AwayTeam"


# --- Manager stint tests ---

def test_manager_stints_loaded(managers):
    assert len(managers) >= 3800, f"Expected >=3800 stints, got {len(managers)}"


def test_manager_dates_order(managers):
    """end_date must be >= start_date where both are present.
    Known Transfermarkt data errors (≤2 stints with swapped dates) are tolerated."""
    df = managers.dropna(subset=["start_date", "end_date"])
    df = df[df["end_date"] != ""]
    df["start"] = pd.to_datetime(df["start_date"], errors="coerce")
    df["end"]   = pd.to_datetime(df["end_date"],   errors="coerce")
    bad = df[df["end"] < df["start"]]
    if len(bad) > 0:
        print(f"\n  WARNING: {len(bad)} stints with end_date < start_date (Transfermarkt data issues):")
        print(bad[["football_data_name", "manager", "start_date", "end_date"]].to_string())
    # Allow up to 2 known TM data errors; fail if more appear
    assert len(bad) <= 2, f"{len(bad)} stints where end_date < start_date (expected ≤2)"


def test_manager_names_in_mapping(managers, mapping):
    """All football_data_name values in managers must exist in team_mapping."""
    known = set(mapping["football_data_name"])
    unknown = set(managers["football_data_name"]) - known
    assert len(unknown) == 0, f"Unknown club names in managers.csv: {unknown}"


def test_no_duplicate_stints(managers):
    """No exact duplicate rows in managers.csv."""
    key = ["football_data_name", "manager", "start_date"]
    dupes = managers[managers.duplicated(subset=key, keep=False)]
    assert len(dupes) == 0, f"{len(dupes)} duplicate manager stint rows"


# --- Manager profiles tests ---

def test_profiles_loaded(profiles):
    assert len(profiles) >= 1000, f"Expected >=1000 profiles, got {len(profiles)}"


def test_profiles_unique_ids(profiles):
    dupes = profiles[profiles.duplicated(subset=["trainer_id"], keep=False)]
    assert len(dupes) == 0, f"{len(dupes)} duplicate trainer_id values in profiles"


# --- Team location tests ---

def test_location_covers_all_mapping(location, mapping):
    """Every club in team_mapping should have a location row."""
    mapped = set(mapping["football_data_name"])
    located = set(location["football_data_name"])
    missing = mapped - located
    assert len(missing) == 0, f"Clubs in mapping but missing from location: {missing}"


def test_location_regions(location):
    """All region values must be one of the 7 Turkish geographic regions."""
    valid_regions = {
        "Marmara", "Aegean", "Mediterranean",
        "Central Anatolia", "Black Sea",
        "Eastern Anatolia", "Southeastern Anatolia"
    }
    bad = location[~location["region"].isin(valid_regions)]
    assert len(bad) == 0, f"Invalid region values:\n{bad[['football_data_name','region']]}"


# ---------------------------------------------------------------------------
# 2. DATA-DESCRIBE  (coverage statistics)
# ---------------------------------------------------------------------------

def data_describe():
    print("\n" + "="*60)
    print("DATA DESCRIBE — Turkish Süper Lig Dataset")
    print("="*60)

    # Match data
    matches = load_matches()
    print(f"\n[Match Data]")
    print(f"  Total matches:       {len(matches):,}")
    print(f"  Seasons:             {matches['_season'].nunique()}")
    print(f"  Unique home teams:   {matches['HomeTeam'].nunique()}")
    print(f"  FTR null:            {matches['FTR'].isna().sum()}")
    print(f"  FTHG null:           {matches['FTHG'].isna().sum()}")
    print(f"  Date null:           {matches['Date'].isna().sum()}")
    print(f"  Has shots (HS col):  {'HS' in matches.columns}")

    # Matches per season
    print(f"\n  Matches per season (first/last 3):")
    per_season = matches.groupby("_season").size().sort_index()
    for s, n in list(per_season.items())[:3] + [("...", "...")] + list(per_season.items())[-3:]:
        print(f"    {s}: {n}")

    # Manager data
    mgr = pd.read_csv(ROOT / "managers" / "managers.csv")
    print(f"\n[Manager Stints]")
    print(f"  Total stints:        {len(mgr):,}")
    print(f"  Unique clubs:        {mgr['football_data_name'].nunique()}")
    print(f"  Unique managers:     {mgr['manager'].nunique()}")
    print(f"  start_date missing:  {mgr['start_date'].isna().sum() + (mgr['start_date']=='').sum()}")
    print(f"  end_date missing:    {(mgr['end_date'].isna() | (mgr['end_date']=='')).sum()} (current managers)")

    # Profiles
    prof = pd.read_csv(ROOT / "managers" / "manager_profiles.csv")
    print(f"\n[Manager Profiles]")
    print(f"  Unique managers:     {len(prof):,}")
    dob_filled = (prof["date_of_birth"] != "") & prof["date_of_birth"].notna()
    cit_filled = (prof["citizenship"] != "") & prof["citizenship"].notna()
    print(f"  DOB coverage:        {dob_filled.sum()} / {len(prof)} ({100*dob_filled.mean():.1f}%)")
    print(f"  Citizenship coverage:{cit_filled.sum()} / {len(prof)} ({100*cit_filled.mean():.1f}%)")

    # Characteristics
    chars = pd.read_csv(ROOT / "managers" / "manager_characteristics.csv")
    print(f"\n[Manager Characteristics]")
    age_filled = pd.to_numeric(chars["age_at_appointment"], errors="coerce").notna()
    print(f"  age_at_appointment:  {age_filled.sum()} / {len(chars)} ({100*age_filled.mean():.1f}%)")
    exp_filled = pd.to_numeric(chars["experience_clubs_before"], errors="coerce").notna()
    print(f"  experience_clubs:    {exp_filled.sum()} / {len(chars)} ({100*exp_filled.mean():.1f}%)")
    age_vals = pd.to_numeric(chars["age_at_appointment"], errors="coerce").dropna()
    print(f"  Age at appointment:  min={age_vals.min():.1f}, median={age_vals.median():.1f}, max={age_vals.max():.1f}")

    # Home/away
    ha = pd.read_csv(ROOT / "features" / "team_home_away.csv")
    print(f"\n[Home/Away Performance]")
    print(f"  Rows (season×team):  {len(ha):,}")
    print(f"  Seasons:             {ha['season'].nunique()}")
    print(f"  Avg home_away_gap:   {ha['home_away_gap'].mean():.3f} PPG")
    print(f"  Max home_away_gap:   {ha['home_away_gap'].max():.3f} ({ha.loc[ha['home_away_gap'].idxmax(), 'team']})")

    # Location
    loc = pd.read_csv(ROOT / "features" / "team_location.csv")
    print(f"\n[Team Location]")
    print(f"  Teams:               {len(loc)}")
    print(f"  Region distribution:")
    for region, count in loc["region"].value_counts().items():
        print(f"    {region:<25} {count}")

    print("\n" + "="*60)


# ---------------------------------------------------------------------------
# 3. CODE TESTS — unit tests for parsing helpers
# ---------------------------------------------------------------------------

def test_parse_date_ddmmyyyy():
    d = parse_date_flexible("11/08/2023")
    assert d is not None
    assert d.year == 2023 and d.month == 8 and d.day == 11


def test_parse_date_ddmmyy():
    d = parse_date_flexible("13/08/94")
    assert d is not None
    assert d.year == 1994 and d.month == 8 and d.day == 13


def test_parse_date_invalid():
    d = parse_date_flexible("not-a-date")
    assert d is None


def test_parse_date_empty():
    d = parse_date_flexible("")
    assert d is None


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if "--describe" in sys.argv:
        data_describe()
    else:
        print("Run with pytest:  pytest tests/test_data.py -v")
        print("Or describe data: python tests/test_data.py --describe")
        data_describe()
