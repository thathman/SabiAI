from sabiai.sources import SourceHealth
from sabiai.system import build_issue_lines, health_digest, notification_for_change
from sabiai.system.readiness import ReadinessIssue, ReadinessState


def source(name: str, state: str, error: str | None = None) -> SourceHealth:
    return SourceHealth(
        name=name,
        kind="public_api",
        cost="free",
        enabled=True,
        requests=1,
        successes=0 if state == "down" else 1,
        failures=1 if state == "down" else 0,
        success_pct=0.0 if state == "down" else 100.0,
        cache_hits=0,
        paid_calls=0,
        last_requested_at=None,
        last_success_at=None,
        last_error_at=None,
        last_error=error,
        state=state,
    )


def test_health_issues_include_actionable_sources_and_readiness_only():
    issues = build_issue_lines(
        [source("Flashscore", "degraded", "HTTP 422\ninvalid query"), source("ESPN", "not_used_yet")],
        [ReadinessIssue(ReadinessState.DEGRADED, "jobs", "heartbeat overdue")],
    )
    assert issues == ["Jobs: heartbeat overdue", "Source Flashscore: degraded (HTTP 422 invalid query)"]


def test_health_notification_is_change_driven_and_recovers():
    warning = notification_for_change({}, issues=("Source Flashscore: degraded",))
    assert warning is not None
    assert warning["tag"] == "sabi-boy-health"
    assert notification_for_change(
        {"digest": health_digest(("Source Flashscore: degraded",))},
        issues=("Source Flashscore: degraded",),
    ) is None
    recovered = notification_for_change(
        {"digest": health_digest(("Source Flashscore: degraded",))},
        issues=(),
    )
    assert recovered is not None
    assert recovered["title"] == "Sabi Boy health recovered"


def test_health_alert_redacts_secret_shaped_source_errors():
    issues = build_issue_lines(
        [source("Analyzer", "down", "token=sbma_not-a-real-key Bearer abc123")],
        [],
    )
    assert issues == ["Source Analyzer: down (token=[redacted] Bearer [redacted])"]
