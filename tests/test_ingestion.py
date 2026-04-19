from __future__ import annotations

import pandas as pd
import pytest

import ingestion


class FakeResponse:
    def __init__(self, text: str, status_code: int = 200):
        self.text = text
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise ingestion.requests.HTTPError(f"status={self.status_code}")


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def get(self, url: str, timeout: int = 30):
        response = self.responses[min(self.calls, len(self.responses) - 1)]
        self.calls += 1
        return response


MATCHES_CSV = """Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,FTR,HS,AS,HST,AST,B365H,B365D,B365A
TR1,11/08/2023,Galatasaray,Trabzonspor,2,0,H,15,7,6,2,1.80,3.60,4.50
"""

MANAGER_SPELLS_HTML = """
<html><body>
<table>
  <tr><th>Club</th><th>Manager</th><th>From</th><th>Until</th><th>Matches</th><th>PPM</th></tr>
  <tr>
    <td>Galatasaray</td>
    <td><a href="/manager/a">Okan Buruk</a></td>
    <td>01/07/2023</td>
    <td>30/06/2024</td>
    <td>40</td>
    <td>2,35</td>
  </tr>
  <tr>
    <td>Besiktas</td>
    <td><a href="/manager/b">Interim Coach</a></td>
    <td>01/10/2023</td>
    <td>15/10/2023</td>
    <td>3</td>
    <td>1,00</td>
  </tr>
</table>
</body></html>
"""

MANAGER_CHARS_HTML = """
<html><body>
<h1>Okan Buruk</h1>
<ul>
  <li><span class="data-header__label">Date of birth:</span> 19/10/1973</li>
  <li><span class="data-header__label">Age:</span> 50</li>
  <li><span class="data-header__label">Citizenship:</span> Turkey</li>
  <li><span class="data-header__label">Preferred formation:</span> 4-2-3-1</li>
</ul>
</body></html>
"""

TEAM_SEASONS_HTML = """
<html><body>
<h1>Galatasaray</h1>
<table>
  <tr>
    <th>Season</th><th>League</th><th>Squad size</th><th>Avg age</th>
    <th>Foreigners</th><th>Avg market value</th><th>Total market value</th>
  </tr>
  <tr>
    <td>2023/24</td><td>Super Lig</td><td>28</td><td>25,4</td>
    <td>14</td><td>€4.50m</td><td>€126.00m</td>
  </tr>
</table>
</body></html>
"""


def _mock_session(monkeypatch: pytest.MonkeyPatch, *responses: FakeResponse) -> FakeSession:
    session = FakeSession(responses)
    monkeypatch.setattr(ingestion, "_build_session", lambda: session)
    return session


def test_fetch_matches_csv_schema_and_parsing(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_session(monkeypatch, FakeResponse(MATCHES_CSV))
    df = ingestion.fetch_matches_csv("https://example.com/matches.csv")
    assert list(df.columns) == ingestion.MATCHES_SCHEMA
    assert len(df) == 1
    assert df.loc[0, "match_id"] == "2023_1_1"
    assert df.loc[0, "season"] == "2023/24"
    assert df.loc[0, "match_date"] == "2023-08-11"
    assert df.loc[0, "home_team"] == "Galatasaray"
    assert df.loc[0, "away_goals"] == 0
    assert df.loc[0, "league"] == "Super Lig"


def test_scrape_manager_spells_schema_and_parsing(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_session(monkeypatch, FakeResponse(MANAGER_SPELLS_HTML))
    df = ingestion.scrape_manager_spells("https://example.com/spells")
    assert list(df.columns) == ingestion.MANAGER_SPELLS_SCHEMA
    assert len(df) == 2
    assert df.loc[0, "manager_name"] == "Okan Buruk"
    assert df.loc[0, "start_date"] == "2023-07-01"
    assert pd.isna(df.loc[0, "departure_reason"])
    assert bool(df.loc[1, "is_caretaker"]) is True


def test_scrape_manager_spells_uses_page_title_and_name_date_of_birth_column(monkeypatch: pytest.MonkeyPatch) -> None:
    html = """
    <html><body>
    <h1>Galatasaray</h1>
    <table>
      <tr><th>Name/Date of birth</th><th>Appointed</th><th>End of time in post</th></tr>
      <tr>
        <td><a href="/okan-buruk/profil/trainer/2218">Okan Buruk</a></td>
        <td>01/07/2023</td>
        <td>30/06/2024</td>
      </tr>
    </table>
    </body></html>
    """
    _mock_session(monkeypatch, FakeResponse(html))
    df = ingestion.scrape_manager_spells("https://example.com/spells")
    assert df.loc[0, "team"] == "Galatasaray"
    assert df.loc[0, "manager_name"] == "Okan Buruk"
    assert df.loc[0, "start_date"] == "2023-07-01"
    assert df.loc[0, "end_date"] == "2024-06-30"


def test_scrape_manager_chars_schema_and_parsing(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_session(monkeypatch, FakeResponse(MANAGER_CHARS_HTML))
    df = ingestion.scrape_manager_chars("https://example.com/manager/a")
    assert list(df.columns) == ingestion.MANAGER_CHARS_SCHEMA
    assert len(df) == 1
    assert df.loc[0, "manager_name"] == "Okan Buruk"
    assert df.loc[0, "birth_date"] == "1973-10-19"
    assert df.loc[0, "nationality"] == "Turkey"
    assert bool(df.loc[0, "is_foreign"]) is False
    assert pd.isna(df.loc[0, "career_win_rate"])


def test_scrape_team_seasons_schema_and_parsing(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_session(monkeypatch, FakeResponse(TEAM_SEASONS_HTML))
    df = ingestion.scrape_team_seasons("https://example.com/team")
    assert list(df.columns) == ingestion.TEAM_SEASONS_SCHEMA
    assert len(df) == 1
    assert df.loc[0, "team"] == "Galatasaray"
    assert df.loc[0, "season"] == "2023/24"
    assert pd.isna(df.loc[0, "prev_season_position"])
    assert df.loc[0, "squad_market_value_eur"] == pytest.approx(126_000_000.0)


@pytest.mark.parametrize(
    ("func_name", "payload"),
    [
        ("fetch_matches_csv", "Div,Date,HomeTeam,AwayTeam\n"),
        ("scrape_manager_spells", "<html><body><table></table></body></html>"),
        ("scrape_manager_chars", "<html><body></body></html>"),
        ("scrape_team_seasons", "<html><body><table></table></body></html>"),
    ],
)
def test_empty_response_raises_value_error(monkeypatch: pytest.MonkeyPatch, func_name: str, payload: str) -> None:
    _mock_session(monkeypatch, FakeResponse(payload))
    func = getattr(ingestion, func_name)
    with pytest.raises(ValueError):
        func("https://example.com/empty")


def test_request_text_retries_retryable_status(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _mock_session(monkeypatch, FakeResponse("", 503), FakeResponse(MATCHES_CSV, 200))
    sleeps = []
    monkeypatch.setattr(ingestion.time, "sleep", lambda seconds: sleeps.append(seconds))
    text = ingestion._request_text("https://example.com/retry")
    assert "Galatasaray" in text
    assert session.calls == 2
    assert len(sleeps) == 1


def test_write_output_uses_parquet_over_threshold(tmp_path) -> None:
    df = pd.DataFrame({"a": range(50_001)})
    written = {}
    original = pd.DataFrame.to_parquet
    pd.DataFrame.to_parquet = lambda self, path, index=False: written.setdefault("path", path)
    try:
        path = ingestion._write_output(df, tmp_path, "big_table")
    finally:
        pd.DataFrame.to_parquet = original
    assert path.suffix == ".parquet"
    assert written["path"] == path


def test_collect_manager_profile_urls_returns_unique_manager_links(monkeypatch: pytest.MonkeyPatch) -> None:
    html = """
    <html><body>
    <table>
      <tr><th>Manager</th><th>From</th></tr>
      <tr><td><a href="/okan-buruk/profil/trainer/2218">Okan Buruk</a></td><td>01/07/2023</td></tr>
      <tr><td><a href="/okan-buruk/profil/trainer/2218">Okan Buruk</a></td><td>01/07/2022</td></tr>
      <tr><td><a href="/another-link/profil/spieler/1">Not a manager profile</a></td><td>01/07/2021</td></tr>
    </table>
    </body></html>
    """
    _mock_session(monkeypatch, FakeResponse(html))
    urls = ingestion.collect_manager_profile_urls("https://example.com/club/mitarbeiterhistorie/verein/1")
    assert urls == ["https://example.com/okan-buruk/profil/trainer/2218"]


def test_scrape_manager_spells_raises_clear_error_for_bot_challenge(monkeypatch: pytest.MonkeyPatch) -> None:
    html = "<html><title>Attention Required!</title><body>Verify you are human</body></html>"
    _mock_session(monkeypatch, FakeResponse(html))
    with pytest.raises(ValueError, match="bot challenge"):
        ingestion.scrape_manager_spells("https://example.com/spells")
