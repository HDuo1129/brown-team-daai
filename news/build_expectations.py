"""
news/build_expectations.py
==========================
Aggregate classified articles into a (team, gameweek) expectations panel.

Reads:  news/articles_classified.csv
Writes: out/expectations.csv

Gameweek unit: ISO calendar week (e.g. 2025-W42).
One row per (team, gameweek) — the object that will be merged onto the
match + manager-change panel in Session 3.

Usage:
    python news/build_expectations.py
"""
import pandas as pd
from pathlib import Path

ROOT          = Path(__file__).parent.parent
CLASSIFIED    = ROOT / "news" / "articles_classified.csv"
OUT_CSV       = ROOT / "out" / "expectations.csv"


def load_classified() -> pd.DataFrame:
    if not CLASSIFIED.exists():
        raise FileNotFoundError(f"{CLASSIFIED} not found — run classify_articles.py first")
    df = pd.read_csv(CLASSIFIED, parse_dates=["date"])
    if df.empty:
        raise ValueError("articles_classified.csv is empty")
    return df


def add_gameweek(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    iso = df["date"].dt.isocalendar()
    df["gameweek"] = iso["year"].astype(str) + "-W" + iso["week"].astype(str).str.zfill(2)
    return df


def aggregate(df: pd.DataFrame) -> pd.DataFrame:
    """One row per (team, gameweek) with avg_grade and n_news."""
    all_articles  = df.groupby(["team", "gameweek"]).agg(n_news=("score", "count")).reset_index()
    rel = df[df["is_relevant"] == True]
    rel_agg = rel.groupby(["team", "gameweek"]).agg(
        avg_grade=("score_norm", "mean"),
        n_relevant=("score_norm", "count"),
    ).reset_index()
    panel = all_articles.merge(rel_agg, on=["team", "gameweek"], how="left")
    panel = panel.rename(columns={"gameweek": "date"})
    panel["avg_grade"]  = panel["avg_grade"].fillna(0.0).round(4)
    panel["n_relevant"] = panel["n_relevant"].fillna(0).astype(int)
    panel = panel.sort_values(["team", "date"]).reset_index(drop=True)
    return panel


def validate_panel(panel: pd.DataFrame) -> None:
    required = {"team", "date", "avg_grade", "n_news"}
    missing = required - set(panel.columns)
    if missing:
        raise ValueError(f"Expectations panel missing columns: {missing}")
    dupes = panel.duplicated(["team", "date"]).sum()
    if dupes:
        raise ValueError(f"{dupes} duplicate (team, date) pairs in expectations panel")
    if panel["avg_grade"].between(0, 1).all() is False:
        raise ValueError("avg_grade out of [0, 1] range")


def main() -> None:
    df = load_classified()
    print(f"Loaded {len(df)} classified articles | relevant: {df['is_relevant'].sum()}")

    df = add_gameweek(df)
    panel = aggregate(df)
    validate_panel(panel)

    OUT_CSV.parent.mkdir(exist_ok=True)
    panel.to_csv(OUT_CSV, index=False)

    teams = panel["team"].nunique()
    weeks = panel["date"].nunique()
    print(f"Expectations panel: {len(panel)} rows | {teams} teams | {weeks} gameweeks → {OUT_CSV}")
    print(panel.head(10).to_string(index=False))


if __name__ == "__main__":
    main()
