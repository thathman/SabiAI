from __future__ import annotations
from dataclasses import asdict
from decimal import Decimal
from sabiai import __version__
from sabiai.bookmakers import default_bookmakers
from sabiai.config import Settings
from sabiai.domain.models import Market, Selection, Ticket, TicketLeg
from sabiai.markets import MarketInterpreter
from sabiai.storage import SabiDatabase
from sabiai.tickets import TicketWorkshop

class SabiToolGateway:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings.from_env()
        self.market_interpreter = MarketInterpreter()
        self.bookmakers = default_bookmakers()
        self.ticket_workshop = TicketWorkshop()

    def dispatch(self, tool: str, args: dict | None = None) -> dict:
        handlers = {"system.health": self.system_health,"market.interpret": self.market_interpret,"bookmaker.resolve": self.bookmaker_resolve,"ticket.split": self.ticket_split,"ticket.trim": self.ticket_trim}
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
            with db.connect() as conn:
                row = conn.execute("SELECT value FROM v2_meta WHERE key='schema_version'").fetchone()
                version = row[0] if row else None
            return {"version": __version__, "database": str(self.settings.v2_db), "database_exists": True, "database_ok": version is not None, "schema_version": version, "counts": db.table_counts()}
        except Exception as exc:
            return {"version": __version__, "database": str(self.settings.v2_db), "database_exists": True, "database_ok": False, "error": str(exc)}

    def market_interpret(self, args: dict) -> dict:
        parsed = self.market_interpreter.interpret(str(args.get("text", "")), home=args.get("home"), away=args.get("away"))
        data = asdict(parsed)
        data["kind"] = parsed.kind.value
        data["line"] = str(parsed.line) if parsed.line is not None else None
        return data

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
