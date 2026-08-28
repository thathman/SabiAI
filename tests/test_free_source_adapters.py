from pathlib import Path

from sabiai.config import Settings
from sabiai.sources import (
    EspnPublicAdapter,
    FootballDataAdapter,
    ParseBotAdapter,
    SourceRequest,
    SportsBettingAnalyzerAdapter,
    TheSportsDBAdapter,
    default_source_bundle,
)


def test_thesportsdb_fixtures_uses_documented_free_endpoint_and_sport_mapping():
    calls = []

    def fake_get(url, *, params=None, headers=None):
        calls.append((url, params, headers))
        return {"events": [{"idEvent": "1", "strEvent": "Arsenal vs Chelsea"}]}

    adapter = TheSportsDBAdapter(http_get=fake_get)
    result = adapter.fetch(
        SourceRequest(
            request_key="fixture:test",
            capability="fixtures",
            sport="football",
            metadata={"date": "2026-08-25"},
        )
    )

    assert calls[0][0].endswith("/123/eventsday.php")
    assert calls[0][1] == {"d": "2026-08-25", "s": "Soccer"}
    assert result["raw"]["events"][0]["strEvent"] == "Arsenal vs Chelsea"
    assert "result limits" in result["raw"]["coverage_note"]


def test_thesportsdb_event_search_returns_plain_finding():
    def fake_get(url, *, params=None, headers=None):
        return {
            "event": [
                {
                    "strEvent": "Arsenal vs Chelsea",
                    "strLeague": "Premier League",
                    "dateEvent": "2026-08-25",
                }
            ]
        }

    result = TheSportsDBAdapter(http_get=fake_get).fetch(
        SourceRequest(
            request_key="event:test",
            capability="event_search",
            sport="football",
            metadata={"event": "Arsenal vs Chelsea"},
        )
    )
    assert result["subject"] == "Arsenal vs Chelsea"
    assert "Premier League" in result["summary"]


def test_thesportsdb_team_search_can_resolve_team_id_for_followup_queries():
    calls = []

    def fake_get(url, *, params=None, headers=None):
        calls.append((url, params))
        return {"teams": [{"idTeam": "133604", "strTeam": "Arsenal"}]}

    result = TheSportsDBAdapter(http_get=fake_get).fetch(
        SourceRequest(
            request_key="team:test",
            capability="team_search",
            sport="football",
            metadata={"team": "Arsenal"},
        )
    )
    assert calls[0][0].endswith("/123/searchteams.php")
    assert calls[0][1] == {"t": "Arsenal"}
    assert result["raw"]["teams"][0]["idTeam"] == "133604"


def test_thesportsdb_form_marks_free_previous_schedule_as_partial():
    def fake_get(url, *, params=None, headers=None):
        assert url.endswith("/123/eventslast.php")
        assert params == {"id": "133604"}
        return {"results": [{"strEvent": "Arsenal vs Leeds", "intHomeScore": "2", "intAwayScore": "0"}]}

    result = TheSportsDBAdapter(http_get=fake_get).fetch(
        SourceRequest(
            request_key="form:test",
            capability="form",
            sport="football",
            metadata={"team_id": "133604"},
        )
    )
    assert result["raw"]["partial"] is True
    assert "must not be treated as complete recent form" in result["summary"]


def test_thesportsdb_lineup_does_not_claim_complete_injury_coverage():
    def fake_get(url, *, params=None, headers=None):
        assert url.endswith("/123/lookuplineup.php")
        return {"lineup": [{"strPlayer": "Player A", "strPosition": "Forward"}]}

    result = TheSportsDBAdapter(http_get=fake_get).fetch(
        SourceRequest(
            request_key="lineup:test",
            capability="availability",
            sport="football",
            metadata={"event_id": "1032723"},
        )
    )
    assert result["raw"]["lineup"][0]["strPlayer"] == "Player A"
    assert "not a complete injury/availability feed" in result["summary"]


def test_espn_team_search_returns_provider_team_id():
    calls = []

    def fake_get(url, *, params=None, headers=None):
        calls.append((url, params))
        return {
            "sports": [
                {
                    "leagues": [
                        {
                            "teams": [
                                {"team": {"id": "359", "displayName": "Arsenal"}},
                                {"team": {"id": "363", "displayName": "Chelsea"}},
                            ]
                        }
                    ]
                }
            ]
        }

    result = EspnPublicAdapter(http_get=fake_get).fetch(
        SourceRequest(
            request_key="espn-team:test",
            capability="team_search",
            sport="football",
            metadata={"team": "Arsenal", "league": "eng.1"},
        )
    )
    assert calls[0][0].endswith("/soccer/eng.1/teams")
    assert result["raw"]["teams"][0]["id"] == "359"


def test_espn_form_returns_recent_completed_events_not_future_games():
    def fake_get(url, *, params=None, headers=None):
        assert url.endswith("/soccer/eng.1/teams/359/schedule")
        return {
            "events": [
                {
                    "id": "future",
                    "date": "2026-08-30T15:00Z",
                    "status": {"type": {"completed": False}},
                },
                {
                    "id": "recent",
                    "date": "2026-08-20T15:00Z",
                    "status": {"type": {"completed": True}},
                },
            ]
        }

    result = EspnPublicAdapter(http_get=fake_get).fetch(
        SourceRequest(
            request_key="espn-form:test",
            capability="form",
            sport="football",
            metadata={"team_id": "359", "league": "eng.1", "limit": 10},
        )
    )
    assert [event["id"] for event in result["raw"]["events"]] == ["recent"]
    assert result["raw"]["partial"] is False


def test_espn_injuries_keeps_coverage_warning():
    def fake_get(url, *, params=None, headers=None):
        assert url.endswith("/basketball/nba/teams/13/injuries")
        return {"injuries": [{"athlete": {"displayName": "Player A"}, "status": "Out"}]}

    result = EspnPublicAdapter(http_get=fake_get).fetch(
        SourceRequest(
            request_key="espn-injury:test",
            capability="injuries",
            sport="basketball",
            metadata={"team_id": "13"},
        )
    )
    assert len(result["raw"]["injuries"]) == 1
    assert "official team/league confirmation" in result["raw"]["coverage_note"]


def test_football_data_adapter_sends_token_and_is_lower_priority_than_unmetered_source():
    calls = []

    def fake_get(url, *, params=None, headers=None):
        calls.append((url, params, headers))
        return {"matches": [{"id": 10}]}

    adapter = FootballDataAdapter(token="free-token", http_get=fake_get)
    result = adapter.fetch(
        SourceRequest(
            request_key="fd:test",
            capability="fixtures",
            sport="football",
            metadata={"date": "2026-08-25"},
        )
    )
    assert calls[0][0].endswith("/v4/matches")
    assert calls[0][2]["X-Auth-Token"] == "free-token"
    assert result["raw"]["matches"][0]["id"] == 10
    assert adapter.source.priority > TheSportsDBAdapter(http_get=fake_get).source.priority


def test_default_source_bundle_requires_no_private_token(tmp_path: Path):
    settings = Settings(
        repo_root=tmp_path,
        data_dir=tmp_path / "data",
        legacy_bets_db=tmp_path / "data" / "bets.db",
        v2_db=tmp_path / "data" / "v2.db",
        timezone="Africa/Lagos",
        paid_sources_enabled=False,
        football_data_token=None,
        thesportsdb_key="123",
    )
    bundle = default_source_bundle(settings)
    names = [source.name for source in bundle.registry.all()]
    assert "TheSportsDB" in names
    assert "ESPN Public Data" in names
    assert "football-data.org" not in names
    assert "OpenClaw Browser" in names
    assert "OpenClaw Search" in names
    assert "TheSportsDB" in bundle.fetchers
    assert "ESPN Public Data" in bundle.fetchers


def test_parse_adapter_calls_only_an_allowlisted_endpoint():
    calls = []

    def fake_post(url, *, payload=None, headers=None):
        calls.append((url, payload, headers))
        return {"status": "success", "data": [{"event": "Arsenal vs Chelsea"}]}

    adapter = ParseBotAdapter(
        name="Parse · Flashscore",
        api_key="test-key",
        scraper_id="d11166c0-0278-4747-828f-936c42d8963a",
        endpoints={"fixtures": "get_daily_fixtures"},
        http_post=fake_post,
    )
    result = adapter.fetch(
        SourceRequest(
            request_key="parse:fixtures",
            capability="fixtures",
            sport="football",
            metadata={"date": "2026-08-27"},
        )
    )

    assert calls == [
        (
            "https://api.parse.bot/scraper/d11166c0-0278-4747-828f-936c42d8963a/get_daily_fixtures",
            {"date": "2026-08-27"},
            {"X-API-Key": "test-key"},
        )
    ]
    assert result["raw"]["data"][0]["event"] == "Arsenal vs Chelsea"


def test_parse_sportybet_catalog_never_exposes_booking_endpoint(tmp_path: Path):
    settings = Settings(
        repo_root=tmp_path,
        data_dir=tmp_path / "data",
        legacy_bets_db=tmp_path / "data" / "bets.db",
        v2_db=tmp_path / "data" / "v2.db",
        timezone="Africa/Lagos",
        paid_sources_enabled=False,
        parse_api_key="test-key",
        parse_sportybet_scraper_id="bcc1b144-d466-46b3-ad01-338d5b27086b",
    )

    bundle = default_source_bundle(settings)
    adapter = bundle.fetchers["Parse · SportyBet"].__self__
    assert "book_bet" not in adapter.allowed_endpoints


def test_all_configured_remote_sources_are_registered(tmp_path: Path):
    settings = Settings(
        repo_root=tmp_path,
        data_dir=tmp_path / "data",
        legacy_bets_db=tmp_path / "data" / "bets.db",
        v2_db=tmp_path / "data" / "v2.db",
        timezone="Africa/Lagos",
        paid_sources_enabled=False,
        parse_api_key="test-key",
        parse_flashscore_scraper_id="flashscore-id",
        parse_livescore_scraper_id="livescore-id",
        parse_sportybet_scraper_id="sportybet-id",
        parse_espn_scraper_id="espn-id",
        sports_betting_analyzer_api_key="analyzer-key",
    )

    bundle = default_source_bundle(settings)
    names = {source.name for source in bundle.registry.all()}

    assert {
        "Parse · Flashscore",
        "Parse · LiveScore",
        "Parse · SportyBet",
        "Parse · ESPN",
        "Sports Betting AI Analyzer",
    } <= names
    assert "Parse · 1xBet" not in names
    assert "Stake" not in names

    by_name = {source.name: source for source in bundle.registry.all()}
    assert "fixtures_with_odds" in by_name["Parse · Flashscore"].capabilities
    assert "fixtures_with_odds" in by_name["Parse · ESPN"].capabilities


def test_sports_betting_analyzer_uses_fixed_suggestion_endpoint():
    calls = []

    def fake_post(url, *, payload=None, headers=None):
        calls.append((url, payload, headers))
        return {"picks": [{"selection": "Example"}]}

    adapter = SportsBettingAnalyzerAdapter(api_key="test-key", http_post=fake_post)
    result = adapter.fetch(
        SourceRequest(
            request_key="analyzer:nba",
            capability="suggested_picks",
            sport="basketball",
            metadata={"provider_sport": "NBA"},
        )
    )

    assert calls == [
        (
            "https://sportsbettingaianalyzer.com/api/picks/suggested",
            {"sport": "NBA"},
            {"X-API-Key": "test-key"},
        )
    ]
    assert result["raw"]["data"]["picks"][0]["selection"] == "Example"
