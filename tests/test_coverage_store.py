from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from sabiai.storage import CoverageStore, SabiDatabase


def test_coverage_store_unions_provider_ids_and_market_inventory(tmp_path: Path):
    database = SabiDatabase(tmp_path / "sabi.db")
    database.initialize()
    store = CoverageStore(database)
    now = datetime.now(timezone.utc)
    starts = now + timedelta(hours=6)

    event = {
        "sport": "football",
        "event": "Arsenal vs Chelsea",
        "home": "Arsenal",
        "away": "Chelsea",
        "competition": "Premier League",
        "starts_at": starts.isoformat(),
        "event_id": "provider-a-123",
    }
    event_id = store.upsert_event(event, source_name="Source A", now=now)
    second = dict(event, event_id="provider-b-999")
    assert store.upsert_event(second, source_name="Source B", now=now) == event_id

    sources = store.event_sources(event_id)
    assert {row["source_name"] for row in sources} == {"Source A", "Source B"}
    assert {row["source_event_id"] for row in sources} == {"provider-a-123", "provider-b-999"}

    market = {
        "source_name": "Odds Sensor",
        "bookmaker": "Example Book",
        "source_market_key": "totals",
        "family": "total",
        "metric": "goals",
        "period": "full match",
        "line": 2.5,
        "market_label": "Total goals",
    }
    catalogue_id = store.upsert_market(event_id, market)
    store.record_offer(event_id, {
        **market,
        "catalogue_id": catalogue_id,
        "selection_label": "Over 2.5",
        "side": "over",
        "decimal_odds": 1.91,
        "observed_at": now.isoformat(),
    })

    inventory = store.market_inventory(event_id, max_age_seconds=3600)
    assert inventory["event"]["event_name"] == "Arsenal vs Chelsea"
    assert inventory["catalogue"][0]["family"] == "total"
    assert inventory["offers"][0]["selection_label"] == "Over 2.5"

    radar = store.radar(now=now, horizon_hours=24)
    assert len(radar) == 1
    assert radar[0]["source_count"] == 2
    assert radar[0]["market_family_count"] == 1


def test_market_inventory_excludes_stale_prices(tmp_path: Path):
    database = SabiDatabase(tmp_path / "sabi.db")
    database.initialize()
    store = CoverageStore(database)
    now = datetime.now(timezone.utc)
    event_id = store.upsert_event({
        "sport": "basketball",
        "event": "Home vs Away",
        "home": "Home",
        "away": "Away",
        "starts_at": (now + timedelta(hours=3)).isoformat(),
    }, source_name="Sensor", now=now)
    store.record_offer(event_id, {
        "source_name": "Sensor",
        "bookmaker": "Book",
        "family": "total",
        "market_label": "Total points",
        "selection_label": "Over 220.5",
        "line": 220.5,
        "decimal_odds": 1.91,
        "observed_at": (now - timedelta(hours=2)).isoformat(),
    })
    assert store.market_inventory(event_id, max_age_seconds=300)["offers"] == []
    assert len(store.market_inventory(event_id, max_age_seconds=10800)["offers"]) == 1


def test_research_candidates_round_robin_sports(tmp_path: Path):
    database = SabiDatabase(tmp_path / "sabi.db")
    database.initialize()
    store = CoverageStore(database)
    now = datetime.now(timezone.utc)
    day = now.date().isoformat()

    for sport in ("football", "tennis"):
        for index in range(4):
            name = f"{sport} home {index} vs {sport} away {index}"
            event_id = store.upsert_event({
                "sport": sport,
                "event": name,
                "home": f"{sport} home {index}",
                "away": f"{sport} away {index}",
                "competition": "Test",
                "starts_at": (now + timedelta(hours=index + 1)).isoformat(),
                "event_id": f"{sport}-{index}",
            }, source_name="Sensor", now=now)
            store.record_offer(event_id, {
                "source_name": "Sensor",
                "bookmaker": "Book",
                "family": "winner",
                "market_label": "Winner",
                "selection_label": f"{sport} home {index}",
                "decimal_odds": 1.8 + index / 10,
                "observed_at": now.isoformat(),
            })

    rows = store.research_candidates(day, timezone_name="UTC", limit=4)
    assert len(rows) == 4
    assert [row["sport"] for row in rows] == ["football", "tennis", "football", "tennis"]
