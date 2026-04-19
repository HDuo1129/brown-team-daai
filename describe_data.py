"""Produce basic descriptive outputs for the Turkey capstone datasets."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


def _read_table(path: Path) -> pd.DataFrame:
    if path.suffix == ".parquet":
        return pd.read_parquet(path)
    return pd.read_csv(path)


def _find_table(directory: Path, stem: str) -> Path:
    for suffix in (".csv", ".parquet"):
        candidate = directory / f"{stem}{suffix}"
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"Missing table {stem} in {directory}")


def describe(raw_dir: Path, processed_dir: Path) -> dict[str, object]:
    matches = _read_table(_find_table(raw_dir, "matches_raw"))
    manager_spells = _read_table(_find_table(raw_dir, "manager_spells"))
    analysis_panel = _read_table(_find_table(processed_dir, "analysis_panel"))
    summary = {
        "matches": int(len(matches)),
        "teams": int(pd.concat([matches["home_team"], matches["away_team"]]).nunique()),
        "manager_spells": int(len(manager_spells)),
        "manager_changes": max(int(len(manager_spells) - manager_spells["team"].nunique()), 0),
        "goal_distribution": {
            "mean_home_goals": float(matches["home_goals"].mean()),
            "mean_away_goals": float(matches["away_goals"].mean()),
            "mean_total_goals": float((matches["home_goals"] + matches["away_goals"]).mean()),
        },
        "coverage_over_time": matches.groupby("season").size().to_dict(),
        "manager_assignment_missing": {
            "home_manager_missing": int(analysis_panel["home_manager"].isna().sum()),
            "away_manager_missing": int(analysis_panel["away_manager"].isna().sum()),
        },
    }
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Describe capstone data coverage and basic stats.")
    parser.add_argument("--raw-dir", default="data/raw")
    parser.add_argument("--processed-dir", default="data/processed")
    parser.add_argument("--out-dir", default="out")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = describe(Path(args.raw_dir), Path(args.processed_dir))
    (out_dir / "data_description.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    pd.DataFrame(
        [{"season": season, "match_count": count} for season, count in summary["coverage_over_time"].items()]
    ).to_csv(out_dir / "coverage_over_time.csv", index=False)


if __name__ == "__main__":
    main()
