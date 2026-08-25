import unittest

from sabiai.bookmakers import BookmakerDiscoveryPlanner
from sabiai.tickets import TicketNormalizer


class BookmakerDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.normalizer = TicketNormalizer()

    def test_conversion_search_plan_preserves_market_identity(self):
        ticket = self.normalizer.normalize(
            [
                {
                    "sport": "Football",
                    "event": "Arsenal vs Chelsea",
                    "home": "Arsenal",
                    "away": "Chelsea",
                    "market": "Arsenal +1.5 handicap",
                    "odds": "1.40",
                },
                {
                    "sport": "Football",
                    "event": "Barcelona vs Sevilla",
                    "home": "Barcelona",
                    "away": "Sevilla",
                    "market": "Over 2.5 goals",
                    "odds": "1.80",
                },
            ]
        ).ticket
        plan = BookmakerDiscoveryPlanner().plan_conversion(
            ticket, target_bookmaker="SportyBet"
        )
        self.assertTrue(plan.ready)
        self.assertEqual(len(plan.tasks), 2)
        first = plan.tasks[0]
        self.assertEqual(first.event, "Arsenal vs Chelsea")
        self.assertEqual(first.sport, "Football")
        self.assertEqual(str(first.line), "1.5")
        self.assertIn("Do not substitute a different line or period", first.instruction)

    def test_missing_sport_blocks_ready_plan(self):
        ticket = self.normalizer.normalize(
            [
                {
                    "event": "Arsenal vs Chelsea",
                    "home": "Arsenal",
                    "away": "Chelsea",
                    "market": "Arsenal to win",
                    "odds": "1.70",
                }
            ]
        ).ticket
        plan = BookmakerDiscoveryPlanner().plan_conversion(
            ticket, target_bookmaker="Bet9ja"
        )
        self.assertFalse(plan.ready)
        self.assertTrue(any("sport" in item.casefold() for item in plan.missing_context))


if __name__ == "__main__":
    unittest.main()
