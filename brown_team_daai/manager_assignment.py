"""Helpers for assigning managers to matches by date range."""

from __future__ import annotations

import pandas as pd


def get_manager_on_date(team: str, date: str | pd.Timestamp, spells_df: pd.DataFrame) -> str | None:
    """Return the manager in charge of ``team`` on ``date`` from ``spells_df``."""
    match_date = pd.Timestamp(date).normalize()
    team_spells = spells_df.loc[spells_df["team"].eq(team)].copy()
    if team_spells.empty:
        return None

    team_spells["start_date"] = pd.to_datetime(team_spells["start_date"]).dt.normalize()
    team_spells["end_date"] = pd.to_datetime(team_spells["end_date"]).dt.normalize()
    active_spells = team_spells.loc[
        team_spells["start_date"].le(match_date)
        & team_spells["end_date"].fillna(pd.Timestamp.max).ge(match_date)
    ].sort_values(["start_date", "end_date"], ascending=[False, False])
    if active_spells.empty:
        return None
    return active_spells.iloc[0]["manager_name"]

