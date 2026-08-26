from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from decimal import Decimal

from sabiai.odds import PriceComparisonService, PriceQuote, SettlementRuleLibrary, SettlementRules

from .serializers import arbitrage_to_dict, json_value


class MarketTools:
    def __init__(self, app):
        self.app = app
        self.comparison = PriceComparisonService()
        self.settlement_rules = SettlementRuleLibrary()

    def handlers(self) -> dict:
        return {
            "market.interpret": self.interpret,
            "market.settlement.profile": self.settlement_profile,
            "market.compare": self.compare,
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

    def settlement_profile(self, args: dict) -> dict:
        sport = str(args.get("sport") or "").strip()
        market = str(args.get("market") or args.get("market_kind") or "").strip()
        if not sport or not market:
            raise ValueError("market.settlement.profile needs sport and market/market_kind.")
        parsed = self.app.market_interpreter.interpret(
            market,
            home=args.get("home"),
            away=args.get("away"),
        )
        market_kind = parsed.kind if parsed.understood else market
        profile = self.settlement_rules.profile(
            sport,
            market_kind,
            period=str(args.get("period") or parsed.period or "full_event"),
            line_key=(str(args.get("line_key")) if args.get("line_key") is not None else (
                str(parsed.line) if parsed.line is not None else None
            )),
        )
        data = json_value(profile)
        data["rules"]["key"] = list(profile.rules.key)
        if profile.verification_required:
            data["next_step"] = "Verify the listed settlement topics against each bookmaker's current rules before treating cross-book prices as equivalent."
        return data

    def compare(self, args: dict) -> dict:
        now = datetime.now(timezone.utc)
        quotes = self._quotes(args.get("quotes", []), now=now)
        result = self.comparison.compare(
            quotes,
            max_age_seconds=int(args.get("max_age_seconds", 180)),
            now=now,
        )
        return {
            "event_key": result.event_key,
            "market_key": result.market_key,
            "rejected_stale": result.rejected_stale,
            "rejected_rule_mismatch": result.rejected_rule_mismatch,
            "rule_key": list(result.rule_key) if result.rule_key is not None else None,
            "selections": [
                {
                    "selection": row.selection_label,
                    "best_bookmaker": row.best_bookmaker,
                    "best_odds": str(row.best_odds),
                    "price_gap": str(row.price_gap),
                    "prices": [
                        {
                            "bookmaker": price.bookmaker,
                            "odds": str(price.odds),
                            "captured_at": price.captured_at.isoformat(),
                            "age_seconds": price.age_seconds,
                        }
                        for price in row.prices
                    ],
                }
                for row in result.selections
            ],
        }

    def arbitrage(self, args: dict) -> dict:
        now = datetime.now(timezone.utc)
        quotes = self._quotes(args.get("quotes", []), now=now)
        result = self.app.arbitrage.find(
            quotes,
            [str(item) for item in args.get("expected_selections", [])],
            total_stake=args.get("total_stake"),
            max_age_seconds=int(args.get("max_age_seconds", 90)),
            now=now,
        )
        return arbitrage_to_dict(result)

    def _quotes(self, rows, *, now: datetime) -> list[PriceQuote]:
        quotes = []
        for raw in rows:
            bookmaker = self.app.bookmakers.resolve(str(raw["bookmaker"]))
            if bookmaker is None:
                raise ValueError(f"Unknown bookmaker: {raw['bookmaker']}")
            rule_data = raw.get("rules") or {}
            captured = raw.get("captured_at") or raw.get("observed_at")
            if captured:
                captured_at = datetime.fromisoformat(str(captured).replace("Z", "+00:00"))
                if captured_at.tzinfo is None:
                    captured_at = captured_at.replace(tzinfo=timezone.utc)
            else:
                captured_at = now
            quotes.append(
                PriceQuote(
                    event_key=str(raw["event_key"]),
                    market_key=str(raw["market_key"]),
                    selection_key=str(raw["selection_key"]),
                    selection_label=str(raw.get("selection_label") or raw["selection_key"]),
                    bookmaker=bookmaker.name,
                    odds=Decimal(str(raw["odds"])),
                    captured_at=captured_at,
                    rules=SettlementRules(
                        period=str(rule_data.get("period", "full_event")),
                        includes_overtime=rule_data.get("includes_overtime"),
                        void_rule=str(rule_data.get("void_rule", "standard")),
                        line_key=rule_data.get("line_key"),
                        retirement_rule=rule_data.get("retirement_rule"),
                        dead_heat_rule=rule_data.get("dead_heat_rule"),
                        format_rule=rule_data.get("format_rule"),
                    ),
                )
            )
        return quotes
