import unittest
from datetime import datetime, timedelta, timezone

from sabiai.research import ResearchCaseService


NOW = datetime(2026, 8, 25, 1, 0, tzinfo=timezone.utc)


class ResearchCaseTests(unittest.TestCase):
    def setUp(self):
        self.service = ResearchCaseService()

    def test_strong_football_case_with_market_evidence(self):
        evidence = [
            {
                "id": "form1",
                "evidence_type": "recent_form",
                "summary": "Arsenal have won four of their last five matches.",
                "reliability": "high",
                "fetched_at": NOW.isoformat(),
            },
            {
                "id": "avail1",
                "evidence_type": "injuries availability",
                "summary": "Current team availability checked from official team news.",
                "reliability": "official",
                "fetched_at": NOW.isoformat(),
            },
            {
                "id": "context1",
                "evidence_type": "competition context",
                "summary": "League match with normal first-team selection expected.",
                "reliability": "high",
                "fetched_at": NOW.isoformat(),
            },
            {
                "id": "ha1",
                "evidence_type": "home_away form",
                "summary": "Arsenal home form and Chelsea away form checked.",
                "reliability": "high",
                "fetched_at": NOW.isoformat(),
            },
            {
                "id": "sched1",
                "evidence_type": "schedule rest travel",
                "summary": "Both teams have normal rest.",
                "reliability": "high",
                "fetched_at": NOW.isoformat(),
            },
            {
                "id": "goals1",
                "evidence_type": "goals market_stats",
                "summary": "Scoring and conceding patterns checked for Over 2.5 goals.",
                "reliability": "high",
                "fetched_at": NOW.isoformat(),
            },
        ]
        result = self.service.assess(
            sport="Football",
            event="Arsenal vs Chelsea",
            market="Over 2.5 goals",
            home="Arsenal",
            away="Chelsea",
            evidence=evidence,
            now=NOW,
        )
        self.assertEqual(result.evidence_quality, "strong")
        self.assertGreaterEqual(result.coverage_pct, 80)
        self.assertFalse(result.skeptic_required)

    def test_stale_evidence_is_not_counted_as_coverage(self):
        result = self.service.assess(
            sport="Football",
            event="Arsenal vs Chelsea",
            market="Over 2.5 goals",
            evidence=[
                {
                    "id": "old_form",
                    "evidence_type": "recent_form",
                    "summary": "Old form check.",
                    "reliability": "high",
                    "fetched_at": (NOW - timedelta(hours=4)).isoformat(),
                    "freshness_seconds": 3600,
                }
            ],
            now=NOW,
        )
        self.assertIn("old_form", result.stale_evidence_ids)
        self.assertEqual(result.evidence_quality, "weak")
        self.assertTrue(result.skeptic_required)

    def test_structured_availability_conflict_is_detected(self):
        evidence = [
            {
                "id": "source_a",
                "evidence_type": "availability",
                "subject": "Player A",
                "summary": "Player A is listed available.",
                "reliability": "high",
                "fetched_at": NOW.isoformat(),
                "raw": {"status": "available"},
            },
            {
                "id": "source_b",
                "evidence_type": "availability",
                "subject": "Player A",
                "summary": "Player A is listed out.",
                "reliability": "high",
                "fetched_at": NOW.isoformat(),
                "raw": {"status": "out"},
            },
        ]
        result = self.service.assess(
            sport="Basketball",
            event="Team A vs Team B",
            market="Player A over 7.5 rebounds",
            evidence=evidence,
            now=NOW,
        )
        self.assertEqual(len(result.conflicts), 1)
        self.assertTrue(result.skeptic_required)
        self.assertTrue(any("conflicting" in q.casefold() for q in result.next_questions))

    def test_unknown_sport_requires_discovery(self):
        result = self.service.assess(
            sport="Kabaddi",
            event="Team A vs Team B",
            market="Team A to win",
            evidence=[],
            now=NOW,
        )
        self.assertTrue(result.needs_source_discovery)
        self.assertTrue(result.skeptic_required)
        self.assertTrue(any("rules" in q.casefold() for q in result.next_questions))


if __name__ == "__main__":
    unittest.main()
