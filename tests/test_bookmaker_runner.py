import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

from sabiai.bookmakers import BookmakerCommandRunner, BuildExecutionPlan


class BookmakerRunnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "scripts").mkdir()
        (self.root / "scripts" / "sportybet_book.py").write_text("# test", encoding="utf-8")
        self.runner = BookmakerCommandRunner()

    def tearDown(self):
        self.tmp.cleanup()

    def plan(self):
        return BuildExecutionPlan(
            bookmaker_slug="sportybet",
            ready=True,
            reason="ready",
            command="python3 scripts/sportybet_book.py",
            legs=(
                {
                    "match": "Arsenal vs Chelsea",
                    "pick": "Arsenal to win",
                    "market": "Arsenal to win",
                    "sport": "Football",
                    "decimal_odds": "1.700",
                    "target_market_ref": None,
                },
            ),
            expects_booking_code=True,
        )

    @patch("sabiai.bookmakers.runner.subprocess.run")
    def test_extracts_booking_code_from_successful_builder(self, run):
        run.return_value = CompletedProcess(
            args=[], returncode=0, stdout="some log\nAB12CD\n", stderr=""
        )
        result = self.runner.execute(self.plan(), repo_root=self.root)
        self.assertTrue(result.success)
        self.assertEqual(result.booking_code, "AB12CD")
        argv = run.call_args.args[0]
        self.assertNotIn("shell=True", str(run.call_args))
        self.assertEqual(argv[:2], ["python3", "scripts/sportybet_book.py"])
        self.assertIn("--legs", argv)

    @patch("sabiai.bookmakers.runner.subprocess.run")
    def test_dry_run_does_not_claim_placeholder_as_real_code(self, run):
        run.return_value = CompletedProcess(
            args=[], returncode=0, stdout="DRY_RUN_CODE_PLACEHOLDER\n", stderr=""
        )
        result = self.runner.execute(self.plan(), repo_root=self.root, dry_run=True)
        self.assertTrue(result.success)
        self.assertIsNone(result.booking_code)

    def test_unlisted_command_is_refused(self):
        bad = BuildExecutionPlan(
            bookmaker_slug="sportybet",
            ready=True,
            reason="ready",
            command="python3 scripts/anything.py",
            legs=self.plan().legs,
            expects_booking_code=True,
        )
        result = self.runner.execute(bad, repo_root=self.root)
        self.assertFalse(result.success)
        self.assertIn("allow-list", result.message)


if __name__ == "__main__":
    unittest.main()
