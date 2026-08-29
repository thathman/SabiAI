from __future__ import annotations

from pathlib import Path

from sabiai.config import Settings
from sabiai.sources import (
    BetfairExchangeAdapter,
    SourceCost,
    SourceRequest,
    TheOddsApiDiscoveryAdapter,
    TheOddsApiMarketsAdapter,
    coverage_source_bundle,
)


def _settings(tmp_path: Path, **overrides) -> Settings:
    values = {
        "repo_root": tmp_path,
        "data_dir": tmp_path / "data",
        "legacy_bets_db": tmp_path / "legacy.db",
        "v2_db": tmp_path / "data" / "v2.db",
        "timezone": "UTC",
        "paid_sources_enabled": False,
    }
    values.update(overrides)
    return Settings(**values)


def test_the_odds_discovery_uses_separate_zero_quota_surface():
    calls = []

    def fake_get(url, *, params=None, headers=None):
        calls.append((url, params))
        if url.endswith("/sports/"):
            return [{"key": "soccer_epl", "group": "Soccer", "title": "Premier League", "active": True}]
        return [{"id": "evt-1", "home_team": "Arsenal", "away_team": "Chelsea", "commence_time": "2026-08-29T15:00:00Z"}]

    adapter = TheOddsApiDiscoveryAdapter(api_key="secret", http_get=fake_get)
    sports = adapter.fetch(SourceRequest(request_key="sports", capability="sport_catalog"))
    events = adapter.fetch(SourceRequest(
        request_key="events",
        capability="fixtures",
        sport="football",
        metadata={"provider_sport": "soccer_epl"},
    ))
    assert sports["raw"]["quota_cost"] == 0
    assert events["raw"]["quota_cost"] == 0
    assert calls[0][0].endswith("/sports/")
    assert calls[1][0].endswith("/sports/soccer_epl/events")


def test_the_odds_market_sensor_is_explicitly_metered():
    adapter = TheOddsApiMarketsAdapter(api_key="secret", http_get=lambda *a, **k: [])
    assert adapter.source.cost is SourceCost.PAID
    assert "odds" in adapter.source.capabilities
    assert "event_odds" in adapter.source.capabilities


def test_coverage_bundle_excludes_parse_from_frequent_radar_by_default(tmp_path: Path):
    settings = _settings(
        tmp_path,
        parse_api_key="parse-secret",
        parse_flashscore_scraper_id="scraper-123",
        discovery_parse_union_enabled=False,
    )
    bundle = coverage_source_bundle(settings)
    assert "Parse · Flashscore" not in bundle.fetchers

    enabled = coverage_source_bundle(_settings(
        tmp_path,
        parse_api_key="parse-secret",
        parse_flashscore_scraper_id="scraper-123",
        discovery_parse_union_enabled=True,
    ))
    assert "Parse · Flashscore" in enabled.fetchers


def test_betfair_adapter_exposes_reads_only():
    methods = []

    def fake_post(url, *, payload=None, headers=None):
        methods.append(payload["method"])
        if payload["method"].endswith("listEventTypes"):
            return {"jsonrpc": "2.0", "id": 1, "result": [{"eventType": {"id": "1", "name": "Soccer"}}]}
        return {"jsonrpc": "2.0", "id": 1, "result": []}

    adapter = BetfairExchangeAdapter(app_key="app", session_token="session", http_post=fake_post)
    result = adapter.fetch(SourceRequest(request_key="bf", capability="sport_catalog"))
    assert result["raw"]["event_types"][0]["eventType"]["name"] == "Soccer"
    assert methods == ["SportsAPING/v1.0/listEventTypes"]
    assert not hasattr(adapter, "place_orders")
    assert not any("placeOrders" in name for name in dir(adapter))
