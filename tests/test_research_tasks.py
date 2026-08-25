import unittest

from sabiai.research import ResearchAssessment, ResearchTaskPlanner
from sabiai.sources import SourceKind


class ResearchTaskPlannerTests(unittest.TestCase):
    def test_missing_topics_become_prioritized_free_first_tasks(self):
        assessment = ResearchAssessment(
            sport="Football",
            event="Arsenal vs Chelsea",
            market="Over 2.5 goals",
            checklist=(),
            evidence_count=1,
            coverage_pct=20,
            evidence_quality="weak",
            missing_topics=("availability", "market_stats", "form"),
            skeptic_required=True,
        )
        tasks = ResearchTaskPlanner().plan(assessment)
        self.assertEqual(tasks[0].topic, "availability")
        self.assertEqual(tasks[0].preferred_source_kinds[0], SourceKind.CACHE)
        self.assertEqual(tasks[0].preferred_source_kinds[-1], SourceKind.SEARCH)
        self.assertNotIn(SourceKind.PAID_API, tasks[0].preferred_source_kinds)
        self.assertTrue(tasks[0].paid_fallback_allowed)

    def test_unknown_sport_gets_non_paid_source_discovery_first(self):
        assessment = ResearchAssessment(
            sport="Kabaddi",
            event="Team A vs Team B",
            market="Team A to win",
            checklist=(),
            evidence_count=0,
            coverage_pct=0,
            evidence_quality="weak",
            missing_topics=("rules", "form"),
            needs_source_discovery=True,
            skeptic_required=True,
        )
        tasks = ResearchTaskPlanner().plan(assessment)
        self.assertEqual(tasks[0].topic, "source_discovery")
        self.assertFalse(tasks[0].paid_fallback_allowed)
        self.assertEqual(tasks[0].preferred_source_kinds[0], SourceKind.OFFICIAL)

    def test_conflict_resolution_is_near_top_priority(self):
        from sabiai.research import EvidenceConflict

        assessment = ResearchAssessment(
            sport="Basketball",
            event="Team A vs Team B",
            market="Player A over 7.5 rebounds",
            checklist=(),
            evidence_count=4,
            coverage_pct=75,
            evidence_quality="fair",
            missing_topics=("context",),
            conflicts=(
                EvidenceConflict(
                    evidence_type="availability",
                    subject="Player A",
                    evidence_ids=("a", "b"),
                    reason="Sources disagree.",
                ),
            ),
            skeptic_required=True,
        )
        tasks = ResearchTaskPlanner().plan(assessment)
        self.assertEqual(tasks[0].topic, "conflict_resolution")
        self.assertEqual(tasks[0].capability, "verification")


if __name__ == "__main__":
    unittest.main()
