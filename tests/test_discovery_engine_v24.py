from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from sabiai.config import Settings
from sabiai.research import CoverageDiscoveryEngine
from sabiai.sources import Source, SourceBundle, SourceCost, SourceKind, SourceRegistry
from sabiai.storage import CoverageStore, SabiDatabase


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        repo_root=tmp_path,
        data_dir=tmp_path / "data",
        legacy_bets_db=tmp_path / "legacy.db",
        v2_db=tmp_path / "data" / "v2.db",
        timezone="UTC",
        paid_sources_enabled=False,
        research_sports=("football",),
        discovery_horizon_hours=72,
        discovery_max_events=2000,
        discovery_max_source_requests=50,
        prefilter_max_events=300,
        research_max_events=120,
    )


def test_discovery_unions_sources_instead_of_stopping_after_first_success(tmp_path: Path):
    now = datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc)
    common = {
        "eventId": "a-common",
        "homeTeamName": "Arsenal",
        "awayTeamName": "Chelsea",
        "kickoffTime": (now + timedelta(hours=8)).isoformat(),
        "homeOdds": "1.90",
    }
    source_a_events = [
        common,
        {
            "eventId": "a-only",
            "homeTeamName": "Liverpool",
            "awayTeamName": "Everton",
            "kickoffTime": (now + timedelta(hours=30)).isoformat(),
            "homeOdds": "1.75",
        },
    ]
    source_b_events = [
        {**common, "eventId": "b-common"},
        {
            "eventId": "b-only",
            "homeTeamName": "Leeds",
            "awayTeamName": "Fulham",
            "kickoffTime": (now + timedelta(hours=50)).isoformat(),
            "homeOdds": "2.10",
        },
    ]

    registry = SourceRegistry()
    for name in ("Source A", "Source B"):
        registry.register(Source(
            name=name,
            kind=SourceKind.PUBLIC_ENDPOINT,
            cost=SourceCost.FREE,
            sports={"football"},
            capabilities={"fixtures"},
        ))

    def fetch_a(_request):
        return {"raw": {"events": source_a_events, "partial": False}}

    def fetch_b(_request):
        return {"raw": {"events": source_b_events, "partial": False}}

    bundle = SourceBundle(registry=registry, fetchers={"Source A": fetch_a, "Source B": fetch_b})
    settings = _settings(tmp_path)
    database = SabiDatabase(settings.v2_db)
    result = CoverageDiscoveryEngine(settings, database, bundle=bundle).refresh(now=now)

    assert result.canonical_events == 3
    assert result.priced_events == 3
    assert result.prefiltered_events == 3
    radar = CoverageStore(database).radar(now=now, horizon_hours=72)
    by_name = {row["event_name"]: row for row in radar}
    assert by_name["Arsenal vs Chelsea"]["source_count"] == 2
    assert "Liverpool vs Everton" in by_name
    assert "Leeds vs Fulham" in by_name


def test_discovery_horizon_sees_future_games_without_making_them_today_research(tmp_path: Path):
    now = datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc)
    registry = SourceRegistry()
    registry.register(Source(
        name="Sensor",
        kind=SourceKind.PUBLIC_ENDPOINT,
        sports={"football"},
        capabilities={"fixtures"},
    ))

    def fetch(_request):
        return {"raw": {"events": [{
            "id": "future",
            "home_team": "Tomorrow FC",
            "away_team": "Future Town",
            "commence_time": (now + timedelta(hours=50)).isoformat(),
            "homeOdds": "1.80",
        }]}}

    settings = _settings(tmp_path)
    database = SabiDatabase(settings.v2_db)
    CoverageDiscoveryEngine(
        settings,
        database,
        bundle=SourceBundle(registry=registry, fetchers={"Sensor": fetch}),
    ).refresh(now=now)
    store = CoverageStore(database)
    assert len(store.radar(now=now, horizon_hours=72)) == 1
    assert store.research_candidates("2026-08-28", timezone_name="UTC", limit=120) == []
