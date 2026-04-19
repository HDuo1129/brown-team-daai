"""Data ingestion pipeline for Turkish Super Lig research datasets."""

from __future__ import annotations

import argparse
import json
import logging
import random
import re
import time
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin

import io
import pandas as pd
import requests
from bs4 import BeautifulSoup

from brown_team_daai.manager_assignment import get_manager_on_date

LOGGER = logging.getLogger(__name__)
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; data-ingestion/1.0)"}
RETRYABLE_STATUS_CODES = {429, 503}
RAW_TABLES = ("matches_raw", "manager_spells", "manager_chars", "team_seasons")

MATCHES_SCHEMA = [
    "match_id",
    "season",
    "match_date",
    "home_team",
    "away_team",
    "home_goals",
    "away_goals",
    "league",
]
MANAGER_PANEL_SCHEMA = [
    "match_id",
    "season",
    "match_date",
    "team",
    "opponent",
    "is_home",
    "manager_name",
    "goals_for",
    "goals_against",
    "points",
]
MANAGER_SPELLS_SCHEMA = [
    "spell_id",
    "team",
    "manager_name",
    "start_date",
    "end_date",
    "departure_reason",
    "is_caretaker",
]
MANAGER_CHARS_SCHEMA = [
    "manager_name",
    "nationality",
    "is_foreign",
    "birth_date",
    "played_professionally",
    "prior_clubs_count",
    "career_win_rate",
]
TEAM_SEASONS_SCHEMA = [
    "team",
    "season",
    "prev_season_position",
    "squad_market_value_eur",
]


def _build_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(HEADERS)
    return session


def _request_text(url: str, session: requests.Session | None = None, max_attempts: int = 5) -> str:
    active_session = session or _build_session()
    for attempt in range(1, max_attempts + 1):
        response = active_session.get(url, timeout=30)
        if response.status_code not in RETRYABLE_STATUS_CODES:
            response.raise_for_status()
            return response.text
        if attempt == max_attempts:
            response.raise_for_status()
        delay = (2 ** (attempt - 1)) + random.uniform(0, 0.25)
        LOGGER.warning("Retrying URL=%s status=%s attempt=%s sleep=%.2f", url, response.status_code, attempt, delay)
        time.sleep(delay)
    raise ValueError(f"Failed to fetch URL after retries: {url}")


def _clean_columns(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = [re.sub(r"[^a-z0-9]+", "_", str(col).strip().lower()).strip("_") for col in df.columns]
    return df


def _ensure_schema(df: pd.DataFrame, schema: list[str]) -> pd.DataFrame:
    frame = df.copy()
    for column in schema:
        if column not in frame.columns:
            frame[column] = pd.NA
    return frame.loc[:, schema]


def _table_headers(table) -> list[str]:
    return [th.get_text(" ", strip=True).lower() for th in table.select("tr th")]


def _find_candidate_table(soup: BeautifulSoup, keywords: Iterable[str]):
    best_table = None
    best_score = -1
    for table in soup.select("table.items, div.box table, table"):
        headers = _table_headers(table)
        if not headers:
            continue
        header_text = " ".join(headers)
        score = sum(keyword in header_text for keyword in keywords)
        if table.select('a[href*="/profil/trainer/"], a[href*="/trainer/"]'):
            score += 2
        if score > best_score:
            best_score = score
            best_table = table
    if best_table is None or best_score <= 0:
        raise ValueError("No matching table found on page.")
    return best_table


def _table_to_frame(table) -> pd.DataFrame:
    rows = []
    for row in table.select("tr"):
        cells = row.select("th, td")
        values = [cell.get_text(" ", strip=True) for cell in cells]
        if values:
            rows.append(values)
    if len(rows) < 2:
        return pd.DataFrame()
    width = max(len(row) for row in rows)
    normalized = [row + [""] * (width - len(row)) for row in rows]
    return _clean_columns(pd.DataFrame(normalized[1:], columns=normalized[0]))


def _extract_links(table, base_url: str) -> list[str]:
    links = []
    for row in table.select("tr")[1:]:
        anchor = row.select_one("td a[href]")
        links.append(urljoin(base_url, anchor["href"]) if anchor else "")
    return links


def _parse_date(series: pd.Series) -> pd.Series:
    cleaned = series.astype(str).str.strip()
    parsed = pd.to_datetime(cleaned, format="%d/%m/%Y", errors="coerce")
    missing = parsed.isna()
    if missing.any():
        parsed.loc[missing] = pd.to_datetime(cleaned.loc[missing], format="%Y-%m-%d", errors="coerce")
    if parsed.isna().any():
        missing = parsed.isna()
        parsed.loc[missing] = pd.to_datetime(cleaned.loc[missing], dayfirst=True, errors="coerce")
    return parsed.dt.strftime("%Y-%m-%d")


def _parse_number(series: pd.Series) -> pd.Series:
    cleaned = series.astype(str).str.replace(r"[^\d,.\-]", "", regex=True).str.replace(".", "", regex=False)
    cleaned = cleaned.str.replace(",", ".", regex=False)
    return pd.to_numeric(cleaned, errors="coerce")


def _extract_market_value_eur(series: pd.Series) -> pd.Series:
    text = series.astype(str).str.lower().str.replace("€", "", regex=False).str.strip()
    factors = text.map(lambda value: 1_000_000 if "m" in value else 1_000 if "k" in value else 1)
    numbers = pd.to_numeric(text.str.replace(r"[^0-9,.\-]", "", regex=True).str.replace(",", ".", regex=False), errors="coerce")
    return numbers * factors


def _series(frame: pd.DataFrame, *names: str) -> pd.Series:
    for name in names:
        if name in frame.columns:
            return frame[name]
    return pd.Series(pd.NA, index=frame.index, dtype="object")


def _extract_first_column_links(table, base_url: str) -> tuple[list[str], list[str]]:
    names = []
    links = []
    for row in table.select("tr")[1:]:
        first_cell = row.select_one("td")
        anchor = first_cell.select_one("a[href]") if first_cell else None
        names.append(anchor.get_text(" ", strip=True) if anchor else "")
        links.append(urljoin(base_url, anchor["href"]) if anchor else "")
    return names, links


def _header_index_map(table) -> dict[str, int]:
    headers = _table_headers(table)
    return {_clean_columns(pd.DataFrame(columns=headers)).columns[idx]: idx for idx in range(len(headers))}


def _table_data_rows(table) -> list:
    rows = table.select("tbody tr")
    if rows:
        return [row for row in rows if row.select("td")]
    return [row for row in table.select("tr") if row.select("td")]


def _cell_text(cells: list, idx: int | None) -> str:
    if idx is None or idx >= len(cells):
        return ""
    return cells[idx].get_text(" ", strip=True)


def _find_first_date_strings(texts: list[str]) -> list[str]:
    date_pattern = re.compile(r"\b\d{2}/\d{2}/\d{4}\b|\b\d{4}-\d{2}-\d{2}\b")
    return [match.group(0) for text in texts for match in date_pattern.finditer(text)]


def clean_manager_name(value: str | None) -> str | None:
    if value is None or pd.isna(value):
        return None
    cleaned = re.sub(r"\d{2}/\d{2}/\d{4}$", "", str(value)).strip()
    return cleaned or None


def extract_birth_date_from_manager_name(value: str | None) -> str | None:
    if value is None or pd.isna(value):
        return None
    match = re.search(r"(\d{2}/\d{2}/\d{4})$", str(value))
    if not match:
        return None
    return _parse_date(pd.Series([match.group(1)])).iloc[0]


def clean_manager_spells_frame(df: pd.DataFrame) -> pd.DataFrame:
    frame = df.copy()
    if "manager_name" in frame.columns:
        frame["manager_name_raw"] = frame["manager_name"]
        frame["manager_name"] = frame["manager_name"].map(clean_manager_name)
        if "birth_date" not in frame.columns:
            frame["birth_date"] = frame["manager_name_raw"].map(extract_birth_date_from_manager_name)
    return frame


def _safe_fetch(loader, url: str, table_name: str) -> pd.DataFrame:
    try:
        return loader(url)
    except Exception as exc:
        LOGGER.warning("Failed table=%s url=%s error=%s", table_name, url, exc)
        return pd.DataFrame()


def _write_output(df: pd.DataFrame, out_dir: Path, stem: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    if len(df) > 50_000:
        path = out_dir / f"{stem}.parquet"
        df.to_parquet(path, index=False)
        return path
    path = out_dir / f"{stem}.csv"
    df.to_csv(path, index=False)
    return path


def _read_output(path: Path) -> pd.DataFrame:
    if path.suffix == ".parquet":
        return pd.read_parquet(path)
    return pd.read_csv(path)


def _read_table_from_dir(directory: Path, stem: str) -> pd.DataFrame:
    for suffix in (".parquet", ".csv"):
        path = directory / f"{stem}{suffix}"
        if path.exists():
            return _read_output(path)
    raise FileNotFoundError(f"Table not found for stem={stem} in {directory}")


def _normalize_name(value: str | None) -> str | None:
    if value is None or pd.isna(value):
        return None
    normalized = re.sub(r"[^a-z0-9]+", " ", str(value).lower()).strip()
    return normalized or None


def load_team_alias_map(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    frame = pd.read_csv(path)
    alias_map = {}
    for _, row in frame.iterrows():
        canonical = row["canonical_name"]
        alias_map[_normalize_name(canonical)] = canonical
        aliases = str(row.get("aliases", "")).split("|")
        for alias in aliases:
            cleaned = _normalize_name(alias)
            if cleaned:
                alias_map[cleaned] = canonical
    return alias_map


def standardize_team_name(value: str | None, alias_map: dict[str, str]) -> str | None:
    normalized = _normalize_name(value)
    if normalized is None:
        return None
    return alias_map.get(normalized, value)


def standardize_team_columns(df: pd.DataFrame, alias_map: dict[str, str], columns: Iterable[str]) -> pd.DataFrame:
    frame = df.copy()
    for column in columns:
        if column in frame.columns:
            frame[column] = frame[column].map(lambda value: standardize_team_name(value, alias_map))
    return frame


def load_source_config(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _fetch_table_from_config(name: str, config: dict) -> pd.DataFrame:
    urls = config.get("urls", [])
    if not urls:
        raise ValueError(f"No URLs configured for table={name}")
    loaders = {
        "matches_raw": fetch_matches_csv,
        "manager_spells": scrape_manager_spells,
        "manager_chars": scrape_manager_chars,
        "team_seasons": scrape_team_seasons,
    }
    frames = [frame for frame in (_safe_fetch(loaders[name], url, name) for url in urls) if not frame.empty]
    if not frames:
        raise ValueError(f"No rows fetched for table={name}")
    frame = pd.concat(frames, ignore_index=True)
    if name == "matches_raw":
        frame = frame.sort_values("match_date").drop_duplicates("match_id")
    if name == "manager_spells":
        frame = clean_manager_spells_frame(frame)
        frame = frame.sort_values(["team", "start_date", "manager_name"]).reset_index(drop=True)
        frame["spell_id"] = range(1, len(frame) + 1)
    return frame


def collect_manager_profile_urls(url: str) -> list[str]:
    """Collect unique manager profile URLs from a club's staff-history page."""
    html = _request_text(url)
    soup = BeautifulSoup(html, "html.parser")
    table = _find_candidate_table(soup, ("manager", "trainer", "appointed", "from", "name", "date of birth"))
    links = [link for link in _extract_links(table, url) if "/trainer/" in link or "/profil/trainer/" in link]
    return list(dict.fromkeys(links))


def build_manager_chars_from_spells(spells_df: pd.DataFrame) -> pd.DataFrame:
    spells = clean_manager_spells_frame(spells_df)
    grouped = spells.groupby("manager_name", dropna=True)
    frame = grouped.agg(
        birth_date=("birth_date", "first"),
        prior_clubs_count=("team", lambda s: max(int(pd.Series(s).dropna().nunique()) - 1, 0)),
    ).reset_index()
    frame["nationality"] = "Unknown"
    frame["is_foreign"] = pd.NA
    frame["played_professionally"] = pd.NA
    frame["career_win_rate"] = pd.NA
    frame = _ensure_schema(frame, MANAGER_CHARS_SCHEMA)
    return frame.sort_values("manager_name").reset_index(drop=True)


def build_team_seasons_from_matches(matches_df: pd.DataFrame) -> pd.DataFrame:
    home = matches_df[["season", "home_team", "home_goals", "away_goals"]].rename(
        columns={"home_team": "team", "home_goals": "goals_for", "away_goals": "goals_against"}
    )
    away = matches_df[["season", "away_team", "away_goals", "home_goals"]].rename(
        columns={"away_team": "team", "away_goals": "goals_for", "home_goals": "goals_against"}
    )
    team_matches = pd.concat([home, away], ignore_index=True)
    team_matches["points"] = (
        (team_matches["goals_for"] > team_matches["goals_against"]) * 3
        + (team_matches["goals_for"] == team_matches["goals_against"])
    ).astype("Int64")
    standings = (
        team_matches.groupby(["season", "team"], as_index=False)
        .agg(points=("points", "sum"), goal_diff=("goals_for", "sum"))
        .sort_values(["season", "points", "goal_diff", "team"], ascending=[True, False, False, True])
    )
    standings["position"] = standings.groupby("season").cumcount().add(1)
    season_order = sorted(standings["season"].dropna().unique())
    previous = {
        season_order[idx + 1]: standings.loc[standings["season"].eq(season_order[idx]), ["team", "position"]].rename(
            columns={"position": "prev_season_position"}
        )
        for idx in range(len(season_order) - 1)
    }
    frames = []
    for season in season_order:
        current = standings.loc[standings["season"].eq(season), ["team"]].copy()
        current["season"] = season
        prev = previous.get(season, pd.DataFrame(columns=["team", "prev_season_position"]))
        current = current.merge(prev, on="team", how="left")
        current["squad_market_value_eur"] = pd.NA
        frames.append(current)
    frame = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=TEAM_SEASONS_SCHEMA)
    return _ensure_schema(frame, TEAM_SEASONS_SCHEMA)


def run_raw_pipeline(config_path: Path, raw_dir: Path) -> dict[str, Path]:
    config = load_source_config(config_path)
    raw_dir.mkdir(parents=True, exist_ok=True)
    outputs = {}
    matches_raw = pd.DataFrame()
    manager_spells = pd.DataFrame()
    manager_spells_enriched = pd.DataFrame()
    for name in ("matches_raw", "manager_spells"):
        table_config = config.get(name, {})
        if not table_config.get("urls"):
            LOGGER.warning("Skipping table=%s because no URLs are configured", name)
            continue
        try:
            frame = _fetch_table_from_config(name, table_config)
        except Exception as exc:
            fallback_path = raw_dir / f"{name}.csv"
            if fallback_path.exists():
                LOGGER.warning("Using existing raw file for table=%s because fetch failed: %s", name, exc)
                frame = _read_output(fallback_path)
                if name == "manager_spells":
                    frame = clean_manager_spells_frame(frame)
            else:
                raise
        outputs[name] = _write_output(frame, raw_dir, name)
        LOGGER.info("Saved raw table=%s path=%s", name, outputs[name])
        if name == "matches_raw":
            matches_raw = frame
        if name == "manager_spells":
            manager_spells_enriched = frame.copy()
            manager_spells = _ensure_schema(frame, MANAGER_SPELLS_SCHEMA)
            outputs[name] = _write_output(manager_spells, raw_dir, name)
            LOGGER.info("Re-saved manager_spells with documented schema path=%s", outputs[name])
    team_config = config.get("team_seasons", {})
    if team_config.get("urls"):
        try:
            team_seasons = _fetch_table_from_config("team_seasons", team_config)
        except Exception as exc:
            LOGGER.warning("Falling back to derived team_seasons because scraping failed: %s", exc)
            team_seasons = build_team_seasons_from_matches(matches_raw)
    else:
        LOGGER.warning("No team_seasons URLs configured; deriving team_seasons from matches_raw")
        team_seasons = build_team_seasons_from_matches(matches_raw)
    if not team_seasons.empty:
        outputs["team_seasons"] = _write_output(team_seasons, raw_dir, "team_seasons")
        LOGGER.info("Saved raw table=team_seasons path=%s", outputs["team_seasons"])
    manager_config = config.get("manager_chars", {})
    manager_urls = list(manager_config.get("urls", []))
    if not manager_urls and config.get("manager_spells", {}).get("urls"):
        for history_url in config["manager_spells"]["urls"]:
            try:
                manager_urls.extend(collect_manager_profile_urls(history_url))
            except Exception as exc:
                LOGGER.warning("Failed to derive manager profile URLs from %s: %s", history_url, exc)
        manager_urls = list(dict.fromkeys(manager_urls))
    if manager_urls:
        frames = [frame for frame in (_safe_fetch(scrape_manager_chars, url, "manager_chars") for url in manager_urls) if not frame.empty]
        frame = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
        if frame.empty:
            frame = build_manager_chars_from_spells(manager_spells_enriched if not manager_spells_enriched.empty else manager_spells)
    else:
        LOGGER.warning("No manager_chars URLs could be derived; building fallback manager_chars from manager_spells")
        frame = build_manager_chars_from_spells(manager_spells_enriched if not manager_spells_enriched.empty else manager_spells)
    if not frame.empty:
        frame = frame.drop_duplicates("manager_name").reset_index(drop=True)
        outputs["manager_chars"] = _write_output(frame, raw_dir, "manager_chars")
        LOGGER.info("Saved raw table=manager_chars path=%s", outputs["manager_chars"])
    return outputs


def build_analysis_panel(
    matches_df: pd.DataFrame,
    spells_df: pd.DataFrame,
    team_seasons_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    panel = matches_df.copy()
    panel["home_manager"] = panel.apply(
        lambda row: get_manager_on_date(row["home_team"], row["match_date"], spells_df),
        axis=1,
    )
    panel["away_manager"] = panel.apply(
        lambda row: get_manager_on_date(row["away_team"], row["match_date"], spells_df),
        axis=1,
    )
    panel["home_points"] = (
        (panel["home_goals"] > panel["away_goals"]) * 3
        + (panel["home_goals"] == panel["away_goals"]) * 1
    ).astype("Int64")
    panel["away_points"] = (
        (panel["away_goals"] > panel["home_goals"]) * 3
        + (panel["away_goals"] == panel["home_goals"]) * 1
    ).astype("Int64")
    if team_seasons_df is not None and not team_seasons_df.empty:
        team_seasons = team_seasons_df.rename(
            columns={
                "team": "home_team",
                "prev_season_position": "home_prev_season_position",
                "squad_market_value_eur": "home_squad_market_value_eur",
            }
        )
        panel = panel.merge(
            team_seasons[["home_team", "season", "home_prev_season_position", "home_squad_market_value_eur"]],
            on=["home_team", "season"],
            how="left",
        )
        away_team_seasons = team_seasons_df.rename(
            columns={
                "team": "away_team",
                "prev_season_position": "away_prev_season_position",
                "squad_market_value_eur": "away_squad_market_value_eur",
            }
        )
        panel = panel.merge(
            away_team_seasons[["away_team", "season", "away_prev_season_position", "away_squad_market_value_eur"]],
            on=["away_team", "season"],
            how="left",
        )
    return panel


def build_manager_panel(matches_df: pd.DataFrame, analysis_panel: pd.DataFrame) -> pd.DataFrame:
    home = analysis_panel[
        ["match_id", "season", "match_date", "home_team", "away_team", "home_manager", "home_goals", "away_goals", "home_points"]
    ].rename(
        columns={
            "home_team": "team",
            "away_team": "opponent",
            "home_manager": "manager_name",
            "home_goals": "goals_for",
            "away_goals": "goals_against",
            "home_points": "points",
        }
    )
    home["is_home"] = True
    away = analysis_panel[
        ["match_id", "season", "match_date", "away_team", "home_team", "away_manager", "away_goals", "home_goals", "away_points"]
    ].rename(
        columns={
            "away_team": "team",
            "home_team": "opponent",
            "away_manager": "manager_name",
            "away_goals": "goals_for",
            "home_goals": "goals_against",
            "away_points": "points",
        }
    )
    away["is_home"] = False
    panel = pd.concat([home, away], ignore_index=True)
    return panel.loc[:, MANAGER_PANEL_SCHEMA]


def build_processed_datasets(raw_dir: Path, processed_dir: Path, team_names_path: Path) -> dict[str, Path]:
    alias_map = load_team_alias_map(team_names_path)
    matches_raw = standardize_team_columns(
        _read_table_from_dir(raw_dir, "matches_raw"),
        alias_map,
        ["home_team", "away_team"],
    )
    manager_spells = standardize_team_columns(
        clean_manager_spells_frame(_read_table_from_dir(raw_dir, "manager_spells")),
        alias_map,
        ["team"],
    )
    try:
        manager_chars = _read_table_from_dir(raw_dir, "manager_chars")
    except FileNotFoundError:
        manager_chars = build_manager_chars_from_spells(manager_spells)
    processed_dir.mkdir(parents=True, exist_ok=True)
    outputs = {
        "matches_clean": _write_output(matches_raw.drop_duplicates("match_id"), processed_dir, "matches_clean"),
        "manager_clean": _write_output(manager_spells.drop_duplicates("spell_id"), processed_dir, "manager_clean"),
        "manager_chars_clean": _write_output(manager_chars.drop_duplicates("manager_name"), processed_dir, "manager_chars_clean"),
    }
    team_seasons = pd.DataFrame()
    try:
        team_seasons = standardize_team_columns(
            _read_table_from_dir(raw_dir, "team_seasons"),
            alias_map,
            ["team"],
        )
        outputs["team_seasons_clean"] = _write_output(
            team_seasons.drop_duplicates(["team", "season"]),
            processed_dir,
            "team_seasons_clean",
        )
    except FileNotFoundError:
        LOGGER.warning("team_seasons raw table not found; analysis_panel will omit team strength controls")
    analysis_panel = build_analysis_panel(matches_raw, manager_spells, team_seasons)
    manager_panel = build_manager_panel(matches_raw, analysis_panel)
    outputs["manager_panel"] = _write_output(manager_panel.drop_duplicates(["match_id", "team"]), processed_dir, "manager_panel")
    outputs["analysis_panel"] = _write_output(analysis_panel, processed_dir, "analysis_panel")
    return outputs


def describe_data_tables(processed_dir: Path) -> pd.DataFrame:
    rows = []
    for stem in ("matches_clean", "manager_clean", "manager_chars_clean", "team_seasons_clean", "analysis_panel"):
        try:
            frame = _read_table_from_dir(processed_dir, stem)
        except FileNotFoundError:
            continue
        rows.append(
            {
                "table_name": stem,
                "rows": int(len(frame)),
                "columns": int(len(frame.columns)),
                "missing_cells": int(frame.isna().sum().sum()),
            }
        )
    if not rows:
        raise ValueError(f"No processed tables found in {processed_dir}")
    return pd.DataFrame(rows)


def _season_key(season: str | None) -> str | None:
    if season is None or pd.isna(season):
        return None
    match = re.search(r"\d{4}", str(season))
    return match.group(0) if match else str(season)


def _add_match_id(frame: pd.DataFrame) -> pd.DataFrame:
    ordered = frame.sort_values(["season", "match_date", "home_team", "away_team"]).reset_index(drop=True)
    week = ordered.groupby("season")["match_date"].rank(method="dense").astype("Int64")
    game_number = ordered.groupby(["season", "match_date"]).cumcount().add(1)
    ordered["match_id"] = [
        f"{_season_key(season)}_{week_no}_{game_no}"
        for season, week_no, game_no in zip(ordered["season"], week, game_number)
    ]
    return ordered


def fetch_matches_csv(url: str) -> pd.DataFrame:
    """Download a football-data CSV and return a cleaned match-level DataFrame."""
    csv_text = _request_text(url)
    raw = _clean_columns(pd.read_csv(io.StringIO(csv_text)))
    frame = pd.DataFrame(
        {
            "season": raw.get("season"),
            "match_date": _parse_date(raw.get("date", pd.Series(dtype="object"))),
            "home_team": raw.get("hometeam"),
            "away_team": raw.get("awayteam"),
            "home_goals": pd.to_numeric(raw.get("fthg"), errors="coerce"),
            "away_goals": pd.to_numeric(raw.get("ftag"), errors="coerce"),
            "league": "Super Lig",
        }
    )
    frame["season"] = frame["season"].fillna(frame["match_date"].map(_season_from_date))
    frame = frame.dropna(subset=["match_date", "home_team", "away_team"], how="any")
    frame = _add_match_id(frame)
    frame = _ensure_schema(frame, MATCHES_SCHEMA)
    LOGGER.info("Fetched URL=%s rows=%s", url, len(frame))
    if frame.empty:
        raise ValueError(f"No match rows found at {url}")
    return frame


def scrape_manager_spells(url: str) -> pd.DataFrame:
    """Scrape Transfermarkt manager spell history into a cleaned DataFrame."""
    html = _request_text(url)
    if _looks_like_bot_challenge(html):
        raise ValueError(f"Transfermarkt bot challenge detected at {url}")
    soup = BeautifulSoup(html, "html.parser")
    table = _find_candidate_table(soup, ("manager", "trainer", "appointed", "from", "name", "date of birth"))
    header_map = _header_index_map(table)
    rows = []
    for row in _table_data_rows(table):
        cells = row.select("td")
        texts = [cell.get_text(" ", strip=True) for cell in cells]
        anchor = row.select_one('a[href*="/profil/trainer/"], a[href*="/trainer/"]')
        manager_name = anchor.get_text(" ", strip=True) if anchor else _cell_text(
            cells,
            header_map.get("manager", header_map.get("trainer", header_map.get("name", header_map.get("name_date_of_birth")))),
        )
        if not manager_name:
            continue
        start_text = _cell_text(cells, header_map.get("from", header_map.get("appointed", header_map.get("date"))))
        end_text = _cell_text(cells, header_map.get("until", header_map.get("to", header_map.get("end_of_time_in_post"))))
        if not start_text:
            dates = _find_first_date_strings(texts)
            start_text = dates[0] if dates else ""
            end_text = dates[1] if len(dates) > 1 else end_text
        rows.append(
            {
                "manager_name": manager_name,
                "start_date": start_text,
                "end_date": end_text,
                "departure_reason": pd.NA,
                "is_caretaker": bool(re.search(r"caretaker|interim", manager_name, re.I)),
            }
        )
    raw = pd.DataFrame(rows)
    team_name = _extract_name(soup)
    frame = pd.DataFrame(
        {
            "spell_id": range(1, len(raw) + 1),
            "team": team_name,
            "manager_name": raw.get("manager_name", pd.Series(dtype="object")),
            "start_date": _parse_date(raw.get("start_date", pd.Series(dtype="object"))),
            "end_date": _parse_date(raw.get("end_date", pd.Series(dtype="object"))),
            "departure_reason": raw.get("departure_reason", pd.Series(dtype="object")),
            "is_caretaker": raw.get("is_caretaker", pd.Series(dtype="bool")),
        }
    )
    frame = _ensure_schema(frame.dropna(subset=["manager_name", "start_date"], how="any"), MANAGER_SPELLS_SCHEMA)
    LOGGER.info("Scraped URL=%s rows=%s", url, len(frame))
    if frame.empty:
        raise ValueError(f"No manager spell rows found at {url}; page_title={_extract_name(soup)!r}")
    return frame


def scrape_manager_chars(url: str) -> pd.DataFrame:
    """Scrape Transfermarkt manager biography fields into a cleaned DataFrame."""
    html = _request_text(url)
    if _looks_like_bot_challenge(html):
        raise ValueError(f"Transfermarkt bot challenge detected at {url}")
    soup = BeautifulSoup(html, "html.parser")
    labels = {node.get_text(" ", strip=True).lower(): node for node in soup.select("li.data-header__label, span.data-header__label, th")}
    nationality = _extract_text_after_label(labels, ("citizenship", "nationality", "citizen"))
    birth_date = _extract_text_after_label(labels, ("date of birth", "born"))
    manager_name = _extract_name(soup)
    frame = pd.DataFrame(
        [
            {
                "manager_name": manager_name,
                "nationality": nationality,
                "is_foreign": nationality != "Turkey" if nationality else pd.NA,
                "birth_date": _parse_date(pd.Series([birth_date])).iloc[0],
                "played_professionally": pd.NA,
                "prior_clubs_count": pd.NA,
                "career_win_rate": pd.NA,
            }
        ]
    )
    frame = _ensure_schema(frame, MANAGER_CHARS_SCHEMA)
    LOGGER.info("Scraped URL=%s rows=%s", url, len(frame))
    if frame.empty or frame["manager_name"].isna().all():
        raise ValueError(f"No manager characteristics found at {url}")
    return frame


def scrape_team_seasons(url: str) -> pd.DataFrame:
    """Scrape Transfermarkt team season summary data into a cleaned DataFrame."""
    html = _request_text(url)
    if _looks_like_bot_challenge(html):
        raise ValueError(f"Transfermarkt bot challenge detected at {url}")
    soup = BeautifulSoup(html, "html.parser")
    table = _find_candidate_table(soup, ("season", "squad", "market value", "avg age"))
    raw = _table_to_frame(table)
    frame = pd.DataFrame(
        {
            "team": _extract_name(soup),
            "season": raw.get("season"),
            "prev_season_position": pd.NA,
            "squad_market_value_eur": _extract_market_value_eur(_series(raw, "total_market_value", "market_value")),
        }
    )
    frame = _ensure_schema(frame.dropna(subset=["season"], how="any"), TEAM_SEASONS_SCHEMA)
    LOGGER.info("Scraped URL=%s rows=%s", url, len(frame))
    if frame.empty:
        raise ValueError(f"No team season rows found at {url}")
    return frame


def _extract_text_after_label(labels: dict[str, object], options: tuple[str, ...]) -> str | None:
    for key, node in labels.items():
        if any(option in key for option in options):
            parent = node.parent
            text = parent.get_text(" ", strip=True).replace(node.get_text(" ", strip=True), "", 1).strip(": ").strip()
            return text or None
    return None


def _extract_name(soup: BeautifulSoup) -> str | None:
    node = soup.select_one("h1") or soup.select_one("title")
    return node.get_text(" ", strip=True).split(" - ")[0] if node else None


def _looks_like_bot_challenge(html: str) -> bool:
    lowered = html.lower()
    markers = (
        "verify you are human",
        "attention required",
        "enable javascript",
        "cloudflare",
        "captcha",
        "press & hold",
    )
    return any(marker in lowered for marker in markers)


def _extract_first_number(value: str | None) -> float | None:
    match = re.search(r"\d+(?:[.,]\d+)?", value or "")
    return float(match.group(0).replace(",", ".")) if match else None


def _season_from_date(value: str | None) -> str | None:
    if not value or pd.isna(value):
        return None
    date = pd.Timestamp(value)
    return f"{date.year}/{str(date.year + 1)[-2:]}" if date.month >= 7 else f"{date.year - 1}/{str(date.year)[-2:]}"


def main() -> None:
    """Run the raw-data or processed-data pipeline."""
    parser = argparse.ArgumentParser(description="Run Turkey capstone data pipeline.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    raw_parser = subparsers.add_parser("fetch-raw", help="Download/scrape raw source tables.")
    raw_parser.add_argument("--config", default="config/turkey_sources.json")
    raw_parser.add_argument("--raw-dir", default="data/raw")

    processed_parser = subparsers.add_parser("build-processed", help="Build cleaned and analysis-ready tables.")
    processed_parser.add_argument("--raw-dir", default="data/raw")
    processed_parser.add_argument("--processed-dir", default="data/processed")
    processed_parser.add_argument("--team-names", default="data/team_names.csv")

    describe_parser = subparsers.add_parser("describe", help="Write a quick table summary for processed data.")
    describe_parser.add_argument("--processed-dir", default="data/processed")
    describe_parser.add_argument("--out-dir", default="out")

    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if args.command == "fetch-raw":
        run_raw_pipeline(Path(args.config), Path(args.raw_dir))
        return
    if args.command == "build-processed":
        build_processed_datasets(Path(args.raw_dir), Path(args.processed_dir), Path(args.team_names))
        return
    summary = describe_data_tables(Path(args.processed_dir))
    path = _write_output(summary, Path(args.out_dir), "table_summary")
    LOGGER.info("Saved table summary path=%s", path)


if __name__ == "__main__":
    main()
