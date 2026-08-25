from pathlib import Path

from sabiai.config import Settings
from sabiai.sources import (
    FootballDataAdapter,
    SourceRequest,
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
    assert "football-data.org" not in names
    assert "OpenClaw Browser" in names
    assert "OpenClaw Search" in names
    assert "TheSportsDB" in bundle.fetchers
