from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from sabiai.config import Settings
from sabiai.research.prefilter import CoveragePrefilter, canonical_action_book, market_consensus
from sabiai.storage import CoverageStore, SabiDatabase


def _settings(tmp_path: Path, **overrides) -> Settings:
    values = {
        "repo_root": tmp_path,
        "data_dir": tmp_path / "data",
        "legacy_bets_db": tmp_path / "legacy.db",
        "v2_db": tmp_path / "data" / "v2.db",
        "timezone": "UTC",
        "paid_sources_enabled": False,
        "research_sports": ("football", "tennis"),
        "research_max_events": 6,
        "research_max_events_per_sport": 4,
        "prefilter_max_events": 20,
    }
    values.update(overrides)
    return Settings(**values)


def _event(store, now, sport, index):
    return store.upsert_event({
        "sport": sport,
        "event": f"{sport} home {index} vs {sport} away {index}",
        "home": f"{sport} home {index}",
        "away": f"{sport} away {index}",
        "starts_at": (now + timedelta(hours=1, minutes=index)).isoformat(),
    }, source_name="Fixture Sensor", now=now)


def test_sensor_only_prices_never_become_actionable_odds(tmp_path: Path):
    settings = _settings(tmp_path)
    database = SabiDatabase(settings.v2_db)
    database.initialize()
    store = CoverageStore(database)
    now = datetime.now(timezone.utc)
    event_id = _event(store, now, "football", 1)
    store.record_offer(event_id, {
        "source_name": "Market Sensor",
        "bookmaker": "Book X",
        "family": "winner",
        "market_label": "Winner",
        "selection_label": "football home 1",
        "decimal_odds": 2.20,
        "observed_at": now.isoformat(),
    })

    assert CoveragePrefilter(settings, store).select(now.date().isoformat(), actionable_only=True) == []
    watch = CoveragePrefilter(settings, store).select(now.date().isoformat(), actionable_only=False)
    assert len(watch) == 1
    assert watch[0]["odds"] == []
    assert watch[0]["action_price_available"] is False
    assert watch[0]["source"] == "Market sensors"


def test_action_book_odds_are_exposed_but_sensor_consensus_is_preserved(tmp_path: Path):
    settings = _settings(tmp_path)
    database = SabiDatabase(settings.v2_db)
    database.initialize()
    store = CoverageStore(database)
    now = datetime.now(timezone.utc)
    event_id = _event(store, now, "football", 2)
    for bookmaker, price in (("SportyBet", 1.95), ("Book X", 1.78), ("Book Y", 1.82)):
        store.record_offer(event_id, {
            "source_name": bookmaker,
            "bookmaker": bookmaker,
            "family": "winner",
            "market_label": "Winner",
            "selection_label": "football home 2",
            "decimal_odds": price,
            "observed_at": now.isoformat(),
        })

    rows = CoveragePrefilter(settings, store).select(now.date().isoformat())
    assert len(rows) == 1
    row = rows[0]
    assert row["source"] == "SportyBet"
    assert row["odds"] == [{
        "label": "football home 2",
        "decimal_odds": 1.95,
        "market": "winner",
        "line": None,
        "period": None,
        "participant": None,
        "bookmaker": "SportyBet",
        "observed_at": now.isoformat(),
    }]
    assert row["market_consensus"][0]["bookmakers"] == 3
    assert row["market_consensus"][0]["median_odds"] == 1.82
    assert row["market_consensus"][0]["best_bookmaker"] == "SportyBet"


def test_market_consensus_never_combines_different_lines():
    rows = market_consensus([
        {"bookmaker": "SportyBet", "family": "total", "line": 2.5, "side": "over", "selection_label": "Over 2.5", "decimal_odds": 1.90},
        {"bookmaker": "Book X", "family": "total", "line": 3.5, "side": "over", "selection_label": "Over 3.5", "decimal_odds": 2.40},
    ])
    assert len(rows) == 2
    assert {row["line"] for row in rows} == {2.5, 3.5}


def test_action_book_aliases_are_conservative():
    assert canonical_action_book("Parse · SportyBet") == "SportyBet"
    assert canonical_action_book("Bet9ja") == "Bet9ja"
    assert canonical_action_book("Stake") is None
    assert canonical_action_book("Market Sensor") is None
