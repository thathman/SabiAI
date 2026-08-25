import unittest

from sabiai.domain.types import MarketKind
from sabiai.markets import MarketInterpreter


class PlainMarketLanguageTests(unittest.TestCase):
    def setUp(self):
        self.interpreter = MarketInterpreter()

    def test_handicap_one_names_home_team(self):
        parsed = self.interpreter.interpret(
            "Handicap 1 +4.5", home="Arsenal", away="Chelsea"
        )
        self.assertTrue(parsed.understood)
        self.assertEqual(parsed.plain_label, "Arsenal +4.5 handicap")
        self.assertEqual(parsed.participant, "Arsenal")

    def test_handicap_two_names_away_team(self):
        parsed = self.interpreter.interpret(
            "Handicap 2 -2.5", home="Arsenal", away="Chelsea"
        )
        self.assertTrue(parsed.understood)
        self.assertEqual(parsed.plain_label, "Chelsea -2.5 handicap")
        self.assertEqual(parsed.participant, "Chelsea")

    def test_team_total_stays_tied_to_team(self):
        parsed = self.interpreter.interpret(
            "Arsenal over 1.5 goals", home="Arsenal", away="Chelsea"
        )
        self.assertEqual(parsed.kind, MarketKind.TEAM_TOTAL)
        self.assertEqual(parsed.plain_label, "Arsenal — Over 1.5 goals")
        self.assertEqual(parsed.participant, "Arsenal")

    def test_player_stat_keeps_player_name(self):
        parsed = self.interpreter.interpret("LeBron James over 7.5 rebounds")
        self.assertEqual(parsed.kind, MarketKind.PLAYER)
        self.assertEqual(
            parsed.plain_label, "LeBron James — Over 7.5 rebounds"
        )
        self.assertEqual(parsed.participant, "LeBron James")

    def test_set_total_is_recognized(self):
        parsed = self.interpreter.interpret("Over 3.5 sets")
        self.assertEqual(parsed.kind, MarketKind.SET_FRAME_MAP)
        self.assertEqual(parsed.plain_label, "Over 3.5 sets")

    def test_period_is_kept_in_plain_label(self):
        parsed = self.interpreter.interpret("First half over 1.5 goals")
        self.assertEqual(parsed.period, "first_half")
        self.assertEqual(parsed.plain_label, "First half — Over 1.5 goals")

    def test_map_period_is_kept(self):
        parsed = self.interpreter.interpret("Map 1 over 20.5 kills")
        self.assertEqual(parsed.period, "map_1")
        self.assertEqual(parsed.plain_label, "Map 1 — Over 20.5 kills")


if __name__ == "__main__":
    unittest.main()
