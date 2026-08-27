import tempfile
import unittest
from pathlib import Path

from sabiai.sources import Source, SourceCost, SourceHealthService, SourceKind, SourceRegistry, SourceRequest, SourceService
from sabiai.storage import SabiDatabase


class SourceServiceTests(unittest.TestCase):
    def make_service(self):
        tmp = tempfile.TemporaryDirectory()
        db = SabiDatabase(Path(tmp.name) / "v2.db")
        db.initialize()
        registry = SourceRegistry()
        registry.register(Source("Official", SourceKind.OFFICIAL, SourceCost.FREE, {"volleyball"}, {"injuries"}))
        registry.register(Source("Free Web", SourceKind.PUBLIC_WEB, SourceCost.FREE, {"volleyball"}, {"injuries"}))
        registry.register(Source("Paid Feed", SourceKind.PAID_API, SourceCost.PAID, {"volleyball"}, {"injuries"}))
        return tmp, db, SourceService(db, registry)

    def test_free_source_wins_even_when_paid_allowed(self):
        tmp, db, service = self.make_service()
        self.addCleanup(tmp.cleanup)
        calls = []
        result = service.execute(
            SourceRequest("injury:test", "injuries", "volleyball"),
            {
                "Official": lambda request: calls.append("official") or {"status": "available"},
                "Paid Feed": lambda request: calls.append("paid") or {"status": "paid"},
            },
            allow_paid=True,
            paid_reason="confirmation",
        )
        self.assertEqual(result.source_name, "Official")
        self.assertEqual(calls, ["official"])

    def test_unused_source_has_a_plain_not_used_yet_state(self):
        tmp, db, _service = self.make_service()
        self.addCleanup(tmp.cleanup)
        db.upsert_source(Source("Official", SourceKind.OFFICIAL, SourceCost.FREE, {"volleyball"}, {"injuries"}))

        states = {source.name: source.state for source in SourceHealthService(db).sources()}

        self.assertEqual(states["Official"], "not_used_yet")

    def test_cache_prevents_duplicate_fetch(self):
        tmp, db, service = self.make_service()
        self.addCleanup(tmp.cleanup)
        calls = []
        fetchers = {"Official": lambda request: calls.append(1) or {"ok": True}}
        request = SourceRequest("same:request", "injuries", "volleyball", ttl_seconds=3600)
        first = service.execute(request, fetchers)
        second = service.execute(request, fetchers)
        self.assertFalse(first.cache_hit)
        self.assertTrue(second.cache_hit)
        self.assertEqual(len(calls), 1)

    def test_paid_used_only_after_free_failure_and_reason(self):
        tmp, db, service = self.make_service()
        self.addCleanup(tmp.cleanup)
        calls = []
        result = service.execute(
            SourceRequest("paid:fallback", "injuries", "volleyball"),
            {
                "Official": lambda request: (_ for _ in ()).throw(RuntimeError("not published")),
                "Free Web": lambda request: (_ for _ in ()).throw(RuntimeError("stale")),
                "Paid Feed": lambda request: calls.append("paid") or {"status": "confirmed"},
            },
            allow_paid=True,
            paid_reason="Both free sources failed and current injury status is needed.",
        )
        self.assertEqual(result.source_name, "Paid Feed")
        self.assertTrue(result.paid)
        self.assertEqual(calls, ["paid"])
        self.assertGreaterEqual(len(result.failures), 2)

    def test_paid_without_reason_is_not_called(self):
        tmp, db, service = self.make_service()
        self.addCleanup(tmp.cleanup)
        paid_calls = []
        with self.assertRaises(RuntimeError):
            service.execute(
                SourceRequest("paid:no-reason", "injuries", "volleyball"),
                {
                    "Official": lambda request: (_ for _ in ()).throw(RuntimeError("failed")),
                    "Free Web": lambda request: (_ for _ in ()).throw(RuntimeError("failed")),
                    "Paid Feed": lambda request: paid_calls.append(1) or {"ok": True},
                },
                allow_paid=True,
            )
        self.assertEqual(paid_calls, [])


if __name__ == "__main__":
    unittest.main()
