"""
analysis/data_description.py
=============================
Generates key descriptive statistics and exhibits for the
Turkish Süper Lig dataset. Outputs an HTML report.

Usage:
    pip install pandas matplotlib
    python analysis/data_description.py
    # → opens analysis/data_description.html
"""

import subprocess
import tempfile
import csv
from datetime import datetime
from pathlib import Path

import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import base64
from io import BytesIO

ROOT = Path(__file__).parent.parent
OUT  = Path(__file__).parent / "data_description.html"


# ---------------------------------------------------------------------------
# Data loaders
# ---------------------------------------------------------------------------

def load_matches() -> pd.DataFrame:
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
            df["_season"] = Path(f).stem
            frames.append(df)
        except Exception:
            pass
        finally:
            Path(tmp_path).unlink(missing_ok=True)
    combined = pd.concat(frames, ignore_index=True)
    return combined.dropna(subset=["Date", "HomeTeam", "AwayTeam"])


def fig_to_b64(fig) -> str:
    buf = BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=110)
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode()


# ---------------------------------------------------------------------------
# Exhibits
# ---------------------------------------------------------------------------

def exhibit_matches_per_season(matches: pd.DataFrame) -> str:
    per_season = matches.groupby("_season").size().sort_index()
    fig, ax = plt.subplots(figsize=(11, 4))
    ax.bar(per_season.index, per_season.values, color="#2c7bb6", width=0.7)
    ax.set_xlabel("Season")
    ax.set_ylabel("Matches")
    ax.set_title("Matches per Season (1994–2026)")
    ax.tick_params(axis="x", rotation=70, labelsize=7)
    fig.tight_layout()
    return fig_to_b64(fig)


def exhibit_missing_coverage(matches: pd.DataFrame) -> str:
    cols = ["FTR", "FTHG", "FTAG", "HTHG", "HTAG", "HS", "AS", "HST", "AST",
            "HF", "AF", "HC", "AC", "HY", "AY", "B365H"]
    present_cols = [c for c in cols if c in matches.columns]
    pct = [(c, 100 * matches[c].notna().mean()) for c in present_cols]
    labels, vals = zip(*pct)

    fig, ax = plt.subplots(figsize=(9, 4))
    colors = ["#1a9641" if v >= 90 else "#fdae61" if v >= 50 else "#d7191c" for v in vals]
    ax.barh(labels, vals, color=colors)
    ax.set_xlim(0, 105)
    ax.set_xlabel("Coverage (%)")
    ax.set_title("Column Coverage Across All Seasons")
    ax.axvline(100, color="gray", lw=0.8, ls="--")
    for i, v in enumerate(vals):
        ax.text(v + 1, i, f"{v:.0f}%", va="center", fontsize=8)
    fig.tight_layout()
    return fig_to_b64(fig)


def exhibit_manager_tenure(managers: pd.DataFrame) -> str:
    df = managers.copy()
    df["start"] = pd.to_datetime(df["start_date"], errors="coerce")
    df["end"]   = pd.to_datetime(df["end_date"],   errors="coerce")
    df["end"]   = df["end"].fillna(pd.Timestamp("2026-04-20"))
    df["tenure_days"] = (df["end"] - df["start"]).dt.days
    df = df[df["tenure_days"] > 0]

    fig, ax = plt.subplots(figsize=(8, 4))
    ax.hist(df["tenure_days"], bins=50, color="#756bb1", edgecolor="white", linewidth=0.4)
    ax.set_xlabel("Tenure (days)")
    ax.set_ylabel("Number of stints")
    ax.set_title("Manager Stint Length Distribution")
    median = df["tenure_days"].median()
    ax.axvline(median, color="red", ls="--", lw=1.5, label=f"Median {median:.0f} days")
    ax.legend()
    fig.tight_layout()
    return fig_to_b64(fig)


def exhibit_manager_age(chars: pd.DataFrame) -> str:
    ages = pd.to_numeric(chars["age_at_appointment"], errors="coerce").dropna()
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.hist(ages, bins=40, color="#f46d43", edgecolor="white", linewidth=0.4)
    ax.set_xlabel("Age at appointment (years)")
    ax.set_ylabel("Number of stints")
    ax.set_title("Manager Age at Appointment")
    ax.axvline(ages.median(), color="black", ls="--", lw=1.5, label=f"Median {ages.median():.1f} yrs")
    ax.legend()
    fig.tight_layout()
    return fig_to_b64(fig)


def exhibit_nationality(managers: pd.DataFrame) -> str:
    top = managers["nationality"].value_counts().head(15)
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.barh(top.index[::-1], top.values[::-1], color="#4dac26")
    ax.set_xlabel("Number of stints")
    ax.set_title("Top 15 Manager Nationalities (by stint count)")
    fig.tight_layout()
    return fig_to_b64(fig)


def exhibit_home_advantage(ha: pd.DataFrame) -> str:
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.hist(ha["home_away_gap"], bins=40, color="#2c7bb6", edgecolor="white", linewidth=0.4)
    ax.axvline(0, color="black", lw=1)
    ax.axvline(ha["home_away_gap"].mean(), color="red", ls="--", lw=1.5,
               label=f"Mean gap = {ha['home_away_gap'].mean():.2f} PPG")
    ax.set_xlabel("Home PPG − Away PPG")
    ax.set_ylabel("Season-team observations")
    ax.set_title("Home Advantage Distribution (all teams, all seasons)")
    ax.legend()
    fig.tight_layout()
    return fig_to_b64(fig)


def exhibit_teams_by_region(loc: pd.DataFrame) -> str:
    counts = loc["region"].value_counts()
    fig, ax = plt.subplots(figsize=(7, 4))
    colors = ["#4575b4","#74add1","#abd9e9","#fee090","#fdae61","#f46d43","#d73027"]
    ax.bar(counts.index, counts.values, color=colors[:len(counts)])
    ax.set_ylabel("Number of clubs")
    ax.set_title("Clubs by Turkish Geographic Region")
    ax.tick_params(axis="x", rotation=25, labelsize=8)
    fig.tight_layout()
    return fig_to_b64(fig)


# ---------------------------------------------------------------------------
# HTML report
# ---------------------------------------------------------------------------

def img_tag(b64: str) -> str:
    return f'<img src="data:image/png;base64,{b64}" style="max-width:100%;margin:16px 0;">'


def stat_row(label: str, value: str) -> str:
    return f"<tr><td style='padding:4px 12px;color:#555'>{label}</td><td style='padding:4px 12px;font-weight:bold'>{value}</td></tr>"


def build_report():
    print("Loading data...")
    matches  = load_matches()
    managers = pd.read_csv(ROOT / "managers" / "managers.csv")
    profiles = pd.read_csv(ROOT / "managers" / "manager_profiles.csv")
    chars    = pd.read_csv(ROOT / "managers" / "manager_characteristics.csv")
    ha       = pd.read_csv(ROOT / "features" / "team_home_away.csv")
    loc      = pd.read_csv(ROOT / "features" / "team_location.csv")

    print("Building exhibits...")
    b_seasons  = exhibit_matches_per_season(matches)
    b_coverage = exhibit_missing_coverage(matches)
    b_tenure   = exhibit_manager_tenure(managers)
    b_age      = exhibit_manager_age(chars)
    b_nat      = exhibit_nationality(managers)
    b_ha       = exhibit_home_advantage(ha)
    b_region   = exhibit_teams_by_region(loc)

    dob_pct = 100 * ((profiles["date_of_birth"] != "") & profiles["date_of_birth"].notna()).mean()
    age_vals = pd.to_numeric(chars["age_at_appointment"], errors="coerce").dropna()

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Turkish Süper Lig — Data Description</title>
<style>
  body {{ font-family: -apple-system, sans-serif; max-width: 960px; margin: 40px auto; padding: 0 20px; color: #222; }}
  h1 {{ border-bottom: 3px solid #2c7bb6; padding-bottom: 8px; }}
  h2 {{ color: #2c7bb6; margin-top: 40px; }}
  table {{ border-collapse: collapse; margin: 10px 0; }}
  td, th {{ border: 1px solid #ddd; padding: 6px 12px; font-size: 0.9em; }}
  th {{ background: #f4f4f4; }}
  .stat-table td {{ border: none; }}
  .note {{ background: #fff8e1; border-left: 4px solid #ffc107; padding: 10px 16px; margin: 16px 0; font-size: 0.9em; }}
</style>
</head>
<body>

<h1>Turkish Süper Lig — Data Description</h1>
<p>Generated: {datetime.now().strftime("%Y-%m-%d %H:%M")} &nbsp;|&nbsp;
<a href="https://github.com/FarangizJ/brown-team-daai">GitHub Repository</a></p>

<h2>1. Match Data</h2>
<table class="stat-table">
  {stat_row("Total matches", f"{len(matches):,}")}
  {stat_row("Seasons covered", f"{matches['_season'].nunique()} (1994/95 – 2025/26)")}
  {stat_row("Unique clubs", str(matches['HomeTeam'].nunique()))}
  {stat_row("Seasons with match stats (shots/cards)", "9 (2017/18 – 2025/26)")}
  {stat_row("Seasons with betting odds", "25 (2001/02 – 2025/26)")}
</table>
{img_tag(b_seasons)}
{img_tag(b_coverage)}
<div class="note">⚠ <strong>Date format:</strong> Seasons 1994–2005 and 2007–2017 use DD/MM/YY (2-digit year).
Seasons 2006–07 and 2018–2026 use DD/MM/YYYY. Both formats must be handled when joining to manager data.</div>

<h2>2. Manager Stints</h2>
<table class="stat-table">
  {stat_row("Total coaching stints", f"{len(managers):,}")}
  {stat_row("Unique clubs covered", str(managers['football_data_name'].nunique()))}
  {stat_row("Unique managers", str(managers['manager'].nunique()))}
  {stat_row("Currently in charge (no end_date)", str((managers['end_date'].isna() | (managers['end_date']=='')).sum()))}
  {stat_row("Clubs with no TM profile", "5 (A. Sebatspor, Oftasspor, P. Ofisi, Sekerspor, Siirt Jet-PA)")}
</table>
{img_tag(b_tenure)}
{img_tag(b_nat)}

<h2>3. Manager Characteristics</h2>
<table class="stat-table">
  {stat_row("Unique manager profiles", f"{len(profiles):,}")}
  {stat_row("DOB coverage", f"{dob_pct:.1f}%")}
  {stat_row("Age at appointment — min", f"{age_vals.min():.1f} yrs")}
  {stat_row("Age at appointment — median", f"{age_vals.median():.1f} yrs")}
  {stat_row("Age at appointment — max", f"{age_vals.max():.1f} yrs")}
</table>
{img_tag(b_age)}

<h2>4. Home / Away Performance</h2>
<table class="stat-table">
  {stat_row("Season×team rows", f"{len(ha):,}")}
  {stat_row("Average home advantage (PPG gap)", f"{ha['home_away_gap'].mean():.3f}")}
  {stat_row("Largest home advantage", f"{ha['home_away_gap'].max():.3f} ({ha.loc[ha['home_away_gap'].idxmax(), 'team']}, {ha.loc[ha['home_away_gap'].idxmax(), 'season']})")}
  {stat_row("Teams with home_away_gap < 0", str((ha['home_away_gap'] < 0).sum()))}
</table>
{img_tag(b_ha)}

<h2>5. Team Locations</h2>
<table class="stat-table">
  {stat_row("Total clubs mapped", str(len(loc)))}
  {stat_row("Regions covered", str(loc['region'].nunique()))}
</table>
{img_tag(b_region)}

<table>
<tr><th>Region</th><th>Clubs</th><th>Example clubs</th></tr>
{''.join(
    f"<tr><td>{r}</td><td>{len(loc[loc['region']==r])}</td><td>{', '.join(loc[loc['region']==r]['football_data_name'].tolist()[:3])}</td></tr>"
    for r in loc['region'].value_counts().index
)}
</table>

<h2>6. Known Data Quality Issues</h2>
<table>
<tr><th>Issue</th><th>Scope</th><th>Impact</th></tr>
<tr><td>5 clubs with no Transfermarkt profile</td><td>A. Sebatspor, Oftasspor, P. Ofisi, Sekerspor, Siirt Jet-PA</td><td>No manager data for these clubs (all 1990s era)</td></tr>
<tr><td>Mixed date format in match CSVs</td><td>Seasons 1994–2005, 2007–2017</td><td>Requires dual-format parsing for manager joins</td></tr>
<tr><td>2 stints with end_date &lt; start_date</td><td>Konyaspor 1988, Karsiyaka 2006</td><td>Transfermarkt data errors; negligible effect</td></tr>
<tr><td>Match stats only from 2017/18</td><td>23 of 32 seasons have no shots/cards data</td><td>Shot-based models limited to recent era</td></tr>
<tr><td>TM date precision (1990s)</td><td>Early career stints</td><td>Day-level joins may misattribute manager near a change date</td></tr>
</table>

</body>
</html>"""

    OUT.write_text(html, encoding="utf-8")
    print(f"\nReport written → {OUT}")
    print("Open in browser to view.")


if __name__ == "__main__":
    build_report()
