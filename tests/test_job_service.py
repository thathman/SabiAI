from datetime import datetime, timezone
from pathlib import Path

from sabiai.system import JobService
from sabiai.storage import SabiDatabase


def test_job_failure_backoff_and_success_reset(tmp_path: Path):
    db = SabiDatabase(tmp_path / "v2.db")
    db.initialize()
    jobs = JobService(db)
    jobs.register("settlement-review", expected_interval_seconds=3600)
    jobs.start("settlement-review")
    first = jobs.failure("settlement-review", "temporary provider error")
    assert first.consecutive_failures == 1
    assert first.retry_after_seconds == 60

    second = jobs.failure("settlement-review", "still failing")
    assert second.consecutive_failures == 2
    assert second.retry_after_seconds == 120

    success = jobs.success("settlement-review")
    assert success.consecutive_failures == 0
    assert success.last_error is None
    assert success.retry_after_seconds is None


def test_default_jobs_are_idempotent_and_report_due(tmp_path: Path):
    db = SabiDatabase(tmp_path / "v2.db")
    db.initialize()
    jobs = JobService(db)
    first = jobs.seed_defaults()
    second = jobs.seed_defaults()
    assert {job.name for job in first} == {job.name for job in second}
    names = {job.name for job in jobs.list()}
    assert "verified-backup" in names
    assert "settlement-review" in names
    assert jobs.get("verified-backup", now=datetime.now(timezone.utc)).due is True
