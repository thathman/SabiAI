from __future__ import annotations

from dataclasses import asdict

from sabiai.bookmakers import (
    BookmakerBrowserProfiles,
    BookmakerOfferService,
    TicketPriceComparisonService,
)
from sabiai.storage import OfferObservationStore

from .helpers import bookmaker_slug, ticket_from_args
from .serializers import json_value


class BookmakerCompareTools:
    """Plan and ingest the same exact ticket/selection search across bookmakers."""

    def __init__(self, app):
        self.app = app
        self.profiles = BookmakerBrowserProfiles()
        self.offer_service = BookmakerOfferService(app.bookmakers)
        self.comparison = TicketPriceComparisonService(app.ticket_converter)

    def handlers(self) -> dict:
        return {
            "bookmaker.compare.plan": self.plan,
            "bookmaker.compare.from_search": self.from_search,
        }

    def plan(self, args: dict) -> dict:
        ticket = ticket_from_args(self.app, args)
        requested = args.get("bookmakers")
        if requested is None:
            requested = [bookmaker.name for bookmaker in self.app.bookmakers.all()]
        if isinstance(requested, str):
            requested = [requested]
        if not isinstance(requested, list) or not requested:
            raise ValueError("bookmakers must be a non-empty list or bookmaker name.")

        plans = []
        unknown = []
        ready_count = 0
        for value in requested:
            bookmaker = self.app.bookmakers.resolve(str(value))
            if bookmaker is None:
                unknown.append(str(value))
                continue
            search = self.app.bookmaker_discovery.plan_conversion(
                ticket,
                target_bookmaker=bookmaker.name,
            )
            profile = self.profiles.market_search(bookmaker.slug)
            browser_ready = bool(profile and profile.ready and profile.entry_url)
            if browser_ready and search.ready:
                ready_count += 1
            plans.append(
                {
                    "bookmaker": bookmaker.name,
                    "slug": bookmaker.slug,
                    "search_ready": search.ready,
                    "browser_ready": browser_ready,
                    "tasks": json_value(search.tasks),
                    "missing_context": list(search.missing_context),
                    "browser_playbook": json_value(profile) if profile else None,
                }
            )

        return {
            "ticket_id": ticket.id,
            "leg_count": len(ticket.legs),
            "bookmakers_requested": len(requested),
            "bookmakers_ready": ready_count,
            "unknown_bookmakers": unknown,
            "plans": plans,
            "next_step": (
                "Run each ready browser search for the exact requested event/market/line/period. "
                "Return current decimal odds with observed_at, then call bookmaker.compare.from_search."
            ),
        }

    def from_search(self, args: dict) -> dict:
        ticket = ticket_from_args(self.app, args)
        raw_batches = args.get("results")
        if not isinstance(raw_batches, list) or not raw_batches:
            raise ValueError(
                "bookmaker.compare.from_search needs results as a list of {bookmaker, offers} objects."
            )

        max_age_seconds = int(args.get("max_age_seconds", 180))
        source_draft_id = str(args.get("source_draft_id") or "").strip() or None
        batches = []
        search_results = []
        observations = []
        store = OfferObservationStore(self.app._db(initialize=True))

        for index, raw in enumerate(raw_batches, start=1):
            if not isinstance(raw, dict):
                search_results.append(
                    {
                        "row": index,
                        "usable": False,
                        "issues": [
                            {"level": "error", "message": "Bookmaker result must be an object."}
                        ],
                    }
                )
                continue

            name = str(raw.get("bookmaker") or raw.get("target_bookmaker") or "").strip()
            offers = raw.get("offers")
            if not name or not isinstance(offers, list):
                search_results.append(
                    {
                        "row": index,
                        "bookmaker": name or None,
                        "usable": False,
                        "issues": [
                            {
                                "level": "error",
                                "message": "Each result needs bookmaker and offers[].",
                            }
                        ],
                    }
                )
                continue

            try:
                batch = self.offer_service.normalize(
                    target_bookmaker=name,
                    rows=offers,
                    source=str(raw.get("source") or args.get("source") or "openclaw_browser"),
                    require_fresh=True,
                    max_age_seconds=max_age_seconds,
                )
            except ValueError as exc:
                search_results.append(
                    {
                        "row": index,
                        "bookmaker": name,
                        "usable": False,
                        "issues": [{"level": "error", "message": str(exc)}],
                    }
                )
                continue

            batches.append(batch)
            saved = []
            for item in batch.offers:
                if not item.observed_at:
                    continue
                observation = store.save(
                    target_bookmaker_slug=batch.target_bookmaker_slug,
                    sport=item.offer.sport,
                    event=item.offer.event,
                    home=item.offer.home,
                    away=item.offer.away,
                    event_ref=item.offer.event_ref,
                    market=item.offer.market,
                    market_ref=item.offer.market_ref,
                    decimal_odds=str(item.offer.odds),
                    observed_at=item.observed_at,
                    source=item.source,
                    source_draft_id=source_draft_id,
                    raw={
                        "purpose": "multi_book_price_compare",
                        "max_age_seconds": max_age_seconds,
                    },
                )
                row = json_value(observation)
                saved.append(row)
                observations.append(row)

            search_results.append(
                {
                    "bookmaker": batch.target_bookmaker_slug,
                    "usable": batch.usable,
                    "offers": len(batch.offers),
                    "issues": [asdict(issue) for issue in batch.issues],
                    "observations": saved,
                }
            )

        source_book = bookmaker_slug(self.app, args.get("bookmaker"))
        comparison = self.comparison.compare(
            ticket,
            batches=batches,
            source_bookmaker_slug=source_book,
        )

        return {
            "complete": comparison.complete,
            "priced_legs": comparison.priced_legs,
            "ticket_legs": len(comparison.legs),
            "legs": [
                {
                    "source_leg_id": leg.source_leg_id,
                    "event": leg.event,
                    "selection": leg.selection,
                    "source_ticket_odds": str(leg.source_ticket_odds),
                    "best": (
                        {
                            "bookmaker": leg.best.bookmaker_slug,
                            "odds": str(leg.best.odds),
                            "event": leg.best.event,
                            "selection": leg.best.selection,
                        }
                        if leg.best
                        else None
                    ),
                    "prices": [
                        {
                            "bookmaker": row.bookmaker_slug,
                            "odds": str(row.odds),
                            "event": row.event,
                            "selection": row.selection,
                            "event_ref": row.event_ref,
                            "market_ref": row.market_ref,
                        }
                        for row in leg.prices
                    ],
                }
                for leg in comparison.legs
            ],
            "bookmaker_notes": comparison.bookmaker_notes,
            "search_results": search_results,
            "observations": observations,
            "note": (
                "Best prices include only fresh exact-equivalent bookmaker offers returned in this search. "
                "The original ticket odds are source context and are not assumed current."
            ),
        }
