from __future__ import annotations

import pandas as pd

import ingestion


def test_build_analysis_panel_adds_managers_and_points() -> None:
    matches = pd.DataFrame(
        [
            {
                "match_id": "2023_1_1",
                "season": "2023/24",
                "match_date": "2023-09-16",
                "home_team": "Galatasaray",
                "away_team": "Fenerbahce",
                "home_goals": 2,
                "away_goals": 1,
                "league": "Super Lig",
            }
        ]
    )
    spells = pd.DataFrame(
        [
            {"spell_id": 1, "team": "Galatasaray", "manager_name": "Manager A", "start_date": "2023-07-01", "end_date": None, "departure_reason": pd.NA, "is_caretaker": False},
            {"spell_id": 2, "team": "Fenerbahce", "manager_name": "Manager B", "start_date": "2023-07-01", "end_date": None, "departure_reason": pd.NA, "is_caretaker": False},
        ]
    )
    panel = ingestion.build_analysis_panel(matches, spells)
    assert panel.loc[0, "home_manager"] == "Manager A"
    assert panel.loc[0, "away_manager"] == "Manager B"
    assert panel.loc[0, "home_points"] == 3
    assert panel.loc[0, "away_points"] == 0


def test_standardize_team_columns_uses_alias_map() -> None:
    frame = pd.DataFrame({"home_team": ["Besiktas JK"], "away_team": ["Galatasaray AS"]})
    alias_map = {"besiktas jk": "Besiktas", "galatasaray as": "Galatasaray"}
    standardized = ingestion.standardize_team_columns(frame, alias_map, ["home_team", "away_team"])
    assert standardized.loc[0, "home_team"] == "Besiktas"
    assert standardized.loc[0, "away_team"] == "Galatasaray"


def test_clean_manager_spells_frame_removes_birthdate_suffix() -> None:
    frame = pd.DataFrame(
        [{"spell_id": 1, "team": "Antalyaspor", "manager_name": "John Doe01/02/1980", "start_date": "2020-01-01", "end_date": None}]
    )
    cleaned = ingestion.clean_manager_spells_frame(frame)
    assert cleaned.loc[0, "manager_name"] == "John Doe"
    assert cleaned.loc[0, "birth_date"] == "1980-02-01"


def test_build_team_seasons_from_matches_derives_previous_position() -> None:
    matches = pd.DataFrame(
        [
            {"match_id": "2023_1_1", "season": "2023/24", "match_date": "2023-08-01", "home_team": "A", "away_team": "B", "home_goals": 1, "away_goals": 0, "league": "Super Lig"},
            {"match_id": "2023_1_2", "season": "2023/24", "match_date": "2023-08-02", "home_team": "B", "away_team": "A", "home_goals": 0, "away_goals": 2, "league": "Super Lig"},
            {"match_id": "2024_1_1", "season": "2024/25", "match_date": "2024-08-01", "home_team": "A", "away_team": "B", "home_goals": 0, "away_goals": 1, "league": "Super Lig"},
        ]
    )
    team_seasons = ingestion.build_team_seasons_from_matches(matches)
    next_season_a = team_seasons.loc[(team_seasons["team"] == "A") & (team_seasons["season"] == "2024/25")].iloc[0]
    assert next_season_a["prev_season_position"] == 1
