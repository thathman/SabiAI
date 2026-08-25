import tempfile
import unittest
from pathlib import Path

from sabiai.research import ResearchOrchestrator, ResearchTask
from sabiai.sources import Source, SourceCost, SourceKind, SourceRegistry
from sabiai.storage import SabiDatabase


class ResearchOrchestratorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = SabiDatabase(Path(self.tmp.name) / "v2.db")
        self.db.initialize()

    def tearDown(self):
        self.tmp.cleanup()

    def test_free_source_is_used_and_result_is_cached(self):
        registry = SourceRegistry()
        registry.register(
            Source(
                "Official Team News",
                SourceKind.OFFICIAL,
                SourceCost.FREE,
                {"football"},
                {"availability"},
            )
        )
        calls = {"count": 0}

        def fetch(_request):
            calls["count"] += 1
            return {
                "summary": "Arsenal's expected starters are available.",
                "subject": "Arsenal",
                "reliability": "official",
                "raw": {"status": "available"},
            }

        task = ResearchTask(
            topic="availability",
            capability="availability",
            instruction="Check availability.",
            priority=10,
            freshness_seconds=600,
            preferred_source_kinds=(SourceKind.OFFICIAL,),
        )
        orchestrator = ResearchOrchestrator(self.db, registry)
        first = orchestrator.execute(
            [task],
            sport="football",
            event="Arsenal vs Chelsea",
            fetchers={"Official Team News": fetch},
        )
        second = orchestrator.execute(
            [task],
            sport="football",
            event="Arsenal vs Chelsea",
            fetchers={"Official Team News": fetch},
        )
        self.assertEqual(first.success_count, 1)
        self.assertEqual(second.cache_hits, 1)
        self.assertEqual(calls["count"], 1)
        self.assertIsNotNone(first.items[0].evidence_id)

    def test_paid_source_requires_explicit_approval_and_reason(self):
        registry = SourceRegistry()
        registry.register(
            Source(
                "Paid Injuries",
                SourceKind.PAID_API,
                SourceCost.PAID,
                {"football"},
                {"availability"},
            )
        )
        task = ResearchTask(
            topic="availability",
            capability="availability",
            instruction="Check availability.",
            priority=10,
            freshness_seconds=600,
            preferred_source_kinds=(SourceKind.OFFICIAL,),
            paid_fallback_allowed=True,
        )
        orchestrator = ResearchOrchestrator(self.db, registry)
        blocked = orchestrator.execute(
            [task],
            sport="football",
            event="Arsenal vs Chelsea",
            fetchers={"Paid Injuries": lambda _: "Player availability checked."},
            allow_paid=False,
        )
        self.assertEqual(blocked.failure_count, 1)

        allowed = orchestrator.execute(
            [task],
            sport="football",
            event="Arsenal vs Chelsea",
            fetchers={"Paid Injuries": lambda _: "Player availability checked."},
            allow_paid=True,
            paid_reason="Official and public sources had no current lineup information.",
        )
        self.assertEqual(allowed.success_count, 1)
        self.assertEqual(allowed.paid_calls, 1)

    def test_source_discovery_task_never_escalates_to_paid(self):
        registry = SourceRegistry()
        registry.register(
            Source(
                "Paid Discovery",
                SourceKind.PAID_API,
                SourceCost.PAID,
                set(),
                {"source_discovery"},
            )
        )
        task = ResearchTask(
            topic="source_discovery",
            capability="source_discovery",
            instruction="Find public sources.",
            priority=0,
            freshness_seconds=3600,
            preferred_source_kinds=(SourceKind.SEARCH,),
            paid_fallback_allowed=False,
        )
        run = ResearchOrchestrator(self.db, registry).execute(
            [task],
            sport="kabaddi",
            event="Team A vs Team B",
            fetchers={"Paid Discovery": lambda _: "Should never run."},
            allow_paid=True,
            paid_reason="test",
        )
        self.assertEqual(run.failure_count, 1)
        self.assertEqual(run.paid_calls, 0)


if __name__ == "__main__":
    unittest.main()
