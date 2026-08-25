import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from sabiai.storage import SabiDatabase
from sabiai.system import ReadinessState, SystemReadinessService


NOW = datetime(2026, 8, 25, 1, 0, tzinfo=timezone.utc)


class SystemReadinessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = SabiDatabase(Path(self.tmp.name) / "v2.db")
        self.db.initialize()
        self.service = SystemReadinessService(self.db)

    def tearDown(self):
        self.tmp.cleanup()

    def test_clean_database_is_ready_without_requested_external_capability(self):
        report = self.service.assess(now=NOW)
        self.assertEqual(report.state, ReadinessState.READY)
        self.assertTrue(report.database_ok)
        self.assertTrue(report.bankroll_ok)
        self.assertTrue(report.can_build_ticket)

    def test_missing_required_source_moves_to_observe_only(self):
        report = self.service.assess(
            required_capabilities=("availability",),
            now=NOW,
        )
        self.assertEqual(report.state, ReadinessState.OBSERVE_ONLY)
        self.assertFalse(report.can_build_ticket)
        self.assertTrue(any("availability" in issue.message for issue in report.issues))

    def test_corrupt_bankroll_running_balance_locks_action(self):
        with self.db.transaction() as conn:
            conn.execute(
                "INSERT INTO bankroll_ledger(kind, amount, balance_after) VALUES('deposit','100.00','99.00')"
            )
        report = self.service.assess(now=NOW)
        self.assertEqual(report.state, ReadinessState.ACTION_LOCKED)
        self.assertFalse(report.bankroll_ok)
        self.assertFalse(report.can_research)

    def test_repeated_settlement_job_failure_moves_to_observe_only(self):
        with self.db.transaction() as conn:
            conn.execute(
                """INSERT INTO jobs(name, description, enabled, consecutive_failures, last_error)
                   VALUES('auto-settlement','test',1,3,'score provider failed')"""
            )
        report = self.service.assess(now=NOW)
        self.assertEqual(report.state, ReadinessState.OBSERVE_ONLY)
        self.assertTrue(any(issue.area == "jobs" for issue in report.issues))


if __name__ == "__main__":
    unittest.main()
