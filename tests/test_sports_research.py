import unittest

from sabiai.openclaw import SabiToolGateway
from sabiai.sports import ResearchPlanner, default_sports


class SportsRegistryTests(unittest.TestCase):
    def test_large_starting_registry(self):
        sports = default_sports().all()
        self.assertGreaterEqual(len(sports), 20)
        names = {sport.name for sport in sports}
        self.assertIn("Football", names)
        self.assertIn("Volleyball", names)
        self.assertIn("Esports", names)
        self.assertIn("Golf", names)

    def test_unknown_sport_requests_discovery(self):
        profile = default_sports().resolve("Sepak Takraw")
        self.assertTrue(profile.needs_discovery)
        self.assertEqual(profile.name, "Sepak Takraw")

    def test_cards_market_changes_research_plan(self):
        plan = ResearchPlanner().plan("football", market_text="Over 4.5 cards", home="Arsenal", away="Chelsea")
        joined = " ".join(plan.market_focus)
        self.assertIn("referee", joined)
        self.assertIn("cards", joined)

    def test_volleyball_set_plan(self):
        plan = ResearchPlanner().plan("volleyball", market_text="Over 3.5 sets")
        joined = " ".join(plan.checklist)
        self.assertIn("sets won and lost", joined)
        self.assertIn("set/frame/map", joined)

    def test_gateway_lists_open_ended_sports(self):
        result = SabiToolGateway().dispatch("sports.list", {})
        self.assertTrue(result["ok"])
        self.assertTrue(result["data"]["open_ended"])
        self.assertGreaterEqual(len(result["data"]["sports"]), 20)


if __name__ == "__main__":
    unittest.main()
