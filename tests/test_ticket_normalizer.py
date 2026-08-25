import unittest

from sabiai.bookmakers import BookmakerCapability, legacy_command_adapters
from sabiai.tickets import TicketNormalizer


class TicketNormalizerTests(unittest.TestCase):
    def setUp(self):
        self.normalizer = TicketNormalizer()

    def test_normalizes_explicit_ticket(self):
        result = self.normalizer.normalize(
            [
                {
                    "home": "Arsenal",
                    "away": "Chelsea",
                    "market": "Handicap 1 +1.5",
                    "odds": "1.42",
                }
            ],
            bookmaker="Sporty Bet",
            source_type="screenshot",
            source_reference="shot-1",
        )
        self.assertTrue(result.usable)
        self.assertEqual(result.ticket.legs[0].event_label, "Arsenal vs Chelsea")
        self.assertEqual(result.ticket.legs[0].selection.label, "Arsenal +1.5 handicap")
        self.assertEqual(result.ticket.source_type, "screenshot")
        self.assertEqual(result.ticket.source_reference, "shot-1")

    def test_duplicate_selection_is_flagged(self):
        leg = {
            "event": "Arsenal vs Chelsea",
            "home": "Arsenal",
            "away": "Chelsea",
            "market": "1",
            "odds": "1.60",
        }
        result = self.normalizer.normalize([leg, leg])
        self.assertTrue(result.usable)
        self.assertTrue(any("Duplicate selection" in issue.message for issue in result.issues))

    def test_invalid_decimal_odds_is_an_error(self):
        result = self.normalizer.normalize(
            [
                {
                    "event": "Arsenal vs Chelsea",
                    "home": "Arsenal",
                    "away": "Chelsea",
                    "market": "1",
                    "odds": "0.95",
                }
            ]
        )
        self.assertFalse(result.usable)
        self.assertTrue(any(issue.level == "error" for issue in result.issues))

    def test_unknown_market_is_preserved_but_flagged(self):
        result = self.normalizer.normalize(
            [
                {
                    "event": "Player A vs Player B",
                    "market": "Mystery special market",
                    "odds": "1.80",
                }
            ]
        )
        self.assertTrue(result.usable)
        self.assertTrue(any(issue.level == "warning" for issue in result.issues))


class BookmakerAdapterTests(unittest.TestCase):
    def test_only_proven_legacy_capabilities_are_advertised(self):
        adapters = legacy_command_adapters()
        sporty = adapters.get("sportybet")
        self.assertIsNotNone(sporty)
        self.assertIn(BookmakerCapability.TICKET_BUILD, sporty.capabilities())
        self.assertIn(BookmakerCapability.BOOKING_CODE_CREATE, sporty.capabilities())
        self.assertNotIn(BookmakerCapability.BOOKING_CODE_IMPORT, sporty.capabilities())
        self.assertIsNone(adapters.get("stake"))


if __name__ == "__main__":
    unittest.main()
