"""Validate Turkey capstone datasets for schema, missing values, and duplicates."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from ingestion import (
    MANAGER_CHARS_SCHEMA,
    MANAGER_SPELLS_SCHEMA,
    MATCHES_SCHEMA,
    TEAM_SEASONS_SCHEMA,
)

TABLE_SPECS = {
    "matches_raw": {
        "schema": MATCHES_SCHEMA,
        "key": ["match_id"],
        "critical": ["match_id", "season", "match_date", "home_team", "away_team", "home_goals", "away_goals", "league"],
    },
    "manager_spells": {
        "schema": MANAGER_SPELLS_SCHEMA,
        "key": ["spell_id"],
        "critical": ["spell_id", "team", "manager_name", "start_date"],
    },
    "manager_chars": {
        "schema": MANAGER_CHARS_SCHEMA,
        "key": ["manager_name"],
        "critical": ["manager_name"],
    },
    "team_seasons": {
        "schema": TEAM_SEASONS_SCHEMA,
        "key": ["team", "season"],
        "critical": ["team", "season"],
    },
    "matches_clean": {
        "schema": MATCHES_SCHEMA,
        "key": ["match_id"],
        "critical": ["match_id", "season", "match_date", "home_team", "away_team"],
    },
    "manager_clean": {
        "schema": MANAGER_SPELLS_SCHEMA,
        "key": ["spell_id"],
        "critical": ["spell_id", "team", "manager_name", "start_date"],
    },
    "manager_chars_clean": {
        "schema": MANAGER_CHARS_SCHEMA,
        "key": ["manager_name"],
        "critical": ["manager_name"],
    },
    "team_seasons_clean": {
        "schema": TEAM_SEASONS_SCHEMA,
        "key": ["team", "season"],
        "critical": ["team", "season"],
    },
    "analysis_panel": {
        "schema": MATCHES_SCHEMA + ["home_manager", "away_manager", "home_points", "away_points"],
        "key": ["match_id"],
        "critical": ["match_id", "home_team", "away_team"],
    },
    "manager_panel": {
        "schema": ["match_id", "season", "match_date", "team", "opponent", "is_home", "manager_name", "goals_for", "goals_against", "points"],
        "key": ["match_id", "team"],
        "critical": ["match_id", "team"],
    },
}


def _load_table(stem: str, roots: list[Path]) -> pd.DataFrame | None:
    for root in roots:
        for suffix in (".csv", ".parquet"):
            path = root / f"{stem}{suffix}"
            if path.exists():
                if suffix == ".csv":
                    return pd.read_csv(path)
                return pd.read_parquet(path)
    return None


def _validate_table(name: str, df: pd.DataFrame) -> dict[str, object]:
    spec = TABLE_SPECS[name]
    missing_columns = [column for column in spec["schema"] if column not in df.columns]
    duplicate_rows = int(df.duplicated(spec["key"]).sum())
    missing_values = {
        column: int(df[column].isna().sum())
        for column in spec["critical"]
        if column in df.columns and int(df[column].isna().sum()) > 0
    }
    malformed_manager_name_count = 0
    if "manager_name" in df.columns:
        malformed_manager_name_count = int(
            df["manager_name"].astype(str).str.contains(r"\d{2}/\d{2}/\d{4}", regex=True, na=False).sum()
        )
    return {
        "table": name,
        "rows": int(len(df)),
        "schema_ok": not missing_columns,
        "missing_columns": missing_columns,
        "duplicate_keys": duplicate_rows,
        "missing_critical_values": missing_values,
        "malformed_manager_names": malformed_manager_name_count,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate Turkey capstone datasets.")
    parser.add_argument("--raw-dir", default="data/raw")
    parser.add_argument("--processed-dir", default="data/processed")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    roots = [Path(args.raw_dir), Path(args.processed_dir)]
    results = []
    for table_name in TABLE_SPECS:
        df = _load_table(table_name, roots)
        if df is None:
            results.append(
                {
                    "table": table_name,
                    "status": "missing_file",
                    "rows": 0,
                    "schema_ok": False,
                    "missing_columns": [],
                    "duplicate_keys": 0,
                    "missing_critical_values": {},
                    "malformed_manager_names": 0,
                }
            )
            continue
        result = _validate_table(table_name, df)
        result["status"] = "ok"
        if result["missing_columns"] or result["duplicate_keys"] or result["missing_critical_values"] or result["malformed_manager_names"]:
            result["status"] = "failed_checks"
        results.append(result)

    payload = {"results": results}
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    else:
        print(json.dumps(payload, indent=2))
    if any(result["status"] != "ok" for result in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
