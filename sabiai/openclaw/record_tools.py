from __future__ import annotations

from sabiai.storage import BankrollLedger, HistoryService

from .serializers import ledger_to_dict


class RecordTools:
    def __init__(self, app):
        self.app = app

    def handlers(self) -> dict:
        return {
            "record.bankroll": self.record_bankroll,
            "history.summary": self.summary,
            "history.by_sport": self.by_sport,
            "history.by_market": self.by_market,
            "history.by_bookmaker": self.by_bookmaker,
            "history.bankroll": self.bankroll,
        }

    def record_bankroll(self, args: dict) -> dict:
        ledger = BankrollLedger(self.app._db(initialize=True))
        entry = ledger.record(
            str(args["kind"]),
            args["amount"],
            pick_id=args.get("pick_id"),
            ticket_id=args.get("ticket_id"),
            legacy_bet_id=args.get("legacy_bet_id"),
            note=args.get("note"),
            occurred_at=args.get("occurred_at"),
        )
        return ledger_to_dict(entry)

    def summary(self, args: dict) -> dict:
        return HistoryService(self.app._db(initialize=True)).summary()

    def by_sport(self, args: dict) -> dict:
        return {"rows": HistoryService(self.app._db(initialize=True)).by_sport()}

    def by_market(self, args: dict) -> dict:
        return {"rows": HistoryService(self.app._db(initialize=True)).by_market()}

    def by_bookmaker(self, args: dict) -> dict:
        return {"rows": HistoryService(self.app._db(initialize=True)).by_bookmaker()}

    def bankroll(self, args: dict) -> dict:
        ledger = BankrollLedger(self.app._db(initialize=True))
        limit = int(args.get("limit", 100))
        return {
            "balance": str(ledger.current_balance()),
            "entries": [ledger_to_dict(entry) for entry in ledger.history(limit)],
        }
