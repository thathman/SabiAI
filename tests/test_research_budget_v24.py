from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from sabiai.config import Settings
from sabiai.research.sharded import merge_research_universe
from sabiai.storage import CoverageStore, SabiDatabase


def test_large_radar_is_bounded_and_keeps_multi_sport_breadth(tmp_path: Path):
    now = datetime.now(timezone.utc)
    settings = Settings(
        repo_root=tmp_path,
        data_dir=tmp_path / "data",
        legacy_bets_db=tmp_path / "legacy.db",
        v2_db=tmp_path / "data" / "v2.db",
        timezone="UTC",
        paid_sources_enabled=False,
        research_sports=("football", "basketball", "tennis"),
        research_max_events=6,
        research_max_events_per_sport=4,
        prefilter_max_events=30,
    )
    database = SabiDatabase(settings.v2_db)
    database.initialize()
    store = CoverageStore(database)

    for sport in settings.research_sports:
        for index in range(12):
            event_id = store.upsert_event({
                "sport": sport,
                "event": f"{sport} home {index} vs {sport} away {index}",
                "home": f"{sport} home {index}",
                "away": f"{sport} away {index}",
                "starts_at": (now + timedelta(hours=1, minutes=index)).isoformat(),
            }, source_name="Fixture Sensor", now=now)
            for family, price in (("winner", 1.80), ("handicap", 1.90), ("total", 1.95)):
                store.record_offer(event_id, {
                    "source_name": "SportyBet",
                    "bookmaker": "SportyBet",
                    "family": family,
                    "market_label": family,
                    "selection_label": f"{family} selection",
                    "decimal_odds": price,
                    "observed_at": now.isoformat(),
                })

    rows = merge_research_universe(settings, store, day=now.date().isoformat(), supplied=[])
    assert len(rows) == 6
    assert {row["sport"] for row in rows} == {"football", "basketball", "tennis"}
    assert all(row["source"] == "SportyBet" for row in rows)
    assert all(len(row["odds"]) >= 3 for row in rows)


def test_quality_remainder_is_not_forced_equal_after_breadth_floor(tmp_path: Path):
    now = datetime.now(timezone.utc)
    settings = Settings(
        repo_root=tmp_path,
        data_dir=tmp_path / "data",
        legacy_bets_db=tmp_path / "legacy.db",
        v2_db=tmp_path / "data" / "v2.db",
        timezone="UTC",
        paid_sources_enabled=False,
        research_sports=("football", "floorball"),
        research_max_events=5,
        research_max_events_per_sport=5,
        prefilter_max_events=20,
    )
    database = SabiDatabase(settings.v2_db)
    database.initialize()
    store = CoverageStore(database)

    for sport, count in (("football", 8), ("floorball", 2)):
        for index in range(count):
            event_id = store.upsert_event({
                "sport": sport,
                "event": f"{sport} {index} home vs {sport} {index} away",
                "home": f"{sport} {index} home",
                "away": f"{sport} {index} away",
                "starts_at": (now + timedelta(hours=1, minutes=index)).isoformat(),
            }, source_name="Fixture Sensor", now=now)
            families = ("winner", "handicap", "total") if sport == "football" else ("winner",)
            for family in families:
                store.record_offer(event_id, {
                    "source_name": "SportyBet",
                    "bookmaker": "SportyBet",
                    "family": family,
                    "market_label": family,
                    "selection_label": f"{family} selection",
                    "decimal_odds": 1.90,
                    "observed_at": now.isoformat(),
                })

    rows = merge_research_universe(settings, store, day=now.date().isoformat(), supplied=[])
    counts = {sport: sum(1 for row in rows if row["sport"] == sport) for sport in {"football", "floorball"}}
    assert counts["floorball"] >= 1
    assert counts["football"] > counts["floorball"]
    assert len(rows) == 5
