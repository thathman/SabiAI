import tempfile
import unittest
from pathlib import Path

from sabiai.config import Settings
from sabiai.openclaw.gateway import SabiToolGateway


class OpenClawGatewayTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.settings = Settings(
            repo_root=root,
            data_dir=root / "data",
            legacy_bets_db=root / "data" / "bets.db",
            v2_db=root / "data" / "v2.db",
            timezone="Africa/Lagos",
            paid_sources_enabled=True,
        )
        self.gateway = SabiToolGateway(self.settings)

    def tearDown(self):
        self.tmp.cleanup()

    def test_tool_registry_includes_new_v2_surfaces(self):
        result = self.gateway.dispatch("system.tools")
        self.assertTrue(result["ok"])
        tools = result["data"]["tools"]
        self.assertIn("research.case.assess", tools)
        self.assertIn("research.case.next", tools)
        self.assertIn("bookmaker.search.plan", tools)
        self.assertIn("system.readiness", tools)
        self.assertIn("ticket.draft.lineage", tools)

    def test_initialize_and_readiness(self):
        initialized = self.gateway.dispatch("system.initialize")
        self.assertTrue(initialized["ok"])
        readiness = self.gateway.dispatch("system.readiness")
        self.assertTrue(readiness["ok"])
        self.assertEqual(readiness["data"]["state"], "READY")

    def test_plain_market_language_still_works_after_refactor(self):
        result = self.gateway.dispatch(
            "market.interpret",
            {"text": "X2", "home": "Arsenal", "away": "Chelsea"},
        )
        self.assertTrue(result["ok"])
        self.assertEqual(
            result["data"]["plain_label"],
            "Chelsea or Draw — Double Chance",
        )

    def test_bookmaker_search_plan_is_available_through_gateway(self):
        result = self.gateway.dispatch(
            "bookmaker.search.plan",
            {
                "target_bookmaker": "SportyBet",
                "legs": [
                    {
                        "sport": "Football",
                        "event": "Arsenal vs Chelsea",
                        "home": "Arsenal",
                        "away": "Chelsea",
                        "market": "Arsenal +1.5 handicap",
                        "odds": "1.40",
                    }
                ],
            },
        )
        self.assertTrue(result["ok"])
        self.assertTrue(result["data"]["ready"])
        self.assertEqual(result["data"]["tasks"][0]["sport"], "Football")

    def test_research_case_returns_next_free_first_tasks(self):
        result = self.gateway.dispatch(
            "research.case.next",
            {
                "sport": "Football",
                "event": "Arsenal vs Chelsea",
                "market": "Over 2.5 goals",
                "home": "Arsenal",
                "away": "Chelsea",
                "evidence": [],
            },
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["data"]["assessment"]["evidence_quality"], "weak")
        self.assertTrue(result["data"]["tasks"])


if __name__ == "__main__":
    unittest.main()
