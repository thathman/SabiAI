from __future__ import annotations

from sabiai.storage import (
    AdvancedAnalytics,
    BankrollLedger,
    DashboardReadService,
    HistoryService,
    PickRecordService,
    PerformanceAnalytics,
)

from .serializers import ledger_to_dict


class RecordTools:
    def __init__(self, app):
        self.app = app

    def handlers(self) -> dict:
        return {
            "record.bankroll": self.record_bankroll,
            "record.pick": self.record_pick,
            "history.picks": self.picks,
            "history.summary": self.summary,
            "history.by_sport": self.by_sport,
            "history.by_market": self.by_market,
            "history.by_bookmaker": self.by_bookmaker,
            "history.bankroll": self.bankroll,
            "history.streaks": self.streaks,
            "history.profit_loss": self.profit_loss,
            "history.by_strategy": self.by_strategy,
            "history.by_competition": self.by_competition,
            "history.by_odds_band": self.by_odds_band,
            "history.by_ticket_size": self.by_ticket_size,
            "history.by_combined_odds": self.by_combined_odds,
            "history.ticket_sources": self.ticket_sources,
            "history.ticket_killers": self.ticket_killers,
            "history.daily_outcomes": self.daily_outcomes,
            "history.bankroll_series": self.bankroll_series,
            "history.ticket_versions": self.ticket_versions,
            "history.bookmaker_prices": self.bookmaker_prices,
            "history.price_disagreements": self.price_disagreements,
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

    def record_pick(self, args: dict) -> dict:
        """Record a Sabi Boy or Hendrix pick in the canonical V2 ledger."""
        return PickRecordService(self.app._db(initialize=True)).record(args)

    def _history(self) -> HistoryService:
        return HistoryService(self.app._db(initialize=True))

    def _analytics(self) -> PerformanceAnalytics:
        return PerformanceAnalytics(self.app._db(initialize=True))

    def _advanced(self) -> AdvancedAnalytics:
        return AdvancedAnalytics(self.app._db(initialize=True))

    def summary(self, args: dict) -> dict:
        return self._history().summary(owner=args.get("owner", "sabi_boy"), record_kind=args.get("record_kind", "pick"))

    def picks(self, args: dict) -> dict:
        """Return the canonical pick ledger rows for Sabi Boy conversation context."""
        reads = DashboardReadService(self.app._db(initialize=True))
        return {
            "rows": reads.picks(
                limit=int(args.get("limit", 100)),
                outcome=args.get("outcome"),
                sport=args.get("sport"),
                strategy=args.get("strategy"),
                owner=args.get("owner", "sabi_boy"),
                record_kind=args.get("record_kind", "pick"),
            )
        }

    def by_sport(self, args: dict) -> dict:
        return {"rows": self._history().by_sport(owner=args.get("owner", "sabi_boy"), record_kind=args.get("record_kind", "pick"))}

    def by_market(self, args: dict) -> dict:
        return {"rows": self._history().by_market(owner=args.get("owner", "sabi_boy"), record_kind=args.get("record_kind", "pick"))}

    def by_bookmaker(self, args: dict) -> dict:
        return {"rows": self._history().by_bookmaker(owner=args.get("owner", "sabi_boy"), record_kind=args.get("record_kind", "pick"))}

    def bankroll(self, args: dict) -> dict:
        ledger = BankrollLedger(self.app._db(initialize=True))
        limit = int(args.get("limit", 100))
        return {
            "balance": str(ledger.current_balance()),
            "entries": [ledger_to_dict(entry) for entry in ledger.history(limit)],
        }

    def streaks(self, args: dict) -> dict:
        return self._analytics().streaks(owner=args.get("owner", "sabi_boy"), record_kind=args.get("record_kind", "pick"))

    def profit_loss(self, args: dict) -> dict:
        return self._analytics().profit_loss()

    def by_strategy(self, args: dict) -> dict:
        return {"rows": self._analytics().by_strategy(owner=args.get("owner", "sabi_boy"), record_kind=args.get("record_kind", "pick"))}

    def by_competition(self, args: dict) -> dict:
        return {"rows": self._analytics().by_competition(owner=args.get("owner", "sabi_boy"), record_kind=args.get("record_kind", "pick"))}

    def by_odds_band(self, args: dict) -> dict:
        return {"rows": self._analytics().by_odds_band(owner=args.get("owner", "sabi_boy"), record_kind=args.get("record_kind", "pick"))}

    def by_ticket_size(self, args: dict) -> dict:
        return {"rows": self._analytics().by_ticket_size()}

    def by_combined_odds(self, args: dict) -> dict:
        return {"rows": self._analytics().by_combined_odds_band()}

    def ticket_sources(self, args: dict) -> dict:
        return {"rows": self._analytics().ticket_sources()}

    def ticket_killers(self, args: dict) -> dict:
        return {"rows": self._analytics().ticket_killers(int(args.get("limit", 25)))}

    def daily_outcomes(self, args: dict) -> dict:
        return {"rows": self._analytics().daily_outcomes(int(args.get("days", 90)), owner=args.get("owner", "sabi_boy"), record_kind=args.get("record_kind", "pick"))}

    def bankroll_series(self, args: dict) -> dict:
        return {"rows": self._analytics().bankroll_series(int(args.get("limit", 365)))}

    def ticket_versions(self, args: dict) -> dict:
        return self._advanced().ticket_version_outcomes(int(args.get("limit", 250)))

    def bookmaker_prices(self, args: dict) -> dict:
        return {"rows": self._advanced().bookmaker_price_history(int(args.get("limit", 100)))}

    def price_disagreements(self, args: dict) -> dict:
        return {"rows": self._advanced().latest_price_disagreements(int(args.get("limit", 50)))}
