from sabiai.research import (
    EvidenceConflict,
    ResearchAssessment,
    ResearchSynthesizer,
    SkepticReviewPlanner,
)


def assessment(**overrides):
    data = dict(
        sport="Football",
        event="Arsenal vs Chelsea",
        market="Arsenal to win",
        checklist=("recent form", "availability", "context"),
        evidence_count=3,
        coverage_pct=80,
        evidence_quality="strong",
        missing_topics=(),
        stale_evidence_ids=(),
        low_reliability_ids=(),
        conflicts=(),
        needs_source_discovery=False,
        skeptic_required=False,
        next_questions=(),
        notes=(),
    )
    data.update(overrides)
    return ResearchAssessment(**data)


def test_synthesis_keeps_plain_findings_and_sources():
    evidence = [
        {
            "id": "e1",
            "summary": "Arsenal have won four of their last five home matches.",
            "source_name": "Official League",
            "reliability": "official",
        },
        {
            "id": "e2",
            "summary": "Chelsea's first-choice striker is expected to miss the match.",
            "source_name": "Club Website",
            "reliability": "official",
        },
    ]
    summary = ResearchSynthesizer().summarize(assessment(), evidence)
    assert summary.what_we_know[0].startswith("Arsenal")
    assert "Official League" in summary.sources_used
    assert "What I know:" in summary.plain_text()


def test_synthesis_surfaces_conflicts_and_stale_items():
    conflict = EvidenceConflict(
        evidence_type="availability",
        subject="Player A",
        evidence_ids=("e1", "e2"),
        reason="Sources disagree on structured field 'available'.",
    )
    case = assessment(
        evidence_quality="weak",
        coverage_pct=40,
        stale_evidence_ids=("e3",),
        conflicts=(conflict,),
        skeptic_required=True,
        next_questions=("Check the current lineup.",),
    )
    summary = ResearchSynthesizer().summarize(case, [])
    assert summary.skeptic_required is True
    assert any("Sources conflict" in item for item in summary.what_worries_me)
    assert summary.still_to_check == ("Check the current lineup.",)


def test_skeptic_review_triggers_for_large_conversion_ticket():
    plan = SkepticReviewPlanner().plan(
        assessment(),
        ticket_legs=8,
        bookmaker_conversion=True,
        user_asked_strongest=True,
    )
    assert plan.required is True
    assert any("8 legs" in item for item in plan.triggers)
    assert any(question.area == "conversion" for question in plan.questions)
    assert any(question.area == "abstention" for question in plan.questions)


def test_skeptic_review_uses_recorded_bankroll_context():
    plan = SkepticReviewPlanner().plan(assessment(), stake="100", bankroll="1000")
    assert plan.required is True
    assert any("10.0%" in item for item in plan.triggers)
    assert any(question.area == "bankroll" for question in plan.questions)
