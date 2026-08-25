from __future__ import annotations

from dataclasses import asdict
from decimal import Decimal

from sabiai.domain.models import Market, Selection

from .helpers import bookmaker_slug, find_leg, target_leg_ids, ticket_from_args
from .serializers import draft_to_dict, ticket_to_dict


class TicketTools:
    def __init__(self, app):
        self.app = app

    def handlers(self) -> dict:
        return {
            "ticket.normalize": self.normalize,
            "ticket.from_text": self.from_text,
            "ticket.draft.save": self.draft_save,
            "ticket.draft.revise": self.draft_revise,
            "ticket.draft.get": self.draft_get,
            "ticket.draft.recent": self.draft_recent,
            "ticket.draft.lineage": self.draft_lineage,
            "ticket.split": self.split,
            "ticket.split_by_size": self.split_by_size,
            "ticket.trim": self.trim,
            "ticket.remove": self.remove,
            "ticket.keep": self.keep,
            "ticket.change_market": self.change_market,
            "ticket.replace": self.replace,
        }

    def normalize(self, args: dict) -> dict:
        result = self.app.ticket_normalizer.normalize(
            args.get("legs", []),
            bookmaker=args.get("bookmaker"),
            source_type=str(args.get("source_type", "instruction")),
            source_reference=args.get("source_reference"),
        )
        return {
            "usable": result.usable,
            "ticket": ticket_to_dict(result.ticket),
            "issues": [asdict(issue) for issue in result.issues],
        }

    def from_text(self, args: dict) -> dict:
        extraction = self.app.ticket_text_importer.extract(str(args.get("text", "")))
        extracted = [leg.as_dict() for leg in extraction.legs]
        if args.get("sport"):
            for leg in extracted:
                leg.setdefault("sport", args.get("sport"))
        result = self.app.ticket_normalizer.normalize(
            extracted,
            bookmaker=args.get("bookmaker"),
            source_type=str(args.get("source_type", "copied_text")),
            source_reference=args.get("source_reference"),
        )
        return {
            "extraction_complete": extraction.complete,
            "unparsed_lines": extraction.unparsed_lines,
            "usable": result.usable,
            "ticket": ticket_to_dict(result.ticket),
            "issues": [asdict(issue) for issue in result.issues],
        }

    def draft_save(self, args: dict) -> dict:
        payload = args.get("payload")
        issues = args.get("issues")
        if payload is None:
            normalized = self.app.ticket_normalizer.normalize(
                args.get("legs", []),
                bookmaker=args.get("bookmaker"),
                source_type=str(args.get("source_type", "instruction")),
                source_reference=args.get("source_reference"),
            )
            payload = ticket_to_dict(normalized.ticket)
            issues = [asdict(issue) for issue in normalized.issues]
        if not isinstance(payload, dict):
            raise ValueError("payload must be one ticket object.")

        draft = self.app._draft_store().create(
            payload,
            source_type=str(args.get("source_type", "instruction")),
            source_reference=args.get("source_reference"),
            source_bookmaker_slug=bookmaker_slug(self.app, args.get("bookmaker")),
            target_bookmaker_slug=bookmaker_slug(self.app, args.get("target_bookmaker")),
            status=str(args.get("status", "draft")),
            issues=list(issues or []),
            parent_draft_id=args.get("parent_draft_id"),
        )
        return draft_to_dict(draft)

    def draft_revise(self, args: dict) -> dict:
        draft_id = str(args["draft_id"])
        payload = args.get("payload")
        issues = args.get("issues")
        if payload is None:
            normalized = self.app.ticket_normalizer.normalize(
                args.get("legs", []),
                bookmaker=args.get("bookmaker"),
                source_type="revision",
                source_reference=args.get("source_reference"),
            )
            payload = ticket_to_dict(normalized.ticket)
            issues = [asdict(issue) for issue in normalized.issues]
        if not isinstance(payload, dict):
            raise ValueError("payload must be one ticket object.")
        draft = self.app._draft_store().revise(
            draft_id,
            payload,
            issues=list(issues or []),
            status=str(args.get("status", "draft")),
            target_bookmaker_slug=bookmaker_slug(self.app, args.get("target_bookmaker")),
        )
        return draft_to_dict(draft)

    def draft_get(self, args: dict) -> dict:
        draft = self.app._draft_store().get(str(args["draft_id"]))
        return {
            "found": draft is not None,
            "draft": draft_to_dict(draft) if draft else None,
        }

    def draft_recent(self, args: dict) -> dict:
        drafts = self.app._draft_store().recent(int(args.get("limit", 25)))
        return {"drafts": [draft_to_dict(draft) for draft in drafts]}

    def draft_lineage(self, args: dict) -> dict:
        drafts = self.app._draft_store().lineage(str(args["draft_id"]))
        return {"lineage": [draft_to_dict(draft) for draft in drafts]}

    def split(self, args: dict) -> dict:
        ticket = ticket_from_args(self.app, args)
        children = self.app.ticket_workshop.split(ticket, int(args["slips"]))
        return {
            "original_odds": str(ticket.combined_odds),
            "slips": [ticket_to_dict(child) for child in children],
        }

    def split_by_size(self, args: dict) -> dict:
        ticket = ticket_from_args(self.app, args)
        children = self.app.ticket_workshop.split_by_size(
            ticket, int(args["games_per_slip"])
        )
        return {
            "original_odds": str(ticket.combined_odds),
            "slips": [ticket_to_dict(child) for child in children],
        }

    def trim(self, args: dict) -> dict:
        ticket = ticket_from_args(self.app, args)
        child = self.app.ticket_workshop.trim_to_target(
            ticket,
            Decimal(str(args["target_odds"])),
            min_legs=int(args.get("min_legs", 1)),
        )
        return {
            "original_odds": str(ticket.combined_odds),
            "target_odds": str(Decimal(str(args["target_odds"]))),
            "ticket": ticket_to_dict(child),
        }

    def remove(self, args: dict) -> dict:
        ticket = ticket_from_args(self.app, args)
        child = self.app.ticket_workshop.remove(ticket, target_leg_ids(ticket, args))
        return {
            "original_odds": str(ticket.combined_odds),
            "ticket": ticket_to_dict(child),
        }

    def keep(self, args: dict) -> dict:
        ticket = ticket_from_args(self.app, args)
        child = self.app.ticket_workshop.keep_only(ticket, target_leg_ids(ticket, args))
        return {
            "original_odds": str(ticket.combined_odds),
            "ticket": ticket_to_dict(child),
        }

    def change_market(self, args: dict) -> dict:
        ticket = ticket_from_args(self.app, args)
        target = find_leg(ticket, args.get("leg_id"), args.get("event"))
        if target is None:
            raise ValueError("The requested game was not found on the ticket.")
        text = str(args.get("new_market") or args.get("market") or "")
        parsed = self.app.market_interpreter.interpret(
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
        child = self.app.ticket_workshop.change_market(
            ticket,
            target.id,
            market,
            selection,
            odds=args.get("new_odds"),
            note=args.get("note"),
        )
        return {
            "original_odds": str(ticket.combined_odds),
            "ticket": ticket_to_dict(child),
        }

    def replace(self, args: dict) -> dict:
        ticket = ticket_from_args(self.app, args)
        target = find_leg(ticket, args.get("leg_id"), args.get("event"))
        if target is None:
            raise ValueError("The requested game was not found on the ticket.")
        replacement_raw = args.get("replacement")
        if not isinstance(replacement_raw, dict):
            raise ValueError("replacement must be one ticket leg object.")
        normalized = self.app.ticket_normalizer.normalize(
            [replacement_raw],
            bookmaker=args.get("bookmaker"),
            source_type="replacement",
        )
        errors = [issue.message for issue in normalized.issues if issue.level == "error"]
        if errors or not normalized.ticket.legs:
            raise ValueError("; ".join(errors) or "Replacement leg is not usable.")
        child = self.app.ticket_workshop.replace_leg(
            ticket,
            target.id,
            normalized.ticket.legs[0],
        )
        return {
            "original_odds": str(ticket.combined_odds),
            "ticket": ticket_to_dict(child),
            "issues": [asdict(issue) for issue in normalized.issues],
        }
