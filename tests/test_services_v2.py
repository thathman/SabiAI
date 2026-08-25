import tempfile
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from sabiai.domain import Event, Participant, Sport
from sabiai.research import Evidence, EvidenceStore
from sabiai.storage import BankrollLedger, HistoryService, SabiDatabase


class V2ServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = SabiDatabase(Path(self.tmp.name) / "sabiai-v2-test.db")
        self.db.initialize()

    def tearDown(self):
        self.tmp.cleanup()

    def test_bankroll_ledger_tracks_balance(self):
        ledger = BankrollLedger(self.db)
        ledger.record("opening_balance", "10000")
        ledger.record("stake", "1000")
        ledger.record("payout", "1500")
        self.assertEqual(ledger.current_balance(), Decimal("10500.00"))
        check = ledger.reconcile("10500")
        self.assertTrue(check["matches"])

    def test_research_evidence_can_be_reused(self):
        sport = Sport(name="Football", slug="football")
        self.db.save_sport(sport)
        home = Participant(name="Arsenal", sport_id=sport.id)
        away = Participant(name="Chelsea", sport_id=sport.id)
        event = Event(
            sport_id=sport.id,
            name="Arsenal vs Chelsea",
            starts_at=datetime.now(timezone.utc),
            home=home,
            away=away,
        )
        self.db.save_event(event)
        store = EvidenceStore(self.db)
        store.save(
            Evidence(
                event_id=event.id,
                sport_id=sport.id,
                evidence_type="injuries",
                subject="Arsenal",
                summary="Arsenal have one first-team defender unavailable.",
                source_name="Club website",
                reliability="official",
            )
        )
        item = store.reusable(event.id, "injuries", max_age_seconds=3600)
        self.assertIsNotNone(item)
        self.assertIn("defender", item["summary"])

    def test_empty_history_summary_is_readable(self):
        summary = HistoryService(self.db).summary()
        self.assertEqual(summary["picks"]["won"], 0)
        self.assertEqual(summary["picks"]["lost"], 0)
        self.assertEqual(summary["bankroll"], "0.00")


if __name__ == "__main__":
    unittest.main()
