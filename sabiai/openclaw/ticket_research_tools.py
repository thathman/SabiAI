from __future__ import annotations

from sabiai.tickets import TicketResearchPlanner
from sabiai.storage import DailyResearchLog, ResearchSliceStore

from .helpers import ticket_from_args
from .serializers import json_value
from .sports_insight_tools import SportsInsightTools


class TicketResearchTools:
    """Research a whole ticket without turning the dashboard into a sports portal."""

    def __init__(self, app):
        self.app = app
        self.planner = TicketResearchPlanner(app.research_planner)
        self.insights = SportsInsightTools(app)

    def handlers(self) -> dict:
        return {
            "ticket.research.plan": self.plan,
            "ticket.research.snapshot": self.snapshot,
        }

    def plan(self, args: dict) -> dict:
        ticket = ticket_from_args(self.app, args)
        plan = self.planner.plan(ticket)
        result = json_value(plan)
        result["daily_scan_context"] = DailyResearchLog(
            self.app._db(initialize=True)
        ).context(limit=int(args.get("scan_limit", 3)))
        cache = ResearchSliceStore(self.app._db(initialize=True))
        result["cached_event_context"] = {
            leg.event: cache.find_event(leg.event, scan_date=args.get("scan_date"), max_age_seconds=int(args.get("cache_max_age_seconds", 86400)))
            for leg in plan.legs
            if leg.event
        }
        return result

    def snapshot(self, args: dict) -> dict:
        ticket = ticket_from_args(self.app, args)
        plan = self.planner.plan(ticket)
        context = args.get("event_context") or {}
        if not isinstance(context, dict):
            raise ValueError("event_context must be an object keyed by event name or leg id.")
        max_legs = max(1, min(int(args.get("max_legs", 25)), 100))
        if len(ticket.legs) > max_legs:
            raise ValueError(
                f"Ticket has {len(ticket.legs)} legs; max_legs is {max_legs}. Split the research run or explicitly raise max_legs."
            )

        rows: list[dict] = []
        for leg_plan in plan.legs:
            row = {
                "leg_id": leg_plan.leg_id,
                "event": leg_plan.event,
                "sport": leg_plan.sport,
                "selection": leg_plan.selection,
                "research_plan": json_value(leg_plan),
                "snapshot": None,
                "error": None,
            }
            if not leg_plan.home or not leg_plan.away or not leg_plan.sport:
                row["error"] = (
                    "This leg needs event/participant resolution before automatic match research. "
                    "Use the Research Scout and keep the visible event/market unchanged."
                )
                rows.append(row)
                continue

            extra = context.get(leg_plan.leg_id) or context.get(leg_plan.event) or {}
            if not isinstance(extra, dict):
                extra = {}
            snapshot_args = {
                "home": leg_plan.home,
                "away": leg_plan.away,
                "sport": leg_plan.sport,
                "market": leg_plan.selection,
                "limit": int(extra.get("limit", args.get("form_limit", 10))),
                **{key: value for key, value in extra.items() if key != "limit"},
            }
            try:
                row["snapshot"] = self.insights.match_snapshot(snapshot_args)
            except Exception as exc:
                row["error"] = str(exc)
            rows.append(row)

        completed = sum(1 for row in rows if row["snapshot"] is not None)
        return {
            "ticket_id": ticket.id,
            "leg_count": len(ticket.legs),
            "researched": completed,
            "needs_followup": len(ticket.legs) - completed,
            "skeptic_required": plan.skeptic_required,
            "skeptic_reasons": list(plan.reasons),
            "legs": rows,
        }
