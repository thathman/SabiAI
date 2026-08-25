import tempfile
import unittest
from pathlib import Path

from sabiai.storage import SabiDatabase, TicketDraftStore


class TicketDraftStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = SabiDatabase(Path(self.tmp.name) / "v2.db")
        self.db.initialize()
        self.store = TicketDraftStore(self.db)

    def tearDown(self):
        self.tmp.cleanup()

    def test_create_and_reload_draft(self):
        draft = self.store.create(
            {"combined_odds": "4.20", "legs": [{"event": "A vs B"}]},
            source_type="booking_code",
            source_reference="ABC123",
            source_bookmaker_slug="bet9ja",
        )
        loaded = self.store.get(draft.id)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.source_reference, "ABC123")
        self.assertEqual(loaded.payload["combined_odds"], "4.20")

    def test_revision_preserves_lineage(self):
        original = self.store.create(
            {"legs": [{"event": "A vs B"}, {"event": "C vs D"}]},
            source_type="screenshot",
            source_bookmaker_slug="sportybet",
        )
        revision = self.store.revise(
            original.id,
            {"legs": [{"event": "A vs B"}]},
            status="edited",
        )
        lineage = self.store.lineage(revision.id)
        self.assertEqual([item.id for item in lineage], [original.id, revision.id])
        self.assertEqual(revision.parent_draft_id, original.id)
        self.assertEqual(revision.source_bookmaker_slug, "sportybet")

    def test_revision_requires_existing_parent(self):
        with self.assertRaises(KeyError):
            self.store.revise("missing", {"legs": []})


if __name__ == "__main__":
    unittest.main()
