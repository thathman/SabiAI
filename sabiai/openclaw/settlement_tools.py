from __future__ import annotations

from dataclasses import asdict

from sabiai.settlement import SettlementService


class SettlementTools:
    def __init__(self, app):
        self.app = app

    def handlers(self) -> dict:
        return {
            "record.settle_pick": self.settle_pick,
            "record.settle_ticket_leg": self.settle_ticket_leg,
            "record.refresh_ticket": self.refresh_ticket,
            "record.ticket_payout": self.ticket_payout,
            "record.void_event": self.void_event,
            "history.settlement_backlog": self.backlog,
        }

    def _service(self) -> SettlementService:
        return SettlementService(self.app._db(initialize=True))

    def settle_pick(self, args: dict) -> dict:
        result = self._service().settle_pick(
            str(args["pick_id"]),
            args["outcome"],
            source=str(args.get("source") or "openclaw"),
            reason=args.get("reason"),
            correction=bool(args.get("correction", False)),
            payout=args.get("payout"),
            record_payout=bool(args.get("record_payout", False)),
        )
        return asdict(result)

    def settle_ticket_leg(self, args: dict) -> dict:
        leg, ticket = self._service().settle_ticket_leg(
            str(args["leg_id"]),
            args["outcome"],
            source=str(args.get("source") or "openclaw"),
            reason=args.get("reason"),
            correction=bool(args.get("correction", False)),
        )
        return {"leg": asdict(leg), "ticket": asdict(ticket)}

    def refresh_ticket(self, args: dict) -> dict:
        return asdict(
            self._service().refresh_ticket(
                str(args["ticket_id"]),
                source=str(args.get("source") or "openclaw"),
                reason=args.get("reason"),
            )
        )

    def ticket_payout(self, args: dict) -> dict:
        return self._service().record_ticket_payout(
            str(args["ticket_id"]),
            args["amount"],
            source=str(args.get("source") or "openclaw"),
            reason=args.get("reason"),
        )

    def void_event(self, args: dict) -> dict:
        return self._service().void_event(
            str(args["event_id"]),
            source=str(args.get("source") or "openclaw"),
            reason=str(args.get("reason") or ""),
        )

    def backlog(self, args: dict) -> dict:
        return self._service().backlog(
            older_than_hours=int(args.get("older_than_hours", 24))
        )
