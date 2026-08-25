from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, HTTPException, Query

from sabiai.blog import BlogService
from sabiai.config import Settings
from sabiai.sources import SourceHealthService
from sabiai.storage import HistoryService, PerformanceAnalytics, SabiDatabase
from sabiai.system import SystemReadinessService


def _post(post) -> dict:
    return asdict(post)


def create_v2_dashboard_router(settings: Settings | None = None) -> APIRouter:
    """Create the read-only Sabi Boy dashboard API.

    Every route in this router is GET-only. The dashboard is an informative monitor of our
    records; writes remain behind OpenClaw/domain services and are not exposed to browser JS.
    """

    settings = settings or Settings.from_env()
    router = APIRouter(prefix="/api/v2", tags=["Sabi Boy V2 Dashboard"])

    def db() -> SabiDatabase:
        return SabiDatabase(settings.v2_db)

    def history() -> HistoryService:
        return HistoryService(db())

    def analytics() -> PerformanceAnalytics:
        return PerformanceAnalytics(db())

    @router.get("/overview")
    def overview():
        database = db()
        readiness = SystemReadinessService(database).assess()
        return {
            "product": "Sabi Boy",
            "summary": HistoryService(database).summary(),
            "streaks": PerformanceAnalytics(database).streaks(),
            "profit_loss": PerformanceAnalytics(database).profit_loss(),
            "readiness": {
                "state": readiness.label,
                "database_ok": readiness.database_ok,
                "bankroll_ok": readiness.bankroll_ok,
                "stale_settlements": readiness.stale_settlements,
                "issues": [
                    {
                        "severity": issue.severity.label,
                        "area": issue.area,
                        "message": issue.message,
                    }
                    for issue in readiness.issues
                ],
            },
        }

    @router.get("/performance/sports")
    def performance_sports():
        return {"rows": history().by_sport()}

    @router.get("/performance/markets")
    def performance_markets():
        return {"rows": history().by_market()}

    @router.get("/performance/bookmakers")
    def performance_bookmakers():
        return {"rows": history().by_bookmaker()}

    @router.get("/performance/strategies")
    def performance_strategies():
        return {"rows": analytics().by_strategy()}

    @router.get("/performance/competitions")
    def performance_competitions():
        return {"rows": analytics().by_competition()}

    @router.get("/performance/odds-bands")
    def performance_odds_bands():
        return {"rows": analytics().by_odds_band()}

    @router.get("/performance/ticket-sizes")
    def performance_ticket_sizes():
        return {"rows": analytics().by_ticket_size()}

    @router.get("/performance/combined-odds")
    def performance_combined_odds():
        return {"rows": analytics().by_combined_odds_band()}

    @router.get("/tickets/sources")
    def ticket_sources():
        return {"rows": analytics().ticket_sources()}

    @router.get("/tickets/killers")
    def ticket_killers(limit: int = Query(25, ge=1, le=250)):
        return {"rows": analytics().ticket_killers(limit)}

    @router.get("/series/outcomes")
    def outcome_series(days: int = Query(90, ge=1, le=730)):
        return {"rows": analytics().daily_outcomes(days)}

    @router.get("/series/bankroll")
    def bankroll_series(limit: int = Query(365, ge=1, le=5000)):
        return {"rows": analytics().bankroll_series(limit)}

    @router.get("/blog")
    def blog_index(
        category: str | None = None,
        limit: int = Query(50, ge=1, le=250),
    ):
        posts = BlogService(db()).list(status="published", category=category, limit=limit)
        return {"posts": [_post(post) for post in posts]}

    @router.get("/blog/{slug}")
    def blog_post(slug: str):
        post = BlogService(db()).get(slug=slug)
        if post is None or post.status != "published":
            raise HTTPException(status_code=404, detail="Blog post not found.")
        return _post(post)

    @router.get("/system/readiness")
    def system_readiness():
        report = SystemReadinessService(db()).assess()
        return {
            "state": report.label,
            "can_research": report.can_research,
            "can_build_ticket": report.can_build_ticket,
            "database_ok": report.database_ok,
            "bankroll_ok": report.bankroll_ok,
            "stale_settlements": report.stale_settlements,
            "source_states": report.source_states,
            "checked_at": report.checked_at,
            "issues": [
                {
                    "severity": issue.severity.label,
                    "area": issue.area,
                    "message": issue.message,
                }
                for issue in report.issues
            ],
        }

    @router.get("/system/sources")
    def system_sources():
        return {
            "sources": [asdict(item) for item in SourceHealthService(db()).sources()]
        }

    @router.get("/system/api-economy")
    def api_economy():
        return SourceHealthService(db()).economy()

    return router
