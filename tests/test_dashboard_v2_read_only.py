from dataclasses import replace
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from sabiai.config import Settings
from sabiai.dashboard import create_v2_dashboard_router
from sabiai.notifications import NotificationHistory
from sabiai.storage import SabiDatabase


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        repo_root=tmp_path,
        data_dir=tmp_path / "data",
        legacy_bets_db=tmp_path / "data" / "bets.db",
        v2_db=tmp_path / "data" / "v2.db",
        timezone="Africa/Lagos",
        paid_sources_enabled=False,
        football_data_token=None,
        thesportsdb_key="123",
    )


def test_v2_dashboard_router_has_no_mutating_http_methods(tmp_path):
    settings = _settings(tmp_path)
    SabiDatabase(settings.v2_db).initialize()
    router = create_v2_dashboard_router(settings)

    methods = set()
    paths = set()
    for route in router.routes:
        paths.add(route.path)
        methods.update(route.methods or set())

    assert methods <= {"GET", "HEAD"}
    assert not ({"POST", "PUT", "PATCH", "DELETE"} & methods)
    assert "/api/v2/overview" in paths
    assert "/api/v2/picks" in paths
    assert "/api/v2/notifications" in paths
    assert "/api/v2/tickets" in paths
    assert "/api/v2/blog" in paths
    assert "/api/v2/system/readiness" in paths
    assert "/api/v2/strategies/plans" in paths
    assert "/api/v2/strategies/learning" in paths
    assert "/api/v2/research/coverage" in paths
    assert "/api/v2/research/cache" in paths


def test_dashboard_router_exposes_detailed_ticket_and_performance_reads(tmp_path):
    settings = _settings(tmp_path)
    SabiDatabase(settings.v2_db).initialize()
    paths = {route.path for route in create_v2_dashboard_router(settings).routes}

    expected = {
        "/api/v2/tickets/{ticket_id}",
        "/api/v2/performance/sports",
        "/api/v2/performance/markets",
        "/api/v2/performance/bookmakers",
        "/api/v2/performance/strategies",
        "/api/v2/performance/odds-bands",
        "/api/v2/performance/ticket-sizes",
        "/api/v2/performance/combined-odds",
        "/api/v2/tickets/killers",
        "/api/v2/series/outcomes",
        "/api/v2/series/bankroll",
    }
    assert expected.issubset(paths)


def test_notification_history_is_readable_from_dashboard(tmp_path):
    settings = _settings(tmp_path)
    database = SabiDatabase(settings.v2_db)
    database.initialize()
    NotificationHistory(database).record(
        {"title": "Sabi Boy picks", "body": "Liverpool to win @ 1.58", "tag": "sabi-boy-daily-picks", "url": "/picks"},
        enabled=True,
        attempted=2,
        delivered=2,
        expired=0,
        failed=0,
    )
    app = FastAPI()
    app.include_router(create_v2_dashboard_router(settings))

    response = TestClient(app).get("/api/v2/notifications?limit=10")

    assert response.status_code == 200
    assert response.json()["rows"][0]["title"] == "Sabi Boy picks"
    assert response.json()["rows"][0]["delivered"] == 2


def test_strategy_plan_read_model_is_readable_from_dashboard(tmp_path):
    settings = _settings(tmp_path)
    database = SabiDatabase(settings.v2_db)
    database.initialize()
    from sabiai.storage import StrategyPlanStore

    StrategyPlanStore(database).save_many(
        [{
            "id": "plan-1",
            "strategy_code": "daily_chain_1_30",
            "name": "Daily 1.30 Chain",
            "status": "ready",
            "target_odds": "1.30",
            "combined_odds": "1.34",
            "suggested_stake": "300.00",
            "confidence_pct": 65,
            "rationale": "Fresh legs.",
            "candidate_count": 2,
            "candidates": [],
            "generated_at": "2026-08-28T08:00:00+00:00",
        }]
    )
    app = FastAPI()
    app.include_router(create_v2_dashboard_router(settings))
    response = TestClient(app).get("/api/v2/strategies/plans")
    assert response.status_code == 200
    assert response.json()["rows"][0]["strategy_code"] == "daily_chain_1_30"


def test_strategy_learning_read_model_is_owner_scoped(tmp_path):
    settings = _settings(tmp_path)
    db = SabiDatabase(settings.v2_db)
    db.initialize()
    app = FastAPI()
    app.include_router(create_v2_dashboard_router(settings))
    response = TestClient(app).get("/api/v2/strategies/learning")
    assert response.status_code == 200
    assert response.json()["owner"] == "sabi_boy"
    assert response.json()["policy"]["automatic_changes"] is False


def test_static_ticket_analytics_routes_are_not_shadowed_by_ticket_detail(tmp_path):
    settings = _settings(tmp_path)
    SabiDatabase(settings.v2_db).initialize()
    app = FastAPI()
    app.include_router(create_v2_dashboard_router(settings))
    client = TestClient(app)

    for path in (
        "/api/v2/tickets/sources",
        "/api/v2/tickets/killers",
        "/api/v2/tickets/version-outcomes",
    ):
        response = client.get(path)
        assert response.status_code == 200, response.text


def test_source_screen_syncs_every_configured_runtime_source(tmp_path):
    settings = replace(
        _settings(tmp_path),
        parse_api_key="test-key",
        parse_flashscore_scraper_id="flashscore-id",
        parse_livescore_scraper_id="livescore-id",
        parse_sportybet_scraper_id="sportybet-id",
        parse_espn_scraper_id="espn-id",
        sports_betting_analyzer_api_key="analyzer-key",
    )
    app = FastAPI()
    app.include_router(create_v2_dashboard_router(settings))

    response = TestClient(app).get("/api/v2/system/sources")

    assert response.status_code == 200
    rows = {row["name"]: row for row in response.json()["sources"]}
    assert {
        "TheSportsDB",
        "ESPN Public Data",
        "OpenClaw Browser",
        "OpenClaw Search",
        "Parse · Flashscore",
        "Parse · LiveScore",
        "Parse · SportyBet",
        "Parse · ESPN",
        "Sports Betting AI Analyzer",
    } <= rows.keys()
    assert all(row["state"] == "not_used_yet" for row in rows.values())
    assert "Parse · 1xBet" not in rows
    assert "Stake" not in rows
