from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from sabiai.config import Settings
from sabiai.dashboard import create_coverage_dashboard_router
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


def test_coverage_dashboard_routes_are_get_only_and_report_radar(tmp_path: Path):
    settings = _settings(tmp_path)
    database = SabiDatabase(settings.v2_db)
    database.initialize()
    now = datetime.now(timezone.utc)
    CoverageStore(database).upsert_event({
        "sport": "football",
        "event": "Arsenal vs Chelsea",
        "home": "Arsenal",
        "away": "Chelsea",
        "starts_at": (now + timedelta(hours=3)).isoformat(),
    }, source_name="Sensor", now=now)

    app = FastAPI()
    router = create_coverage_dashboard_router(settings)
    app.include_router(router)
    for route in router.routes:
        assert set(route.methods or ()) <= {"GET", "HEAD"}

    client = TestClient(app)
    response = client.get("/api/v2/research/discovery?hours=24")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 1
    assert data["events"][0]["event_name"] == "Arsenal vs Chelsea"
    assert client.post("/api/v2/research/discovery").status_code == 405


def test_openclaw_tool_surface_includes_coverage_engine_without_network_call(tmp_path: Path):
    gateway = SabiToolGateway(_settings(tmp_path))
    tools = gateway.dispatch("system.tools")["data"]["tools"]
    required = {
        "research.discovery.refresh",
        "research.radar",
        "research.market_inventory",
        "research.event.sources",
        "research.coverage.funnel",
    }
    assert required.issubset(set(tools))
    assert gateway.dispatch("research.radar", {"horizon_hours": 72})["data"]["count"] == 0
    funnel = gateway.dispatch("research.coverage.funnel")["data"]
    assert funnel["discovered"] == 0
    assert funnel["selected"] == 0
