"""Data quality checks for the Turkey capstone tables."""

from __future__ import annotations

from collections.abc import Iterable

import pandas as pd


def check_required_columns(df: pd.DataFrame, required_columns: Iterable[str]) -> list[str]:
    return [column for column in required_columns if column not in df.columns]


def check_unique_key(df: pd.DataFrame, key_columns: list[str]) -> int:
    return int(df.duplicated(key_columns).sum())


def check_missing_critical_values(df: pd.DataFrame, critical_columns: list[str]) -> dict[str, int]:
    return {column: int(df[column].isna().sum()) for column in critical_columns if column in df.columns}


def check_allowed_values(df: pd.DataFrame, column: str, allowed_values: set[str]) -> set[str]:
    if column not in df.columns:
        return set()
    observed = set(df[column].dropna().astype(str))
    return observed - allowed_values


def summarize_quality_checks(
    df: pd.DataFrame,
    *,
    required_columns: list[str],
    key_columns: list[str],
    critical_columns: list[str],
) -> dict[str, object]:
    return {
        "missing_columns": check_required_columns(df, required_columns),
        "duplicate_keys": check_unique_key(df, key_columns),
        "missing_critical_values": check_missing_critical_values(df, critical_columns),
    }
