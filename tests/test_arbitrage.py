import unittest
from datetime import datetime, timezone
from decimal import Decimal

from sabiai.odds import ArbitrageEngine, PriceQuote, SettlementRules


NOW = datetime.now(timezone.utc)


def quote(selection, bookmaker, odds, rules=None):
    return PriceQuote(
        event_key="event:1",
        market_key="winner:full",
        selection_key=selection,
        selection_label=selection,
        bookmaker=bookmaker,
        odds=Decimal(odds),
        captured_at=NOW,
        rules=rules or SettlementRules(period="full_event", includes_overtime=True),
    )


class ArbitrageTests(unittest.TestCase):
    def test_two_outcome_arbitrage(self):
        result = ArbitrageEngine().find(
            [quote("home", "Book A", "2.10"), quote("away", "Book B", "2.10")],
            ["home", "away"],
            total_stake="10000",
            now=NOW,
        )
        self.assertTrue(result.found)
        self.assertGreater(result.locked_profit, Decimal("0"))
        self.assertEqual(sum(row.stake for row in result.allocations), Decimal("10000.00"))

    def test_three_outcome_not_arbitrage(self):
        result = ArbitrageEngine().find(
            [
                quote("home", "A", "2.40"),
                quote("draw", "B", "3.10"),
                quote("away", "C", "2.70"),
            ],
            ["home", "draw", "away"],
            now=NOW,
        )
        self.assertFalse(result.found)

    def test_different_settlement_rules_do_not_mix(self):
        regulation = SettlementRules(period="regulation", includes_overtime=False)
        overtime = SettlementRules(period="full_event", includes_overtime=True)
        result = ArbitrageEngine().find(
            [
                quote("home", "A", "2.20", regulation),
                quote("away", "B", "2.20", overtime),
            ],
            ["home", "away"],
            now=NOW,
        )
        self.assertFalse(result.found)
        self.assertIn("settlement rules", result.reason)

    def test_best_price_selected_per_outcome(self):
        result = ArbitrageEngine().find(
            [
                quote("home", "A", "1.95"),
                quote("home", "B", "2.10"),
                quote("away", "A", "2.10"),
            ],
            ["home", "away"],
            now=NOW,
        )
        self.assertTrue(result.found)
        home = next(row for row in result.quotes if row.selection_key == "home")
        self.assertEqual(home.bookmaker, "B")


if __name__ == "__main__":
    unittest.main()
