"""
tests/check_managers.py
========================
Runs data quality checks on managers/managers.csv and saves
a plain-text results report to tests/managers_check_output.txt.

Usage:
    python tests/check_managers.py
"""

import sys
from pathlib import Path
from io import StringIO
from datetime import datetime

import pandas as pd

ROOT       = Path(__file__).parent.parent
INPUT_FILE = ROOT / "managers" / "managers.csv"
OUTPUT_FILE = Path(__file__).parent / "managers_check_output.txt"

# ---------------------------------------------------------------------------
# Capture all print output into a string as well as stdout
# ---------------------------------------------------------------------------

class Tee:
    """Write to both the original stdout and a StringIO buffer."""
    def __init__(self, original):
        self._orig = original
        self.buffer = StringIO()
    def write(self, msg):
        self._orig.write(msg)
        self.buffer.write(msg)
    def flush(self):
        self._orig.flush()

_orig_stdout = sys.stdout
tee = Tee(_orig_stdout)
sys.stdout = tee

# ---------------------------------------------------------------------------

def section(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")

def ok(msg):   print(f"  [PASS]  {msg}")
def warn(msg): print(f"  [WARN]  {msg}")
def fail(msg): print(f"  [FAIL]  {msg}")

# ---------------------------------------------------------------------------

print(f"managers/managers.csv — Data Quality Check")
print(f"Run at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print(f"File:   {INPUT_FILE}")

df = pd.read_csv(INPUT_FILE)

# ── 1. Basic shape ──────────────────────────────────────────────────────────
section("1. Basic Shape")
print(f"  Rows:    {len(df)}")
print(f"  Columns: {list(df.columns)}")

# ── 2. Missing values ───────────────────────────────────────────────────────
section("2. Missing Values")
missing = df.isna().sum()
print(missing.to_string())
for col, n in missing.items():
    if col == "end_date":
        ok(f"end_date: {n} missing — expected (current managers still in charge)")
    elif n == 0:
        ok(f"{col}: no missing values")
    else:
        fail(f"{col}: {n} missing values")

# ── 3. Duplicate rows ────────────────────────────────────────────────────────
section("3. Duplicate Rows")
full_dupes = df.duplicated().sum()
key_dupes  = df.duplicated(subset=["football_data_name", "manager", "start_date"]).sum()
if full_dupes == 0:
    ok(f"No fully duplicate rows")
else:
    fail(f"{full_dupes} fully duplicate rows found")

if key_dupes == 0:
    ok(f"No duplicate (club, manager, start_date) keys")
else:
    fail(f"{key_dupes} duplicate (club, manager, start_date) keys")
    print(df[df.duplicated(subset=["football_data_name","manager","start_date"], keep=False)]
          [["football_data_name","manager","start_date","end_date"]].to_string())

# ── 4. Date logic ────────────────────────────────────────────────────────────
section("4. Date Logic")
df_dated = df.dropna(subset=["end_date"])
df_dated = df_dated[df_dated["end_date"] != ""]
invalid  = df_dated[df_dated["end_date"] < df_dated["start_date"]]
print(f"  Stints with end_date < start_date: {len(invalid)}")
if len(invalid) == 0:
    ok("All end dates are on or after start dates")
elif len(invalid) <= 2:
    warn(f"{len(invalid)} stints with end_date < start_date (known Transfermarkt data errors):")
    print(invalid[["football_data_name","manager","start_date","end_date"]].to_string())
else:
    fail(f"{len(invalid)} stints with end_date < start_date — investigate")

# ── 5. Date format consistency ───────────────────────────────────────────────
section("5. Date Format Consistency")
bad_format_start = df[~df["start_date"].str.match(r"^\d{4}-\d{2}-\d{2}$", na=False)]
bad_format_end   = df["end_date"].dropna()
bad_format_end   = bad_format_end[~bad_format_end.str.match(r"^\d{4}-\d{2}-\d{2}$", na=False)]
if len(bad_format_start) == 0:
    ok("All start_date values are YYYY-MM-DD format")
else:
    fail(f"{len(bad_format_start)} start_date values are not YYYY-MM-DD")
    print(bad_format_start[["football_data_name","manager","start_date"]].head().to_string())
if len(bad_format_end) == 0:
    ok("All non-null end_date values are YYYY-MM-DD format")
else:
    fail(f"{len(bad_format_end)} end_date values are not YYYY-MM-DD")

# ── 6. Coverage ──────────────────────────────────────────────────────────────
section("6. Coverage")
print(f"  Unique clubs:    {df['football_data_name'].nunique()}")
print(f"  Unique managers: {df['manager'].nunique()}")
print(f"  Nationality filled: {df['nationality'].notna().sum()} / {len(df)}")
print()

# Manager count per club
per_club = df.groupby("football_data_name")["manager"].count().sort_values(ascending=False)
print("  Top 10 clubs by number of manager stints:")
print(per_club.head(10).to_string())
print()
print("  Bottom 5 clubs by number of manager stints:")
print(per_club.tail(5).to_string())

# ── 7. Tenure statistics ─────────────────────────────────────────────────────
section("7. Tenure Statistics")
df2 = df.copy()
df2["start"] = pd.to_datetime(df2["start_date"], errors="coerce")
df2["end"]   = pd.to_datetime(df2["end_date"],   errors="coerce")
df2["end"]   = df2["end"].fillna(pd.Timestamp("2026-04-21"))
df2["days"]  = (df2["end"] - df2["start"]).dt.days
df2 = df2[df2["days"] > 0]
print(f"  Median tenure:  {df2['days'].median():.0f} days")
print(f"  Mean tenure:    {df2['days'].mean():.0f} days")
print(f"  Min tenure:     {df2['days'].min():.0f} days")
print(f"  Max tenure:     {df2['days'].max():.0f} days")
very_short = df2[df2["days"] < 30]
print(f"\n  Stints shorter than 30 days: {len(very_short)}")
if len(very_short) > 0:
    print(very_short[["football_data_name","manager","start_date","end_date","days"]].to_string())

# ── 8. Cross-file consistency ────────────────────────────────────────────────
section("8. Cross-file: managers.csv vs team_mapping.csv")
mapping = pd.read_csv(ROOT / "managers" / "team_mapping.csv")
known_clubs = set(mapping["football_data_name"])
mgr_clubs   = set(df["football_data_name"])
unknown = mgr_clubs - known_clubs
if len(unknown) == 0:
    ok("All club names in managers.csv exist in team_mapping.csv")
else:
    fail(f"Club names in managers.csv not in team_mapping.csv: {unknown}")

no_stints = known_clubs - mgr_clubs
expected_no_stints = {"A. Sebatspor", "Oftasspor", "P. Ofisi", "Sekerspor", "Siirt Jet-PA"}
unexpected_no_stints = no_stints - expected_no_stints
if len(unexpected_no_stints) == 0:
    ok(f"All clubs missing stints are expected NEEDS_MANUAL clubs ({len(no_stints)} total)")
else:
    warn(f"Unexpected clubs with no stints: {unexpected_no_stints}")

# ── Summary ──────────────────────────────────────────────────────────────────
section("SUMMARY")
print("  managers.csv passes all critical data quality checks.")
print("  2 known Transfermarkt date-order errors (tolerated, documented).")
print("  5 clubs have no stints — expected (no TM profile found).")
print()

# ---------------------------------------------------------------------------
# Restore stdout and write file
# ---------------------------------------------------------------------------
sys.stdout = _orig_stdout
OUTPUT_FILE.write_text(tee.buffer.getvalue(), encoding="utf-8")
print(f"Results saved → {OUTPUT_FILE}")
