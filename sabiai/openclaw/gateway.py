from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from decimal import Decimal

from sabiai import __version__
from sabiai.bookmakers import default_bookmakers, legacy_command_adapters
from sabiai.config import Settings
from sabiai.domain.models import Market, Selection, Ticket, TicketLeg
from sabiai.markets import MarketInterpreter
from sabiai.odds import ArbitrageEngine, PriceQuote, SettlementRules
from sabiai.research import Evidence, EvidenceStore
from sabiai.sports import ResearchPlanner, default_sports
from sabiai.storage import BankrollLedger, HistoryService, SabiDatabase
from sabiai.tickets import TicketNormalizer, TicketWorkshop


class SabiToolGateway:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings.from_env()
        self.market_interpreter = MarketInterpreter()
        self.bookmakers = default_bookmakers()
        self.bookmaker_adapters = legacy_command_adapters()
        self.sports = default_sports()
        self.research_planner = ResearchPlanner(self.sports)
        self.ticket_normalizer = TicketNormalizer(self.bookmakers, self.market_interpreter)
        self.ticket_workshop = TicketWorkshop()
        self.arbitrage = ArbitrageEngine()

    def dispatch(self, tool: str, args: dict | None = None) -> dict:
        handlers = {
            "system.health": self.system_health,
            "system.initialize": self.system_initialize,
            "sports.list": self.sports_list,
            "sports.describe": self.sports_describe,
            "research.plan": self.research_plan,
            "research.evidence.save": self.research_evidence_save,
            "research.evidence.list": self.research_evidence_list,
            "market.interpret": self.market_interpret,
            "market.arbitrage": self.market_arbitrage,
            "bookmaker.resolve": self.bookmaker_resolve,
            "bookmaker.capabilities": self.bookmaker_capabilities,
            "ticket.normalize": self.ticket_normalize,
            "ticket.split": self.ticket_split,
            "ticket.split_by_size": self.ticket_split_by_size,
            "ticket.trim": self.ticket_trim,
            "ticket.remove": self.ticket_remove,
            "ticket.keep": self.ticket_keep,
            "ticket.change_market": self.ticket_change_market,
            "ticket.replace": self.ticket_replace,
            "record.bankroll": self.record_bankroll,
            "history.summary": self.history_summary,
            "history.by_sport": self.history_by_sport,
            "history.by_market": self.history_by_market,
            "history.by_bookmaker": self.history_by_bookmaker,
            "history.bankroll": self.history_bankroll,
        }
        handler = handlers.get(tool)
        if handler is None:
            return {"ok": False, "error": f"Unknown Sabi V2 tool: {tool}"}
        try:
            return {"ok": True, "tool": tool, "data": handler(args or {})}
        except Exception as exc:
            return {"ok": False, "tool": tool, "error": str(exc)}

    def _db(self, *, initialize: bool = False) -> SabiDatabase:
        db = SabiDatabase(self.settings.v2_db)
        if initialize:
            db.initialize()
        return db

    def system_initialize(self, args: dict) -> dict:
        db = self._db(initialize=True)
        return {
            "database": str(self.settings.v2_db),
            "schema_version": db.schema_version(),
            "counts": db.table_counts(),
        }

    def system_health(self, args: dict) -> dict:
        db = self._db()
        exists = self.settings.v2_db.exists()
        if not exists:
            return {
                "version": __version__,
                "database": str(self.settings.v2_db),
                "database_exists": False,
                "database_ok": False,
            }
        try:
            version = db.schema_version()
            return {
                "version": __version__,
                "database": str(self.settings.v2_db),
                "database_exists": True,
                "database_ok": version is not None,
                "schema_version": version,
                "counts": db.table_counts(),
            }
        except Exception as exc:
            return {
                "version": __version__,
                "database": str(self.settings.v2_db),
                "database_exists": True,
                "database_ok": False,
                "error": str(exc),
            }

    def sports_list(self, args: dict) -> dict:
        return {
            "sports": [
                {"name": profile.name, "slug": profile.slug}
                for profile in self.sports.all()
            ],
            "open_ended": True,
            "note": "This registry is a starting knowledge set, not a coverage limit.",
        }

    def sports_describe(self, args: dict) -> dict:
        profile = self.sports.resolve(str(args.get("sport", "")))
        return {
            "name": profile.name,
            "slug": profile.slug,
            "participant_shape": profile.participant_shape,
            "event_parts": list(profile.event_parts),
            "common_metrics": list(profile.common_metrics),
            "research_topics": list(profile.research_topics),
            "draw_possible": profile.draw_possible,
            "needs_discovery": profile.needs_discovery,
        }

    def research_plan(self, args: dict) -> dict:
        plan = self.research_planner.plan(
            str(args.get("sport", "")),
            market_text=args.get("market"),
            home=args.get("home"),
            away=args.get("away"),
        )
        return {
            "sport": plan.sport.name,
            "sport_slug": plan.sport.slug,
            "market": plan.market_text,
            "checklist": list(plan.checklist),
            "market_focus": list(plan.market_focus),
            "needs_source_discovery": plan.needs_source_discovery,
        }

    def research_evidence_save(self, args: dict) -> dict:
        db = self._db(initialize=True)
        store = EvidenceStore(db)
        evidence = Evidence(
            evidence_type=str(args["evidence_type"]),
            summary=str(args["summary"]),
            event_id=args.get("event_id"),
            sport_id=args.get("sport_id"),
            subject=args.get("subject"),
            source_name=args.get("source_name"),
            source_url=args.get("source_url"),
            observed_at=args.get("observed_at"),
            freshness_seconds=int(args["freshness_seconds"])
            if args.get("freshness_seconds") is not None
            else None,
            reliability=args.get("reliability"),
            raw=args.get("raw"),
            id=args.get("id"),
        )
        return {"id": store.save(evidence)}

    def research_evidence_list(self, args: dict) -> dict:
        db = self._db(initialize=True)
        event_id = str(args["event_id"])
        store = EvidenceStore(db)
        return {
            "event_id": event_id,
            "evidence": store.for_event(
                event_id, evidence_type=args.get("evidence_type")
            ),
        }

    def market_interpret(self, args: dict) -> dict:
        parsed = self.market_interpreter.interpret(
            str(args.get("text", "")),
            home=args.get("home"),
            away=args.get("away"),
        )
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
            quotes.append(
                PriceQuote(
                    event_key=str(raw["event_key"]),
                    market_key=str(raw["market_key"]),
                    selection_key=str(raw["selection_key"]),
                    selection_label=str(
                        raw.get("selection_label") or raw["selection_key"]
                    ),
                    bookmaker=str(raw["bookmaker"]),
                    odds=Decimal(str(raw["odds"])),
                    captured_at=captured_at,
                    rules=SettlementRules(
                        period=str(rule_data.get("period", "full_event")),
                        includes_overtime=rule_data.get("includes_overtime"),
                        void_rule=str(rule_data.get("void_rule", "standard")),
                        line_key=rule_data.get("line_key"),
                    ),
                )
            )
        result = self.arbitrage.find(
            quotes,
            [str(item) for item in args.get("expected_selections", [])],
            total_stake=args.get("total_stake"),
            max_age_seconds=int(args.get("max_age_seconds", 90)),
            now=now,
        )
        return self._arb_to_dict(result)

    def bookmaker_resolve(self, args: dict) -> dict:
        bookmaker = self.bookmakers.resolve(str(args.get("name", "")))
        if bookmaker is None:
            return {"found": False, "name": args.get("name")}
        adapter = self.bookmaker_adapters.get(bookmaker.slug)
        proven = sorted(cap.value for cap in adapter.capabilities()) if adapter else []
        return {
            "found": True,
            "id": bookmaker.id,
            "name": bookmaker.name,
            "slug": bookmaker.slug,
            "proven_capabilities": proven,
        }

    def bookmaker_capabilities(self, args: dict) -> dict:
        name = args.get("name")
        if name:
            bookmaker = self.bookmakers.resolve(str(name))
            if bookmaker is None:
                return {"found": False, "name": name}
            adapter = self.bookmaker_adapters.get(bookmaker.slug)
            return {
                "found": True,
                "bookmaker": bookmaker.name,
                "slug": bookmaker.slug,
                "adapter": asdict(adapter.status()) if adapter else None,
            }
        return {
            "bookmakers": [asdict(status) for status in self.bookmaker_adapters.statuses()]
        }

    def ticket_normalize(self, args: dict) -> dict:
        result = self.ticket_normalizer.normalize(
            args.get("legs", []),
            bookmaker=args.get("bookmaker"),
            source_type=str(args.get("source_type", "instruction")),
            source_reference=args.get("source_reference"),
        )
        return {
            "usable": result.usable,
            "ticket": self._ticket_to_dict(result.ticket),
            "issues": [asdict(issue) for issue in result.issues],
        }

    def ticket_split(self, args: dict) -> dict:
        ticket = self._ticket_from_args(args)
        children = self.ticket_workshop.split(ticket, int(args["slips"]))
        return {
            "original_odds": str(ticket.combined_odds),
            "slips": [self._ticket_to_dict(child) for child in children],
        }

    def ticket_split_by_size(self, args: dict) -> dict:
        ticket = self._ticket_from_args(args)
        children = self.ticket_workshop.split_by_size(
            ticket, int(args["games_per_slip"])
        )
        return {
            "original_odds": str(ticket.combined_odds),
            "slips": [self._ticket_to_dict(child) for child in children],
        }

    def ticket_trim(self, args: dict) -> dict:
        ticket = self._ticket_from_args(args)
        child = self.ticket_workshop.trim_to_target(
            ticket,
            Decimal(str(args["target_odds"])),
            min_legs=int(args.get("min_legs", 1)),
        )
        return {
            "original_odds": str(ticket.combined_odds),
            "target_odds": str(Decimal(str(args["target_odds"]))),
            "ticket": self._ticket_to_dict(child),
        }

    def ticket_remove(self, args: dict) -> dict:
        ticket = self._ticket_from_args(args)
        leg_ids = self._target_leg_ids(ticket, args)
        child = self.ticket_workshop.remove(ticket, leg_ids)
        return {
            "original_odds": str(ticket.combined_odds),
            "ticket": self._ticket_to_dict(child),
        }

    def ticket_keep(self, args: dict) -> dict:
        ticket = self._ticket_from_args(args)
        leg_ids = self._target_leg_ids(ticket, args)
        child = self.ticket_workshop.keep_only(ticket, leg_ids)
        return {
            "original_odds": str(ticket.combined_odds),
            "ticket": self._ticket_to_dict(child),
        }

    def ticket_change_market(self, args: dict) -> dict:
        ticket = self._ticket_from_args(args)
        target = self._find_leg(ticket, args.get("leg_id"), args.get("event"))
        if target is None:
            raise ValueError("The requested game was not found on the ticket.")
        text = str(args.get("new_market") or args.get("market") or "")
        parsed = self.market_interpreter.interpret(
            text,
            home=args.get("home"),
            away=args.get("away"),
        )
        if not parsed.understood:
            raise ValueError(parsed.reason or "The new market could not be understood.")
        market = Market(
            kind=parsed.kind,
            label=parsed.plain_label,
            metric=parsed.metric,
            line=parsed.line,
            period=parsed.period,
        )
        selection = Selection(
            market_id=market.id,
            label=parsed.plain_label,
            side=parsed.side,
        )
        child = self.ticket_workshop.change_market(
            ticket,
            target.id,
            market,
            selection,
            odds=args.get("new_odds"),
            note=args.get("note"),
        )
        return {
            "original_odds": str(ticket.combined_odds),
            "ticket": self._ticket_to_dict(child),
        }

    def ticket_replace(self, args: dict) -> dict:
        ticket = self._ticket_from_args(args)
        target = self._find_leg(ticket, args.get("leg_id"), args.get("event"))
        if target is None:
            raise ValueError("The requested game was not found on the ticket.")
        replacement_raw = args.get("replacement")
        if not isinstance(replacement_raw, dict):
            raise ValueError("replacement must be one ticket leg object.")
        normalized = self.ticket_normalizer.normalize(
            [replacement_raw],
            bookmaker=args.get("bookmaker"),
            source_type="replacement",
        )
        errors = [issue.message for issue in normalized.issues if issue.level == "error"]
        if errors or not normalized.ticket.legs:
            raise ValueError("; ".join(errors) or "Replacement leg is not usable.")
        child = self.ticket_workshop.replace_leg(
            ticket, target.id, normalized.ticket.legs[0]
        )
        return {
            "original_odds": str(ticket.combined_odds),
            "ticket": self._ticket_to_dict(child),
            "issues": [asdict(issue) for issue in normalized.issues],
        }

    def record_bankroll(self, args: dict) -> dict:
        db = self._db(initialize=True)
        ledger = BankrollLedger(db)
        entry = ledger.record(
            str(args["kind"]),
            args["amount"],
            pick_id=args.get("pick_id"),
            ticket_id=args.get("ticket_id"),
            legacy_bet_id=args.get("legacy_bet_id"),
            note=args.get("note"),
            occurred_at=args.get("occurred_at"),
        )
        return self._ledger_to_dict(entry)

    def history_summary(self, args: dict) -> dict:
        return HistoryService(self._db(initialize=True)).summary()

    def history_by_sport(self, args: dict) -> dict:
        return {"rows": HistoryService(self._db(initialize=True)).by_sport()}

    def history_by_market(self, args: dict) -> dict:
        return {"rows": HistoryService(self._db(initialize=True)).by_market()}

    def history_by_bookmaker(self, args: dict) -> dict:
        return {"rows": HistoryService(self._db(initialize=True)).by_bookmaker()}

    def history_bankroll(self, args: dict) -> dict:
        ledger = BankrollLedger(self._db(initialize=True))
        limit = int(args.get("limit", 100))
        return {
            "balance": str(ledger.current_balance()),
            "entries": [self._ledger_to_dict(entry) for entry in ledger.history(limit)],
        }

    def _ticket_from_args(self, args: dict) -> Ticket:
        normalized = self.ticket_normalizer.normalize(
            args.get("legs", []),
            bookmaker=args.get("bookmaker"),
            source_type=str(args.get("source_type", "instruction")),
            source_reference=args.get("source_reference"),
        )
        errors = [issue.message for issue in normalized.issues if issue.level == "error"]
        if errors or not normalized.ticket.legs:
            raise ValueError("; ".join(errors) or "Ticket needs at least one usable leg.")
        return normalized.ticket

    @staticmethod
    def _find_leg(ticket: Ticket, leg_id, event_label) -> TicketLeg | None:
        if leg_id:
            target = str(leg_id)
            return next((leg for leg in ticket.legs if leg.id == target), None)
        if event_label:
            target = str(event_label).strip().casefold()
            return next(
                (
                    leg
                    for leg in ticket.legs
                    if (leg.event_label or "").strip().casefold() == target
                ),
                None,
            )
        return None

    def _target_leg_ids(self, ticket: Ticket, args: dict) -> set[str]:
        ids = {str(item) for item in args.get("leg_ids", [])}
        events = {str(item).strip().casefold() for item in args.get("events", [])}
        for leg in ticket.legs:
            if (leg.event_label or "").strip().casefold() in events:
                ids.add(leg.id)
        if not ids:
            raise ValueError("Specify leg_ids or event names.")
        return ids

    @staticmethod
    def _ticket_to_dict(ticket: Ticket) -> dict:
        return {
            "id": ticket.id,
            "parent_ticket_id": ticket.parent_ticket_id,
            "source_type": ticket.source_type,
            "source_reference": ticket.source_reference,
            "combined_odds": str(ticket.combined_odds),
            "legs": [
                {
                    "id": leg.id,
                    "event_id": leg.event_id,
                    "event": leg.event_label,
                    "pick": leg.selection.label,
                    "odds": str(leg.odds),
                    "locked": leg.locked,
                }
                for leg in ticket.legs
            ],
            "notes": ticket.notes,
        }

    @staticmethod
    def _ledger_to_dict(entry) -> dict:
        return {
            "id": entry.id,
            "occurred_at": entry.occurred_at,
            "kind": entry.kind,
            "amount": str(entry.amount),
            "balance_after": str(entry.balance_after)
            if entry.balance_after is not None
            else None,
            "pick_id": entry.pick_id,
            "ticket_id": entry.ticket_id,
            "legacy_bet_id": entry.legacy_bet_id,
            "note": entry.note,
        }

    @staticmethod
    def _arb_to_dict(result) -> dict:
        return {
            "found": result.found,
            "reason": result.reason,
            "event_key": result.event_key,
            "market_key": result.market_key,
            "implied_total_pct": str(result.implied_total_pct)
            if result.implied_total_pct is not None
            else None,
            "profit_pct": str(result.profit_pct)
            if result.profit_pct is not None
            else None,
            "total_stake": str(result.total_stake)
            if result.total_stake is not None
            else None,
            "locked_return": str(result.locked_return)
            if result.locked_return is not None
            else None,
            "locked_profit": str(result.locked_profit)
            if result.locked_profit is not None
            else None,
            "prices": [
                {
                    "selection": quote.selection_label,
                    "bookmaker": quote.bookmaker,
                    "odds": str(quote.odds),
                    "period": quote.rules.period,
                    "includes_overtime": quote.rules.includes_overtime,
                    "void_rule": quote.rules.void_rule,
                    "line_key": quote.rules.line_key,
                }
                for quote in result.quotes
            ],
            "stake_split": [
                {
                    "selection": row.selection_label,
                    "bookmaker": row.bookmaker,
                    "odds": str(row.odds),
                    "stake": str(row.stake),
                    "return": str(row.expected_return),
                }
                for row in result.allocations
            ],
        }
