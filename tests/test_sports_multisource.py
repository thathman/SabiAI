from pathlib import Path

from sabiai.openclaw.sports_tools import SportsTools
from sabiai.sources import EspnPublicAdapter, SourceBundle, SourceRegistry, TheSportsDBAdapter
from sabiai.storage import SabiDatabase


class FakeApp:
    def __init__(self, db_path: Path, source_bundle: SourceBundle):
        self._database = SabiDatabase(db_path)
        self._database.initialize()
        self.source_bundle = source_bundle

    def _db(self, *, initialize: bool = False):
        if initialize:
            self._database.initialize()
        return self._database


def _bundle(calls):
    def sportsdb_get(url, *, params=None, headers=None):
        calls.append(("TheSportsDB", url, params))
        if url.endswith("searchteams.php"):
            return {"teams": [{"idTeam": "TSD-ARS", "strTeam": "Arsenal"}]}
        if url.endswith("eventslast.php"):
            assert params == {"id": "TSD-ARS"}
            return {"results": [{"idEvent": "old-1", "strEvent": "Arsenal vs Leeds"}]}
        raise AssertionError(f"Unexpected TheSportsDB URL: {url}")

    def espn_get(url, *, params=None, headers=None):
        calls.append(("ESPN Public Data", url, params))
        if url.endswith("/teams"):
            return {
                "sports": [
                    {
                        "leagues": [
                            {
                                "teams": [
                                    {"team": {"id": "ESPN-ARS", "displayName": "Arsenal"}}
                                ]
                            }
                        ]
                    }
                ]
            }
        if url.endswith("/teams/ESPN-ARS/schedule"):
            return {
                "events": [
                    {
                        "id": "e1",
                        "date": "2026-08-20T18:00Z",
                        "status": {"type": {"completed": True}},
                    },
                    {
                        "id": "e2",
                        "date": "2026-08-10T18:00Z",
                        "status": {"type": {"completed": True}},
                    },
                ]
            }
        if url.endswith("/teams/ESPN-ARS/injuries"):
            return {"injuries": [{"athlete": {"displayName": "Player A"}, "status": "Out"}]}
        raise AssertionError(f"Unexpected ESPN URL: {url}")

    sportsdb = TheSportsDBAdapter(http_get=sportsdb_get)
    espn = EspnPublicAdapter(http_get=espn_get)
    registry = SourceRegistry()
    registry.register(sportsdb.source)
    registry.register(espn.source)
    return SourceBundle(
        registry=registry,
        fetchers={sportsdb.name: sportsdb.fetch, espn.name: espn.fetch},
    )


def test_team_form_resolves_each_provider_id_independently(tmp_path: Path):
    calls = []
    tools = SportsTools(FakeApp(tmp_path / "v2.db", _bundle(calls)))

    result = tools.team_form(
        {"team": "Arsenal", "sport": "football", "league": "eng.1", "limit": 10}
    )

    assert result["complete"] is True
    by_source = {item["source"]: item for item in result["sources"]}
    assert by_source["TheSportsDB"]["team_id"] == "TSD-ARS"
    assert by_source["TheSportsDB"]["partial"] is True
    assert by_source["ESPN Public Data"]["team_id"] == "ESPN-ARS"
    assert by_source["ESPN Public Data"]["partial"] is False

    espn_schedule_calls = [call for call in calls if call[0] == "ESPN Public Data" and "/schedule" in call[1]]
    assert espn_schedule_calls
    assert "/teams/ESPN-ARS/schedule" in espn_schedule_calls[0][1]
    assert "TSD-ARS" not in espn_schedule_calls[0][1]


def test_raw_team_id_requires_explicit_source(tmp_path: Path):
    tools = SportsTools(FakeApp(tmp_path / "v2.db", _bundle([])))

    try:
        tools.team_form({"team_id": "TSD-ARS", "sport": "football", "league": "eng.1"})
    except ValueError as exc:
        assert "provider-specific" in str(exc)
    else:
        raise AssertionError("Provider-specific team ids must not be accepted without a source.")


def test_team_injuries_resolves_espn_id_by_team_name(tmp_path: Path):
    calls = []
    tools = SportsTools(FakeApp(tmp_path / "v2.db", _bundle(calls)))

    result = tools.team_injuries(
        {"team": "Arsenal", "sport": "football", "league": "eng.1"}
    )

    assert result["complete"] is False
    assert result["needs_official_confirmation"] is True
    assert result["sources"][0]["source"] == "ESPN Public Data"
    assert result["sources"][0]["team_id"] == "ESPN-ARS"
    injury_calls = [call for call in calls if call[0] == "ESPN Public Data" and "/injuries" in call[1]]
    assert injury_calls and "/teams/ESPN-ARS/injuries" in injury_calls[0][1]
