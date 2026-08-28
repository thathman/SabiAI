from __future__ import annotations

from fastapi import APIRouter, Query

from sabiai.config import Settings
from sabiai.storage import CoverageStore, SabiDatabase


def create_coverage_dashboard_router(settings: Settings | None = None) -> APIRouter:
    """GET-only V2.4 discovery/market coverage telemetry for the Sabi Boy dashboard."""

    settings = settings or Settings.from_env()
    router = APIRouter(prefix="/api/v2/research", tags=["Sabi Boy V2.4 Coverage"])

    def store() -> CoverageStore:
        database = SabiDatabase(settings.v2_db)
        database.initialize()
        return CoverageStore(database)

    @router.get("/funnel")
    def funnel(run_id: str | None = None):
        return store().funnel(run_id)

    @router.get("/discovery")
    def discovery(
        hours: int = Query(72, ge=1, le=336),
        sport: str | None = None,
        limit: int = Query(500, ge=1, le=5000),
        priced_only: bool = False,
    ):
        rows = store().radar(
            horizon_hours=hours,
            sport=sport,
            limit=limit,
            priced_only=priced_only,
        )
        return {"count": len(rows), "hours": hours, "sport": sport, "events": rows}

    @router.get("/markets")
    def markets(
        event_id: str = Query(..., min_length=1),
        max_age_seconds: int = Query(21600, ge=60, le=604800),
    ):
        return store().market_inventory(event_id, max_age_seconds=max_age_seconds)

    @router.get("/event-sources")
    def event_sources(event_id: str = Query(..., min_length=1)):
        return {"event_id": event_id, "sources": store().event_sources(event_id)}

    return router
