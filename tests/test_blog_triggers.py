import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sabiai.blog import BlogTriggerService
from sabiai.storage import SabiDatabase


class BlogTriggerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = SabiDatabase(Path(self.tmp.name) / "sabi-v2.db")
        self.db.initialize()

    def tearDown(self):
        self.tmp.cleanup()

    def test_parse_stamp_accepts_sqlite_and_iso_formats(self):
        sqlite_stamp = BlogTriggerService._parse_stamp("2026-08-25 17:30:00")
        iso_stamp = BlogTriggerService._parse_stamp("2026-08-25T17:30:00+00:00")
        self.assertEqual(sqlite_stamp, iso_stamp)

    def test_recent_settlement_correction_and_verified_source_trigger_reflection(self):
        now = datetime(2026, 8, 25, 18, 0, tzinfo=timezone.utc)
        recent = (now - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
        with self.db.transaction() as conn:
            conn.execute(
                """INSERT INTO settlement_audit(
                       entity_type,entity_id,previous_outcome,new_outcome,source,reason,changed_at
                   ) VALUES(?,?,?,?,?,?,?)""",
                ("pick", "pick-1", "lost", "won", "test", "official correction", recent),
            )
            conn.execute(
                """INSERT INTO source_discoveries(
                       id,name,url,kind,status,sports_json,capabilities_json,reliability,verified_at
                   ) VALUES(?,?,?,?,?,?,?,?,?)""",
                (
                    "source-1",
                    "Official League",
                    "https://example.test/league",
                    "official",
                    "verified",
                    '["volleyball"]',
                    '["results"]',
                    "high",
                    recent,
                ),
            )

        triggers = BlogTriggerService(self.db).evaluate(hours=24, now=now)
        keys = [item.key for item in triggers]
        self.assertIn("settlement_correction", keys)
        self.assertIn("source_discovery", keys)
        self.assertEqual(triggers[0].key, "settlement_correction")
        self.assertEqual(triggers[0].priority, "high")

    def test_old_activity_does_not_trigger_recent_reflection(self):
        now = datetime(2026, 8, 25, 18, 0, tzinfo=timezone.utc)
        old = (now - timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S")
        with self.db.transaction() as conn:
            conn.execute(
                """INSERT INTO settlement_audit(
                       entity_type,entity_id,previous_outcome,new_outcome,source,reason,changed_at
                   ) VALUES(?,?,?,?,?,?,?)""",
                ("pick", "pick-old", "lost", "won", "test", "old correction", old),
            )

        triggers = BlogTriggerService(self.db).evaluate(hours=24, now=now)
        self.assertNotIn("settlement_correction", [item.key for item in triggers])


if __name__ == "__main__":
    unittest.main()
