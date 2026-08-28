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
        expected = {
            "research.case.assess",
            "research.case.next",
            "research.case.summary",
            "research.review.plan",
            "bookmaker.search.plan",
            "bookmaker.browser.playbook",
            "bookmaker.booking_code.restore",
            "system.readiness",
            "system.daily_research",
            "history.picks",
            "ticket.draft.lineage",
        }
        self.assertTrue(expected.issubset(set(tools)))

    def test_initialize_and_readiness(self):
        initialized = self.gateway.dispatch("system.initialize")
        self.assertTrue(initialized["ok"])
        readiness = self.gateway.dispatch("system.readiness")
        self.assertTrue(readiness["ok"])
        self.assertEqual(readiness["data"]["state"], "READY")

    def test_history_picks_returns_canonical_pick_rows(self):
        db = self.gateway._db(initialize=True)
        with db.transaction() as conn:
            conn.execute("INSERT INTO sports(id,slug,name) VALUES('sport_football','football','Football')")
            conn.execute(
                "INSERT INTO events(id,sport_id,name,starts_at,status) VALUES(?,?,?,?,?)",
                ("event_1", "sport_football", "Arsenal vs Chelsea", "2026-08-28T18:00:00+00:00", "scheduled"),
            )
            conn.execute(
                "INSERT INTO markets(id,event_id,kind,label) VALUES(?,?,?,?)",
                ("market_1", "event_1", "winner", "Arsenal to win"),
            )
            conn.execute(
                "INSERT INTO selections(id,market_id,label) VALUES(?,?,?)",
                ("selection_1", "market_1", "Arsenal to win"),
            )
            conn.execute(
                """INSERT INTO picks_v2(
                       id,event_id,market_id,selection_id,decimal_odds,confidence_pct,
                       rationale,strategy,outcome,created_at
                   ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (
                    "pick_1",
                    "event_1",
                    "market_1",
                    "selection_1",
                    "1.80",
                    64,
                    "Home form and availability support the selection.",
                    "value",
                    "pending",
                    "2026-08-28T08:00:00+00:00",
                ),
            )

        result = self.gateway.dispatch("history.picks", {"limit": 10})
        self.assertTrue(result["ok"])
        self.assertEqual(result["data"]["rows"][0]["event"], "Arsenal vs Chelsea")
        self.assertEqual(result["data"]["rows"][0]["selection"], "Arsenal to win")
        self.assertEqual(result["data"]["rows"][0]["outcome"], "pending")

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

    def test_bookmaker_browser_playbook_is_available_through_gateway(self):
        result = self.gateway.dispatch(
            "bookmaker.browser.playbook",
            {"bookmaker": "SportyBet"},
        )
        self.assertTrue(result["ok"])
        self.assertTrue(result["data"]["found"])
        self.assertEqual(
            result["data"]["playbook"]["entry_url"],
            "https://www.sportybet.com/ng/lite/betslip",
        )

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

    def test_research_summary_stays_plain_language(self):
        result = self.gateway.dispatch(
            "research.case.summary",
            {
                "sport": "Football",
                "event": "Arsenal vs Chelsea",
                "market": "Arsenal to win",
                "home": "Arsenal",
                "away": "Chelsea",
                "evidence": [
                    {
                        "id": "e1",
                        "evidence_type": "form",
                        "summary": "Arsenal have won four of their last five home matches.",
                        "source_name": "Official League",
                        "reliability": "official",
                    }
                ],
            },
        )
        self.assertTrue(result["ok"])
        self.assertIn("What I know:", result["data"]["plain_text"])
        self.assertNotIn("model", result["data"]["plain_text"].casefold())

    def test_skeptic_review_plan_triggers_for_large_ticket(self):
        result = self.gateway.dispatch(
            "research.review.plan",
            {
                "sport": "Volleyball",
                "event": "Team A vs Team B",
                "market": "Team A to win",
                "evidence": [],
                "ticket_legs": 8,
                "user_asked_strongest": True,
            },
        )
        self.assertTrue(result["ok"])
        self.assertTrue(result["data"]["required"])
        self.assertTrue(result["data"]["questions"])


if __name__ == "__main__":
    unittest.main()
