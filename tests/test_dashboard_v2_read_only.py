from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from sabiai.config import Settings
from sabiai.dashboard import create_v2_dashboard_router
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
    assert "/api/v2/tickets" in paths
    assert "/api/v2/blog" in paths
    assert "/api/v2/system/readiness" in paths


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
