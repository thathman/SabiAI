from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from decimal import Decimal

from sabiai.odds import PriceQuote, SettlementRules

from .serializers import arbitrage_to_dict


class MarketTools:
    def __init__(self, app):
        self.app = app

    def handlers(self) -> dict:
        return {
            "market.interpret": self.interpret,
            "market.arbitrage": self.arbitrage,
        }

    def interpret(self, args: dict) -> dict:
        parsed = self.app.market_interpreter.interpret(
            str(args.get("text", "")),
            home=args.get("home"),
            away=args.get("away"),
        )
        data = asdict(parsed)
        data["kind"] = parsed.kind.value
        data["line"] = str(parsed.line) if parsed.line is not None else None
        return data

    def arbitrage(self, args: dict) -> dict:
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
                    selection_label=str(raw.get("selection_label") or raw["selection_key"]),
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
        result = self.app.arbitrage.find(
            quotes,
            [str(item) for item in args.get("expected_selections", [])],
            total_stake=args.get("total_stake"),
            max_age_seconds=int(args.get("max_age_seconds", 90)),
            now=now,
        )
        return arbitrage_to_dict(result)
