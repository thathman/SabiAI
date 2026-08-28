from pathlib import Path

from sabiai.config import Settings
from sabiai.research import CrossSportDecisionPass, ShardedDailyResearch, build_slices
from sabiai.storage import ResearchSliceStore, SabiDatabase
from sabiai.system import research_heartbeat


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        repo_root=tmp_path,
        data_dir=tmp_path / "data",
        legacy_bets_db=tmp_path / "legacy.db",
        v2_db=tmp_path / "data" / "v2.db",
        timezone="Africa/Lagos",
        paid_sources_enabled=False,
        research_api_key="test-key",
        research_sports=("football", "basketball"),
        research_slice_workers=2,
    )


def _event(sport: str, event: str, country: str, competition: str, division: str):
    return {"sport": sport, "event": event, "country": country, "competition": competition, "division": division,
            "starts_at": "2026-08-28T12:00:00+00:00", "event_id": event, "source": "source",
            "odds": [{"label": "home", "decimal_odds": 2.0}]}


def test_build_slices_preserves_country_competition_and_division():
    rows = [_event("football", "A vs B", "England", "Premier League", "1"),
            _event("football", "C vs D", "England", "Championship", "2"),
            _event("basketball", "E vs F", "USA", "NBA", "1")]
    slices = build_slices("2026-08-28", rows)
    assert [(item.sport, item.country, item.competition, item.division) for item in slices] == [
        ("basketball", "USA", "NBA", "1"), ("football", "England", "Championship", "2"),
        ("football", "England", "Premier League", "1")]


def test_decision_pass_round_robins_qualifying_sports():
    rows = []
    for sport in ("football", "basketball"):
        for index in range(4):
            rows.append({"sport": sport, "event": f"{sport}-{index}", "market": "winner", "pick": "home",
                         "decimal_odds": 2.0, "confidence_pct": 70, "estimated_probability_pct": 65,
                         "country": "Country", "competition": "League", "division": "1"})
    result = CrossSportDecisionPass(max_recommendations=4, max_per_sport=3).select(rows)
    assert [row["sport"] for row in result["recommendations"]].count("football") == 2
    assert [row["sport"] for row in result["recommendations"].copy()].count("basketball") == 2
    assert result["recommendations"][0]["value_edge_pct"] == 15.0


def test_slice_cache_round_trip_and_event_lookup(tmp_path):
    db = SabiDatabase(_settings(tmp_path).v2_db)
    db.initialize()
    store = ResearchSliceStore(db)
    event = _event("football", "A vs B", "England", "Premier League", "1")
    scope = {"sport": "football", "country": "England", "competition": "Premier League", "division": "1"}
    key = store.cache_key("2026-08-28", scope, [event])
    store.put_cached(cache_key=key, scan_date="2026-08-28", scope=scope, events=[event], recommendations=[{"event": event["event"], "decimal_odds": 2.0}], model="test", usage={"total_tokens": 4})
    assert store.get_cached(key)["recommendations"][0]["event"] == "A vs B"
    assert store.find_event("A vs B", scan_date="2026-08-28")["cache_hit"] is True


def test_sharded_research_reuses_cache_without_second_model_call(monkeypatch, tmp_path):
    settings = _settings(tmp_path)
    db = SabiDatabase(settings.v2_db)
    db.initialize()
    calls = []

    def fake_model(_settings, *, day, events, scope=None, max_tokens=2200):
        calls.append((day, scope, max_tokens))
        return ({"recommendations": [{"sport": events[0]["sport"], "event": events[0]["event"], "market": "winner", "pick": "home", "decimal_odds": 2.0, "confidence_pct": 70}], "notes": []}, "test-model", {"total_tokens": 3})

    monkeypatch.setattr(research_heartbeat, "call_research_model", fake_model)
    events = [_event("football", "A vs B", "England", "Premier League", "1")]
    first = ShardedDailyResearch(settings, db).run(day="2026-08-28", events=events)
    second = ShardedDailyResearch(settings, db).run(day="2026-08-28", events=events)
    assert first["recommendations"] and second["recommendations"]
    assert len(calls) == 1
    assert second["coverage"]["cache_hits"] == 1
