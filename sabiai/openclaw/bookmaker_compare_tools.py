from __future__ import annotations

from sabiai.bookmakers import BookmakerBrowserProfiles

from .helpers import ticket_from_args
from .serializers import json_value


class BookmakerCompareTools:
    """Plan the same exact ticket/selection search across multiple bookmakers."""

    def __init__(self, app):
        self.app = app
        self.profiles = BookmakerBrowserProfiles()

    def handlers(self) -> dict:
        return {"bookmaker.compare.plan": self.plan}

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
                "Run the ready browser searches, stamp every observed price, then feed normalized quotes to market.compare."
            ),
        }
