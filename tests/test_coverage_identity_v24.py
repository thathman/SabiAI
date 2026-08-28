from datetime import datetime, timedelta, timezone
from pathlib import Path

from sabiai.config import Settings
from sabiai.openclaw import SabiToolGateway
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
    )


def test_provider_stable_id_wins_over_large_kickoff_change(tmp_path: Path):
    settings = _settings(tmp_path)
    database = SabiDatabase(settings.v2_db)
    database.initialize()
    store = CoverageStore(database)
    now = datetime.now(timezone.utc)
    first = store.upsert_event({
        "sport": "football",
        "event": "Arsenal vs Chelsea",
        "home": "Arsenal",
        "away": "Chelsea",
        "starts_at": (now + timedelta(hours=5)).isoformat(),
        "event_id": "provider-event-42",
    }, source_name="Provider A", now=now)
    second = store.upsert_event({
        "sport": "football",
        "event": "Arsenal vs Chelsea",
        "home": "Arsenal",
        "away": "Chelsea",
        "starts_at": (now + timedelta(hours=7)).isoformat(),
        "event_id": "provider-event-42",
    }, source_name="Provider A", now=now + timedelta(minutes=10))
    assert second == first
    with database.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM coverage_events").fetchone()[0] == 1
        row = conn.execute("SELECT starts_at FROM coverage_events WHERE id=?", (first,)).fetchone()
    assert row["starts_at"] == (now + timedelta(hours=7)).isoformat()


def test_action_price_gap_surfaces_sensor_event_but_disappears_after_sportybet_price(tmp_path: Path):
    settings = _settings(tmp_path)
    database = SabiDatabase(settings.v2_db)
    database.initialize()
    store = CoverageStore(database)
    now = datetime.now(timezone.utc)
    event_id = store.upsert_event({
        "sport": "football",
        "event": "Arsenal vs Chelsea",
        "home": "Arsenal",
        "away": "Chelsea",
        "starts_at": (now + timedelta(hours=3)).isoformat(),
    }, source_name="Fixture Sensor", now=now)
    for book, price in (("Book X", 1.80), ("Book Y", 1.95)):
        store.record_offer(event_id, {
            "source_name": "Odds Sensor",
            "bookmaker": book,
            "family": "winner",
            "market_label": "Winner",
            "selection_label": "Arsenal",
            "decimal_odds": price,
            "observed_at": now.isoformat(),
        })

    gateway = SabiToolGateway(settings)
    gap = gateway.dispatch("research.action_price.gaps", {"horizon_hours": 24})
    assert gap["ok"] is True
    assert gap["data"]["count"] == 1
    assert gap["data"]["events"][0]["event"] == "Arsenal vs Chelsea"
    assert gap["data"]["events"][0]["best_sensor_disagreement_pct"] > 0

    store.record_offer(event_id, {
        "source_name": "SportyBet",
        "bookmaker": "SportyBet",
        "family": "winner",
        "market_label": "Winner",
        "selection_label": "Arsenal",
        "decimal_odds": 1.90,
        "observed_at": now.isoformat(),
    })
    resolved = gateway.dispatch("research.action_price.gaps", {"horizon_hours": 24})
    assert resolved["ok"] is True
    assert resolved["data"]["count"] == 0
