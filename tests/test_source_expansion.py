import json
from pathlib import Path

from sabiai.config import Settings
from sabiai.sources import (
    ApiSportsAdapter,
    CricsheetAdapter,
    FastF1Adapter,
    JolpicaF1Adapter,
    NbaLiveDataAdapter,
    OpenLigaDBAdapter,
    PandaScoreAdapter,
    SportMonksAdapter,
    SportsDataIOAdapter,
    SportsGameOddsAdapter,
    StatsBombOpenDataAdapter,
    SourceRequest,
    default_source_bundle,
)


def _request(capability, sport=None, metadata=None):
    return SourceRequest(
        request_key=f"expansion:{capability}:{sport or 'none'}",
        capability=capability,
        sport=sport,
        metadata=metadata or {},
    )


def test_api_sports_uses_header_and_normalizes_fixture():
    calls = []

    def fake_get(url, *, params=None, headers=None):
        calls.append((url, params, headers))
        return {"response": [{"fixture": {"id": 10, "date": "2026-08-29T15:00:00Z"}, "teams": {"home": {"name": "A"}, "away": {"name": "B"},}, "league": {"name": "Premier League"}}]}

    result = ApiSportsAdapter(api_key="api-test", http_get=fake_get).fetch(
        _request("fixtures", "football", {"date": "2026-08-29"})
    )

    assert calls[0][0] == "https://v3.football.api-sports.io/fixtures"
    assert calls[0][2] == {"x-apisports-key": "api-test"}
    assert result["raw"]["events"][0]["event_id"] == 10
    assert result["raw"]["events"][0]["home"] == "A"


def test_sportsgameodds_v2_preserves_odd_id_and_market_sensor_boundary():
    calls = []

    def fake_get(url, *, params=None, headers=None):
        calls.append((url, params, headers))
        return {"data": [{"eventID": "e1", "name": "A vs B", "status": {"startsAt": "2026-08-29T15:00:00Z"}, "odds": {"points-home-game-ml-home": {"byBookmaker": {"book": {"odds": "+150", "available": True}}}}}]}

    adapter = SportsGameOddsAdapter(api_key="sgo-test", http_get=fake_get)
    result = adapter.fetch(_request("fixtures", "basketball", {"leagueID": "NBA", "limit": 10}))

    assert calls[0][0] == "https://api.sportsgameodds.com/v2/events"
    assert calls[0][2] == {"x-api-key": "sgo-test"}
    assert result["market_sensor"] is True
    assert result["raw"]["events"][0]["odds"][0]["source_market_id"] == "points-home-game-ml-home"
    assert result["raw"]["events"][0]["odds"][0]["decimal_odds"] == 2.5


def test_pandascore_uses_bearer_and_maps_esports_match():
    calls = []

    def fake_get(url, *, params=None, headers=None):
        calls.append((url, params, headers))
        return [{"id": 99, "name": "Final", "begin_at": "2026-08-29T18:00:00Z", "opponents": [{"opponent": {"name": "Alpha"}}, {"opponent": {"name": "Beta"}}], "league": {"id": 4, "name": "League"}}]

    result = PandaScoreAdapter(token="ps-test", http_get=fake_get).fetch(_request("fixtures", "esports", {"game": "lol"}))

    assert calls[0][0] == "https://api.pandascore.co/lol/matches"
    assert calls[0][2] == {"Authorization": "Bearer ps-test"}
    assert result["raw"]["events"][0]["home"] == "Alpha"
    assert result["raw"]["events"][0]["provider_event_id"] == 99


def test_jolpica_parses_race_table():
    def fake_get(url, *, params=None, headers=None):
        assert url.endswith("/2026.json")
        return {"MRData": {"RaceTable": {"Races": [{"round": "1", "raceName": "Bahrain Grand Prix", "date": "2026-03-01"}]}}}

    result = JolpicaF1Adapter(http_get=fake_get).fetch(_request("schedule", "motorsport", {"season": "2026"}))

    assert result["raw"]["events"][0]["raceName"] == "Bahrain Grand Prix"


def test_fastf1_is_lazy_and_uses_local_cache():
    class Cache:
        paths = []

        @classmethod
        def enable_cache(cls, path):
            cls.paths.append(path)

    cache_cls = Cache

    class FakeFastF1:
        Cache = cache_cls

        @staticmethod
        def get_event_schedule(year):
            return [{"EventName": "Monaco Grand Prix", "EventDate": "2026-05-24"}]

    adapter = FastF1Adapter(cache_dir=Path("/tmp/sabi-fastf1-test"), fastf1_module=FakeFastF1)
    result = adapter.fetch(_request("schedule", "motorsport", {"year": 2026}))

    assert result["raw"]["events"][0]["EventName"] == "Monaco Grand Prix"
    assert Cache.paths


def test_cricsheet_reads_requested_local_match(tmp_path: Path):
    match = {"meta": {"data_version": "1.1.0"}, "info": {"dates": ["2026-01-01"]}, "innings": []}
    (tmp_path / "12345.json").write_text(json.dumps(match), encoding="utf-8")

    adapter = CricsheetAdapter(data_dir=tmp_path)
    result = adapter.fetch(_request("match_lookup", "cricket", {"match_id": "12345"}))

    assert adapter.source.enabled is True
    assert result["raw"]["events"][0]["meta"]["data_version"] == "1.1.0"


def test_sportsdataio_uses_subscription_header():
    calls = []

    def fake_get(url, *, params=None, headers=None):
        calls.append((url, params, headers))
        return [{"GameID": 1, "HomeTeam": "A", "AwayTeam": "B", "DateTime": "2026-08-29T15:00:00Z"}]

    SportsDataIOAdapter(api_key="sdio-test", http_get=fake_get).fetch(_request("fixtures", "basketball", {"date": "2026-08-29"}))
    assert calls[0][0] == "https://api.sportsdata.io/v3/basketball/scores/json/GamesByDate/2026-08-29"
    assert calls[0][2] == {"Ocp-Apim-Subscription-Key": "sdio-test"}


def test_sportmonks_motorsport_uses_v3_and_header():
    calls = []

    def fake_get(url, *, params=None, headers=None):
        calls.append((url, params, headers))
        return {"data": [{"id": 2, "name": "Race", "starting_at": "2026-03-01T12:00:00Z", "participants": [{"name": "A"}, {"name": "B"}]}]}

    result = SportMonksAdapter(token="sm-test", http_get=fake_get).fetch(_request("fixtures", "motorsport"))
    assert calls[0][0] == "https://api.sportmonks.com/v3/motorsport/fixtures"
    assert calls[0][2] == {"Authorization": "sm-test"}
    assert result["api_family"] == "motorsport"


def test_statsbomb_reads_local_historical_json(tmp_path: Path):
    path = tmp_path / "matches"
    path.mkdir()
    (path / "10.json").write_text(json.dumps([{"match_id": 10, "home_team": {"name": "A"}}]), encoding="utf-8")
    result = StatsBombOpenDataAdapter(data_dir=tmp_path).fetch(_request("matches", "football", {"match_id": "10"}))
    assert result["raw"]["events"][0]["match_id"] == 10


def test_openligadb_normalizes_match_and_uses_documented_route():
    calls = []

    def fake_get(url, *, params=None, headers=None):
        calls.append(url)
        return [{"matchID": 4, "matchDateTimeUTC": "2026-08-29T15:00:00Z", "team1": {"teamName": "A"}, "team2": {"teamName": "B"}, "leagueName": "BL1"}]

    result = OpenLigaDBAdapter(http_get=fake_get).fetch(_request("fixtures", "football", {"league": "bl1", "season": 2026}))
    assert calls == ["https://api.openligadb.de/getmatchdata/bl1/2026"]
    assert result["raw"]["events"][0]["home"] == "A"


def test_nba_livedata_uses_public_scoreboard():
    calls = []

    def fake_get(url, *, params=None, headers=None):
        calls.append(url)
        return {"scoreboard": {"games": [{"gameId": "001", "gameTimeUTC": "2026-08-29T15:00:00Z", "homeTeam": {"teamName": "A"}, "awayTeam": {"teamName": "B"}, "gameStatus": 1}]}}

    result = NbaLiveDataAdapter(http_get=fake_get).fetch(_request("fixtures", "basketball"))
    assert calls == ["https://cdn.nba.com/static/json/liveData/scoreboard/todaysScoreboard_00.json"]
    assert result["raw"]["events"][0]["event_id"] == "001"


def test_catalog_exposes_optional_sources_as_not_configured(tmp_path: Path):
    settings = Settings(
        repo_root=tmp_path,
        data_dir=tmp_path / "data",
        legacy_bets_db=tmp_path / "data" / "bets.db",
        v2_db=tmp_path / "data" / "v2.db",
        timezone="Africa/Lagos",
        paid_sources_enabled=False,
    )
    bundle = default_source_bundle(settings)
    sources = {source.name: source for source in bundle.registry.all()}

    assert sources["API-Sports"].enabled is False
    assert sources["API-Sports"].health == "not_configured"
    assert sources["SportsGameOdds"].enabled is False
    assert sources["PandaScore"].enabled is False
    assert sources["Jolpica F1"].enabled is True
    assert sources["OpenLigaDB"].enabled is True
    assert sources["NBA LiveData"].enabled is True


def test_catalog_registers_keyed_expansion_adapters_without_exposing_keys(tmp_path: Path):
    settings = Settings(
        repo_root=tmp_path,
        data_dir=tmp_path / "data",
        legacy_bets_db=tmp_path / "data" / "bets.db",
        v2_db=tmp_path / "data" / "v2.db",
        timezone="Africa/Lagos",
        paid_sources_enabled=True,
        api_sports_key="api-secret",
        sportsgameodds_key="sgo-secret",
        pandascore_token="ps-secret",
        sportsdataio_key="sdio-secret",
        sportmonks_token="sm-secret",
    )
    bundle = default_source_bundle(settings)
    assert {"API-Sports", "SportsGameOdds", "PandaScore", "SportsDataIO", "SportMonks"} <= set(bundle.fetchers)
    for source in bundle.registry.all():
        assert "secret" not in (source.notes or "").casefold()
