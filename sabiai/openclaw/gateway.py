from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from decimal import Decimal

from sabiai import __version__
from sabiai.bookmakers import default_bookmakers
from sabiai.config import Settings
from sabiai.domain.models import Market, Selection, Ticket, TicketLeg
from sabiai.markets import MarketInterpreter
from sabiai.odds import ArbitrageEngine, PriceQuote, SettlementRules
from sabiai.sports import ResearchPlanner, default_sports
from sabiai.storage import SabiDatabase
from sabiai.tickets import TicketWorkshop


class SabiToolGateway:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings.from_env()
        self.market_interpreter = MarketInterpreter()
        self.bookmakers = default_bookmakers()
        self.sports = default_sports()
        self.research_planner = ResearchPlanner(self.sports)
        self.ticket_workshop = TicketWorkshop()
        self.arbitrage = ArbitrageEngine()

    def dispatch(self, tool: str, args: dict | None = None) -> dict:
        handlers = {
            "system.health": self.system_health,
            "sports.list": self.sports_list,
            "sports.describe": self.sports_describe,
            "research.plan": self.research_plan,
            "market.interpret": self.market_interpret,
            "market.arbitrage": self.market_arbitrage,
            "bookmaker.resolve": self.bookmaker_resolve,
            "ticket.split": self.ticket_split,
            "ticket.trim": self.ticket_trim,
        }
        handler = handlers.get(tool)
        if handler is None:
            return {"ok": False, "error": f"Unknown Sabi V2 tool: {tool}"}
        try:
            return {"ok": True, "tool": tool, "data": handler(args or {})}
        except Exception as exc:
            return {"ok": False, "tool": tool, "error": str(exc)}

    def system_health(self, args: dict) -> dict:
        db = SabiDatabase(self.settings.v2_db)
        exists = self.settings.v2_db.exists()
        if not exists:
            return {"version": __version__, "database": str(self.settings.v2_db), "database_exists": False, "database_ok": False}
        try:
            version = db.schema_version()
            return {"version": __version__, "database": str(self.settings.v2_db), "database_exists": True, "database_ok": version is not None, "schema_version": version, "counts": db.table_counts()}
        except Exception as exc:
            return {"version": __version__, "database": str(self.settings.v2_db), "database_exists": True, "database_ok": False, "error": str(exc)}

    def sports_list(self, args: dict) -> dict:
        return {"sports": [{"name": profile.name, "slug": profile.slug} for profile in self.sports.all()], "open_ended": True, "note": "This registry is a starting knowledge set, not a coverage limit."}

    def sports_describe(self, args: dict) -> dict:
        profile = self.sports.resolve(str(args.get("sport", "")))
        return {"name": profile.name, "slug": profile.slug, "participant_shape": profile.participant_shape, "event_parts": list(profile.event_parts), "common_metrics": list(profile.common_metrics), "research_topics": list(profile.research_topics), "draw_possible": profile.draw_possible, "needs_discovery": profile.needs_discovery}

    def research_plan(self, args: dict) -> dict:
        plan = self.research_planner.plan(str(args.get("sport", "")), market_text=args.get("market"), home=args.get("home"), away=args.get("away"))
        return {"sport": plan.sport.name, "sport_slug": plan.sport.slug, "market": plan.market_text, "checklist": list(plan.checklist), "market_focus": list(plan.market_focus), "needs_source_discovery": plan.needs_source_discovery}

    def market_interpret(self, args: dict) -> dict:
        parsed = self.market_interpreter.interpret(str(args.get("text", "")), home=args.get("home"), away=args.get("away"))
        data = asdict(parsed)
        data["kind"] = parsed.kind.value
        data["line"] = str(parsed.line) if parsed.line is not None else None
        return data

    def market_arbitrage(self, args: dict) -> dict:
        now = datetime.now(timezone.utc)
        quotes = []
        for raw in args.get("quotes", []):
            rule_data = raw.get("rules") or {}
            captured = raw.get("captured_at")
            captured_at = datetime.fromisoformat(captured) if captured else now
            quotes.append(PriceQuote(event_key=str(raw["event_key"]), market_key=str(raw["market_key"]), selection_key=str(raw["selection_key"]), selection_label=str(raw.get("selection_label") or raw["selection_key"]), bookmaker=str(raw["bookmaker"]), odds=Decimal(str(raw["odds"])), captured_at=captured_at, rules=SettlementRules(period=str(rule_data.get("period", "full_event")), includes_overtime=rule_data.get("includes_overtime"), void_rule=str(rule_data.get("void_rule", "standard")), line_key=rule_data.get("line_key"))))
        result = self.arbitrage.find(quotes, [str(item) for item in args.get("expected_selections", [])], total_stake=args.get("total_stake"), max_age_seconds=int(args.get("max_age_seconds", 90)), now=now)
        return self._arb_to_dict(result)

    def bookmaker_resolve(self, args: dict) -> dict:
        bookmaker = self.bookmakers.resolve(str(args.get("name", "")))
        if bookmaker is None:
            return {"found": False, "name": args.get("name")}
        return {"found": True, "id": bookmaker.id, "name": bookmaker.name, "slug": bookmaker.slug, "capabilities": sorted(bookmaker.capabilities)}

    def ticket_split(self, args: dict) -> dict:
        ticket = self._ticket_from_args(args)
        children = self.ticket_workshop.split(ticket, int(args["slips"]))
        return {"original_odds": str(ticket.combined_odds), "slips": [self._ticket_to_dict(child) for child in children]}

    def ticket_trim(self, args: dict) -> dict:
        ticket = self._ticket_from_args(args)
        child = self.ticket_workshop.trim_to_target(ticket, Decimal(str(args["target_odds"])), min_legs=int(args.get("min_legs", 1)))
        return {"original_odds": str(ticket.combined_odds), "target_odds": str(Decimal(str(args["target_odds"]))), "ticket": self._ticket_to_dict(child)}

    def _ticket_from_args(self, args: dict) -> Ticket:
        bookmaker_id = None
        if args.get("bookmaker"):
            book = self.bookmakers.resolve(str(args["bookmaker"]))
            bookmaker_id = book.id if book else None
        ticket = Ticket(bookmaker_id=bookmaker_id, source_type=str(args.get("source_type", "instruction")), source_reference=args.get("source_reference"))
        for index, raw in enumerate(args.get("legs", []), start=1):
            parsed = self.market_interpreter.interpret(str(raw.get("market") or raw.get("pick") or ""), home=raw.get("home"), away=raw.get("away"))
            market = Market(kind=parsed.kind, label=parsed.plain_label, metric=parsed.metric, line=parsed.line, period=parsed.period)
            selection = Selection(market_id=market.id, label=parsed.plain_label, side=parsed.side)
            ticket.add_leg(TicketLeg(event_id=str(raw.get("event_id") or f"draft_event_{index}"), market=market, selection=selection, odds=Decimal(str(raw["odds"])), bookmaker_id=bookmaker_id, locked=bool(raw.get("locked", False)), note=raw.get("note")))
        if not ticket.legs:
            raise ValueError("Ticket needs at least one leg.")
        return ticket

    @staticmethod
    def _ticket_to_dict(ticket: Ticket) -> dict:
        return {"id": ticket.id, "parent_ticket_id": ticket.parent_ticket_id, "combined_odds": str(ticket.combined_odds), "legs": [{"id": leg.id, "event_id": leg.event_id, "pick": leg.selection.label, "odds": str(leg.odds), "locked": leg.locked} for leg in ticket.legs], "notes": ticket.notes}

    @staticmethod
    def _arb_to_dict(result) -> dict:
        return {"found": result.found, "reason": result.reason, "event_key": result.event_key, "market_key": result.market_key, "implied_total_pct": str(result.implied_total_pct) if result.implied_total_pct is not None else None, "profit_pct": str(result.profit_pct) if result.profit_pct is not None else None, "total_stake": str(result.total_stake) if result.total_stake is not None else None, "locked_return": str(result.locked_return) if result.locked_return is not None else None, "locked_profit": str(result.locked_profit) if result.locked_profit is not None else None, "prices": [{"selection": quote.selection_label, "bookmaker": quote.bookmaker, "odds": str(quote.odds), "period": quote.rules.period, "includes_overtime": quote.rules.includes_overtime, "void_rule": quote.rules.void_rule, "line_key": quote.rules.line_key} for quote in result.quotes], "stake_split": [{"selection": row.selection_label, "bookmaker": row.bookmaker, "odds": str(row.odds), "stake": str(row.stake), "return": str(row.expected_return)} for row in result.allocations]}
