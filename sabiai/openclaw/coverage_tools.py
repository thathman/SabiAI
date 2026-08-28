from __future__ import annotations

from sabiai.research import CoverageDiscoveryEngine, canonical_action_book, market_consensus
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
            "research.action_price.gaps": self.action_price_gaps,
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
            horizon_hours=int(
                args.get("horizon_hours")
                or getattr(self.app.settings, "discovery_horizon_hours", 72)
            ),
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
        inventory = self._store().market_inventory(
            event_id,
            max_age_seconds=int(args.get("max_age_seconds", 21600)),
        )
        inventory["consensus"] = market_consensus(inventory.get("offers") or [])
        return inventory

    def event_sources(self, args: dict) -> dict:
        event_id = str(args.get("event_id") or "").strip()
        if not event_id:
            raise ValueError("research.event.sources needs event_id.")
        return {"event_id": event_id, "sources": self._store().event_sources(event_id)}

    def funnel(self, args: dict) -> dict:
        return self._store().funnel(args.get("run_id"))

    def action_price_gaps(self, args: dict) -> dict:
        """Prioritize sensor-covered events that still need SportyBet/Bet9ja verification."""

        store = self._store()
        rows = store.radar(
            horizon_hours=int(args.get("horizon_hours", 72)),
            sport=args.get("sport"),
            limit=min(max(int(args.get("scan_limit", 1000)), 1), 5000),
            priced_only=True,
        )
        output = []
        max_age = int(args.get("max_age_seconds", 7200))
        for event in rows:
            inventory = store.market_inventory(str(event["id"]), max_age_seconds=max_age)
            offers = inventory.get("offers") or []
            if not offers:
                continue
            action_books = sorted({
                book
                for offer in offers
                for book in [canonical_action_book(offer.get("bookmaker") or offer.get("source_name"))]
                if book
            })
            if action_books:
                continue
            consensus = market_consensus(offers)
            output.append({
                "event_id": event["id"],
                "sport": event.get("sport"),
                "event": event.get("event_name"),
                "competition": event.get("competition"),
                "starts_at": event.get("starts_at"),
                "source_count": event.get("source_count"),
                "market_family_count": event.get("market_family_count"),
                "fresh_bookmaker_count": event.get("fresh_bookmaker_count"),
                "best_sensor_disagreement_pct": max(
                    (float(row.get("price_disagreement_pct") or 0) for row in consensus),
                    default=0.0,
                ),
                "market_consensus": consensus[:5],
                "needed": "Verify the exact shortlisted markets on SportyBet and/or Bet9ja before automatic promotion or ticket work.",
            })
        output.sort(
            key=lambda row: (
                -float(row.get("best_sensor_disagreement_pct") or 0),
                -int(row.get("market_family_count") or 0),
                -int(row.get("source_count") or 0),
                str(row.get("starts_at") or ""),
            )
        )
        limit = min(max(int(args.get("limit", 50)), 1), 250)
        return {"count": len(output[:limit]), "events": output[:limit]}
