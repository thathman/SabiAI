from pathlib import Path

from sabiai.openclaw.sports_insight_tools import SportsInsightTools
from sabiai.openclaw.sports_tools import SportsTools
from sabiai.sources import EspnPublicAdapter, SourceBundle, SourceRegistry, TheSportsDBAdapter
from sabiai.sports import ResearchPlanner, default_sports
from sabiai.storage import SabiDatabase


class FakeApp:
    def __init__(self, db_path: Path, source_bundle: SourceBundle):
        self._database = SabiDatabase(db_path)
        self._database.initialize()
        self.source_bundle = source_bundle
        self.sports = default_sports()
        self.research_planner = ResearchPlanner(self.sports)

    def _db(self, *, initialize: bool = False):
        if initialize:
            self._database.initialize()
        return self._database


def _espn_event(event_id, date, arsenal_score, opponent_score, opponent, *, home=True):
    arsenal = {
        "homeAway": "home" if home else "away",
        "score": str(arsenal_score),
        "winner": arsenal_score > opponent_score,
        "team": {"id": "ESPN-ARS", "displayName": "Arsenal"},
    }
    other = {
        "homeAway": "away" if home else "home",
        "score": str(opponent_score),
        "winner": opponent_score > arsenal_score,
        "team": {"id": f"OPP-{opponent}", "displayName": opponent},
    }
    return {
        "id": event_id,
        "date": date,
        "status": {"type": {"completed": True}},
        "competitions": [{"competitors": [arsenal, other]}],
    }


def _bundle(calls):
    def sportsdb_get(url, *, params=None, headers=None):
        calls.append(("TheSportsDB", url, params))
        if url.endswith("searchteams.php"):
            query = (params or {}).get("t")
            source_id = "TSD-ARS" if query == "Arsenal" else "TSD-CHE"
            return {"teams": [{"idTeam": source_id, "strTeam": query}]}
        if url.endswith("eventslast.php"):
            team_id = (params or {}).get("id")
            if team_id == "TSD-ARS":
                return {
                    "results": [
                        {
                            "idEvent": "old-1",
                            "dateEvent": "2026-08-05",
                            "strHomeTeam": "Arsenal",
                            "strAwayTeam": "Leeds",
                            "intHomeScore": "2",
                            "intAwayScore": "0",
                        }
                    ]
                }
            return {
                "results": [
                    {
                        "idEvent": "old-che",
                        "dateEvent": "2026-08-04",
                        "strHomeTeam": "Chelsea",
                        "strAwayTeam": "Everton",
                        "intHomeScore": "1",
                        "intAwayScore": "0",
                    }
                ]
            }
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
                                    {"team": {"id": "ESPN-ARS", "displayName": "Arsenal"}},
                                    {"team": {"id": "ESPN-CHE", "displayName": "Chelsea"}},
                                ]
                            }
                        ]
                    }
                ]
            }
        if url.endswith("/teams/ESPN-ARS/schedule"):
            return {
                "events": [
                    _espn_event("e1", "2026-08-20T18:00Z", 2, 1, "Chelsea", home=True),
                    _espn_event("e2", "2026-08-10T18:00Z", 1, 1, "Liverpool", home=False),
                    _espn_event("e3", "2026-08-01T18:00Z", 0, 2, "Chelsea", home=False),
                ]
            }
        if url.endswith("/teams/ESPN-CHE/schedule"):
            return {
                "events": [
                    {
                        "id": "c1",
                        "date": "2026-08-19T18:00Z",
                        "status": {"type": {"completed": True}},
                        "competitions": [
                            {
                                "competitors": [
                                    {
                                        "homeAway": "home",
                                        "score": "1",
                                        "winner": True,
                                        "team": {"id": "ESPN-CHE", "displayName": "Chelsea"},
                                    },
                                    {
                                        "homeAway": "away",
                                        "score": "0",
                                        "winner": False,
                                        "team": {"id": "OPP-EVE", "displayName": "Everton"},
                                    },
                                ]
                            }
                        ],
                    }
                ]
            }
        if url.endswith("/teams/ESPN-ARS/injuries"):
            return {
                "injuries": [
                    {
                        "athlete": {"displayName": "Player A"},
                        "status": "Out",
                        "description": "Ankle",
                    }
                ]
            }
        if url.endswith("/teams/ESPN-CHE/injuries"):
            return {"injuries": []}
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


def test_plain_form_summary_and_recent_h2h_are_human_readable(tmp_path: Path):
    app = FakeApp(tmp_path / "v2.db", _bundle([]))
    tools = SportsInsightTools(app)

    form = tools.form_summary(
        {"team": "Arsenal", "sport": "football", "league": "eng.1", "limit": 3}
    )
    assert form["summary"]["form"] == "W-D-W"
    assert form["summary"]["wins"] == 2
    assert form["summary"]["draws"] == 1
    assert form["summary"]["losses"] == 0

    h2h = tools.h2h(
        {"home": "Arsenal", "away": "Chelsea", "sport": "football", "league": "eng.1", "limit": 10}
    )
    assert h2h["meetings"] == 2
    assert h2h["home_team_wins"] == 1
    assert h2h["away_team_wins"] == 1
    assert h2h["complete_history"] is False


def test_injury_summary_returns_names_and_statuses(tmp_path: Path):
    app = FakeApp(tmp_path / "v2.db", _bundle([]))
    result = SportsInsightTools(app).injury_summary(
        {"team": "Arsenal", "sport": "football", "league": "eng.1"}
    )

    assert result["listed"] == 1
    assert result["players"][0]["player"] == "Player A"
    assert result["players"][0]["status"] == "Out"
    assert result["players"][0]["detail"] == "Ankle"
    assert result["needs_official_confirmation"] is True


def test_match_snapshot_composes_form_h2h_injuries_and_market_checks(tmp_path: Path):
    app = FakeApp(tmp_path / "v2.db", _bundle([]))
    result = SportsInsightTools(app).match_snapshot(
        {
            "home": "Arsenal",
            "away": "Chelsea",
            "sport": "football",
            "league": "eng.1",
            "market": "Over 2.5 goals",
            "limit": 10,
        }
    )

    assert result["home_team"] == "Arsenal"
    assert result["away_team"] == "Chelsea"
    assert result["sections"]["form"] is not None
    assert result["sections"]["h2h"]["meetings"] == 2
    assert result["sections"]["home_injuries"]["listed"] == 1
    assert result["sections"]["away_injuries"]["listed"] == 0
    assert result["market_specific_checks"]
    assert "Arsenal vs Chelsea" in result["plain"]
