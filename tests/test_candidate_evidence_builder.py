from pathlib import Path
from types import SimpleNamespace

from sabiai.research.context import CandidateEvidenceBuilder
from sabiai.sources import Source, SourceBundle, SourceCost, SourceKind, SourceRegistry
from sabiai.storage import SabiDatabase


def _bundle():
    registry = SourceRegistry()
    source = Source(
        name="TheSportsDB",
        kind=SourceKind.OPEN_DATA,
        cost=SourceCost.FREE,
        sports={"football"},
        capabilities={"team_search", "form", "schedule", "injuries"},
    )
    registry.register(source)

    def fetch(request):
        team = str(request.metadata.get("team") or "")
        team_id = str(request.metadata.get("team_id") or "")
        if request.capability == "team_search":
            resolved = "ARS" if team.casefold() == "arsenal" else "CHE"
            return {"summary": f"found {team}", "raw": {"teams": [{"idTeam": resolved, "strTeam": team}]}}
        if request.capability == "form":
            if team_id == "ARS":
                events = [
                    {"idEvent": "a1", "dateEvent": "2026-08-27", "strHomeTeam": "Arsenal", "strAwayTeam": "Leeds", "intHomeScore": "2", "intAwayScore": "0"},
                    {"idEvent": "a2", "dateEvent": "2026-08-20", "strHomeTeam": "Liverpool", "strAwayTeam": "Arsenal", "intHomeScore": "1", "intAwayScore": "1"},
                ]
            else:
                events = [
                    {"idEvent": "c1", "dateEvent": "2026-08-26", "strHomeTeam": "Chelsea", "strAwayTeam": "Everton", "intHomeScore": "3", "intAwayScore": "1"},
                    {"idEvent": "c2", "dateEvent": "2026-08-18", "strHomeTeam": "Man City", "strAwayTeam": "Chelsea", "intHomeScore": "2", "intAwayScore": "1"},
                ]
            return {"summary": "recent form", "raw": {"events": events, "partial": False}}
        if request.capability == "schedule":
            return {"summary": "schedule", "raw": {"events": [{"idEvent": f"next-{team_id}", "dateEvent": "2026-09-02"}], "partial": False}}
        if request.capability == "injuries":
            return {"summary": "availability checked", "raw": {"injuries": [], "partial": True}}
        raise AssertionError(request.capability)

    return SourceBundle(registry=registry, fetchers={"TheSportsDB": fetch})


def _settings(tmp_path: Path):
    return SimpleNamespace(v2_db=tmp_path / "v2.db", timezone="Africa/Lagos")


def test_team_event_can_become_evidence_ready_from_free_structured_sources(tmp_path: Path):
    database = SabiDatabase(tmp_path / "v2.db")
    database.initialize()
    event = {
        "sport": "football",
        "event": "Arsenal vs Chelsea",
        "home": "Arsenal",
        "away": "Chelsea",
        "competition": "Premier League",
    }
    result = CandidateEvidenceBuilder(_settings(tmp_path), database, bundle=_bundle()).build(event)
    assert result["ready_for_decision"] is True
    assert result["quality"] in {"fair", "strong"}
    assert result["sections"]["form"]["home"]["played"] == 2
    assert result["sections"]["form"]["away"]["played"] == 2
    assert result["sections"]["availability"]["checked"] is True
    assert result["sources"] == ["TheSportsDB"]


def test_field_or_race_event_stays_weak_without_sport_specific_deep_evidence(tmp_path: Path):
    database = SabiDatabase(tmp_path / "v2.db")
    database.initialize()
    event = {"sport": "horse_racing", "event": "Example Stakes", "competition": "Example Track"}
    result = CandidateEvidenceBuilder(_settings(tmp_path), database, bundle=_bundle()).build(event)
    assert result["ready_for_decision"] is False
    assert result["quality"] == "weak"
    assert result["fallback_tasks"]
    assert any("recent form" in item.casefold() for item in result["missing_topics"])


def test_evidence_budget_marks_unenriched_events_as_watch_only(tmp_path: Path):
    database = SabiDatabase(tmp_path / "v2.db")
    database.initialize()
    events = [
        {"sport": "football", "event": "Arsenal vs Chelsea", "home": "Arsenal", "away": "Chelsea", "competition": "Premier League"},
        {"sport": "football", "event": "Team C vs Team D", "home": "Team C", "away": "Team D", "competition": "Premier League"},
    ]
    result = CandidateEvidenceBuilder(_settings(tmp_path), database, bundle=_bundle()).enrich_in_place(events, limit=1)
    assert result.enriched == 1
    assert events[0]["evidence_packet"]["ready_for_decision"] is True
    assert events[1]["evidence_packet"]["ready_for_decision"] is False
    assert "budget" in events[1]["evidence_packet"]["missing_topics"][0]
