from __future__ import annotations

import pandas as pd

from brown_team_daai.quality import (
    check_allowed_values,
    check_missing_critical_values,
    check_required_columns,
    check_unique_key,
    summarize_quality_checks,
)


def test_quality_checks_flag_duplicates_and_missing_values() -> None:
    frame = pd.DataFrame(
        [
            {"match_id": "2023_1_1", "home_team": "Galatasaray", "away_team": "Fenerbahce"},
            {"match_id": "2023_1_1", "home_team": None, "away_team": "Besiktas"},
        ]
    )
    assert check_required_columns(frame, ["match_id", "home_team", "away_team"]) == []
    assert check_unique_key(frame, ["match_id"]) == 1
    assert check_missing_critical_values(frame, ["home_team", "away_team"]) == {"home_team": 1, "away_team": 0}


def test_check_allowed_values_reports_unexpected_categories() -> None:
    frame = pd.DataFrame({"league": ["Super Lig", "Other League"]})
    assert check_allowed_values(frame, "league", {"Super Lig"}) == {"Other League"}


def test_summarize_quality_checks_returns_compact_report() -> None:
    frame = pd.DataFrame([{"spell_id": 1, "team": "Galatasaray", "manager_name": "Manager A"}])
    summary = summarize_quality_checks(
        frame,
        required_columns=["spell_id", "team", "manager_name"],
        key_columns=["spell_id"],
        critical_columns=["team", "manager_name"],
    )
    assert summary["missing_columns"] == []
    assert summary["duplicate_keys"] == 0
    assert summary["missing_critical_values"] == {"team": 0, "manager_name": 0}
