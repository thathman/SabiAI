from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, HTTPException, Query

from sabiai.blog import BlogService
from sabiai.config import Settings
from sabiai.notifications import NotificationHistory
from sabiai.sources import SourceHealthService, default_source_bundle
from sabiai.storage import (
    AdvancedAnalytics,
    DashboardReadService,
    HistoryService,
    PerformanceAnalytics,
    SabiDatabase,
    StrategyPlanStore,
)
from sabiai.system import SystemReadinessService
from sabiai.strategy import StrategyChainStore, StrategyLearningService


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

    def advanced() -> AdvancedAnalytics:
        return AdvancedAnalytics(db())

    def reads() -> DashboardReadService:
        return DashboardReadService(db())

    @router.get("/overview")
    def overview():
        database = db()
        database.initialize()
        readiness = SystemReadinessService(database).assess()
        read_service = DashboardReadService(database)
        return {
            "product": "Sabi Boy",
            "summary": HistoryService(database).summary(owner="sabi_boy", record_kind="pick"),
            "streaks": PerformanceAnalytics(database).streaks(owner="sabi_boy", record_kind="pick"),
            "profit_loss": PerformanceAnalytics(database).profit_loss(),
            "recent_picks": read_service.picks(limit=8, owner="sabi_boy", record_kind="pick"),
            "recent_tickets": read_service.tickets(limit=5),
            "strategy_plans": StrategyPlanStore(database).latest_by_strategy(),
            "strategy_learning": StrategyLearningService(database).summaries(owner="sabi_boy"),
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

    @router.get("/picks")
    def picks(
        limit: int = Query(100, ge=1, le=1000),
        outcome: str | None = None,
        sport: str | None = None,
        strategy: str | None = None,
        owner: str | None = None,
        record_kind: str | None = None,
    ):
        return {
            "rows": reads().picks(
                limit=limit,
                outcome=outcome,
                sport=sport,
                strategy=strategy,
                owner=owner,
                record_kind=record_kind,
            )
        }

    @router.get("/notifications")
    def notifications(
        limit: int = Query(100, ge=1, le=500),
        tag: str | None = None,
    ):
        database = db()
        database.initialize()
        return {"rows": NotificationHistory(database).list(limit=limit, tag=tag)}

    @router.get("/tickets")
    def tickets(
        limit: int = Query(100, ge=1, le=1000),
        status: str | None = None,
        source_type: str | None = None,
    ):
        return {
            "rows": reads().tickets(
                limit=limit,
                status=status,
                source_type=source_type,
            )
        }

    @router.get("/filters")
    def filters():
        service = reads()
        return {
            "sports": service.sports(),
            "strategies": service.strategies(),
            "owners": ["sabi_boy", "hendrix"],
            "record_kinds": ["pick", "tip"],
        }

    @router.get("/performance/sports")
    def performance_sports():
        return {"rows": history().by_sport(owner="sabi_boy", record_kind="pick")}

    @router.get("/performance/markets")
    def performance_markets():
        return {"rows": history().by_market(owner="sabi_boy", record_kind="pick")}

    @router.get("/performance/bookmakers")
    def performance_bookmakers():
        return {"rows": history().by_bookmaker(owner="sabi_boy", record_kind="pick")}

    @router.get("/performance/strategies")
    def performance_strategies():
        return {"rows": analytics().by_strategy(owner="sabi_boy", record_kind="pick")}

    @router.get("/strategies/plans")
    def strategy_plans(
        limit: int = Query(30, ge=1, le=200),
        strategy_code: str | None = None,
    ):
        database = db()
        database.initialize()
        return {"rows": StrategyPlanStore(database).latest(limit=limit, strategy_code=strategy_code)}

    @router.get("/strategies/learning")
    def strategy_learning(
        owner: str = Query("sabi_boy"),
        limit: int = Query(50, ge=1, le=250),
    ):
        database = db()
        database.initialize()
        return {
            "owner": owner,
            "rows": StrategyLearningService(database).summaries(owner=owner, limit=limit),
            "policy": {
                "minimum_sample": StrategyLearningService.MIN_SAMPLE,
                "policy_sample": StrategyLearningService.POLICY_SAMPLE,
                "automatic_changes": False,
            },
        }

    @router.get("/strategies/chain")
    def strategy_chain():
        database = db()
        database.initialize()
        return {"chain": StrategyChainStore(database).get()}

    @router.get("/performance/competitions")
    def performance_competitions():
        return {"rows": analytics().by_competition(owner="sabi_boy", record_kind="pick")}

    @router.get("/performance/odds-bands")
    def performance_odds_bands():
        return {"rows": analytics().by_odds_band(owner="sabi_boy", record_kind="pick")}

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

    @router.get("/tickets/version-outcomes")
    def ticket_version_outcomes(limit: int = Query(250, ge=1, le=1000)):
        return advanced().ticket_version_outcomes(limit)

    @router.get("/tickets/{ticket_id}")
    def ticket_detail(ticket_id: str):
        row = reads().ticket(ticket_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Ticket not found.")
        return row

    @router.get("/bookmakers/price-history")
    def bookmaker_price_history(limit: int = Query(100, ge=1, le=1000)):
        return {"rows": advanced().bookmaker_price_history(limit)}

    @router.get("/bookmakers/price-disagreements")
    def bookmaker_price_disagreements(limit: int = Query(50, ge=1, le=500)):
        return {"rows": advanced().latest_price_disagreements(limit)}

    @router.get("/series/outcomes")
    def outcome_series(days: int = Query(90, ge=1, le=730)):
        return {"rows": analytics().daily_outcomes(days, owner="sabi_boy", record_kind="pick")}

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
        database = db()
        database.initialize()
        for source in default_source_bundle(settings).registry.all():
            database.upsert_source(source)
        return {
            "sources": [asdict(item) for item in SourceHealthService(database).sources()]
        }

    @router.get("/system/api-economy")
    def api_economy():
        return SourceHealthService(db()).economy()

    return router
