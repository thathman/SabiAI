from __future__ import annotations

from sabiai.research import CoverageDiscoveryEngine
from sabiai.sources import coverage_source_bundle
from sabiai.storage import CoverageStore


class CoverageTools:
    """OpenClaw reads/actions for the deterministic V2.4 coverage engine."""

    def __init__(self, app):
        self.app = app

    def handlers(self) -> dict:
        return {
            "research.discovery.refresh": self.refresh,
            "research.radar": self.radar,
            "research.market_inventory": self.market_inventory,
            "research.event.sources": self.event_sources,
            "research.coverage.funnel": self.funnel,
        }

    def _store(self) -> CoverageStore:
        return CoverageStore(self.app._db(initialize=True))

    def refresh(self, args: dict) -> dict:
        requested_metered = bool(args.get("allow_metered", False))
        if requested_metered and not bool(getattr(self.app.settings, "coverage_metered_markets_enabled", False)):
            raise ValueError(
                "Metered market coverage is disabled in the Sabi Boy runtime. "
                "Enable SABIAI_COVERAGE_METERED_MARKETS explicitly before using quota-consuming sensors."
            )
        result = CoverageDiscoveryEngine(
            self.app.settings,
            self.app._db(initialize=True),
            bundle=coverage_source_bundle(self.app.settings),
        ).refresh(
            horizon_hours=int(args.get("horizon_hours") or getattr(self.app.settings, "discovery_horizon_hours", 72)),
            allow_metered=requested_metered,
        )
        return result.as_dict()

    def radar(self, args: dict) -> dict:
        rows = self._store().radar(
            horizon_hours=int(args.get("horizon_hours", 72)),
            sport=args.get("sport"),
            limit=int(args.get("limit", 500)),
            priced_only=bool(args.get("priced_only", False)),
        )
        return {"events": rows, "count": len(rows)}

    def market_inventory(self, args: dict) -> dict:
        event_id = str(args.get("event_id") or "").strip()
        if not event_id:
            raise ValueError("research.market_inventory needs event_id.")
        return self._store().market_inventory(
            event_id,
            max_age_seconds=int(args.get("max_age_seconds", 21600)),
        )

    def event_sources(self, args: dict) -> dict:
        event_id = str(args.get("event_id") or "").strip()
        if not event_id:
            raise ValueError("research.event.sources needs event_id.")
        return {"event_id": event_id, "sources": self._store().event_sources(event_id)}

    def funnel(self, args: dict) -> dict:
        return self._store().funnel(args.get("run_id"))
