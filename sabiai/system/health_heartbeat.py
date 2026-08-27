from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Iterable

from sabiai.config import Settings
from sabiai.notifications import PushDeliveryReport, WebPushService
from sabiai.sources import SourceHealth, SourceHealthService
from sabiai.storage import SabiDatabase
from sabiai.system.jobs import JobService, JobState
from sabiai.system.readiness import ReadinessIssue, ReadinessReport, SystemReadinessService


@dataclass(frozen=True, slots=True)
class HealthSnapshot:
    checked_at: str
    readiness: ReadinessReport
    sources: tuple[SourceHealth, ...]
    jobs: tuple[JobState, ...]
    issues: tuple[str, ...]


def collect_snapshot(
    database: SabiDatabase,
    *,
    now: datetime | None = None,
) -> HealthSnapshot:
    """Read local source/readiness state without making provider or model calls."""

    checked_at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()
    sources = tuple(SourceHealthService(database).sources())
    readiness = SystemReadinessService(database).assess(now=now)
    jobs = tuple(JobService(database).list(enabled_only=True, now=now))
    issues = tuple(build_issue_lines(sources, readiness.issues))
    return HealthSnapshot(
        checked_at=checked_at,
        readiness=readiness,
        sources=sources,
        jobs=jobs,
        issues=issues,
    )


def build_issue_lines(
    sources: Iterable[SourceHealth],
    readiness_issues: Iterable[ReadinessIssue],
) -> list[str]:
    """Return stable, concise alert lines for actionable local degradation."""

    lines: list[str] = []
    for source in sources:
        if source.state not in {"down", "degraded"}:
            continue
        detail = f" ({_safe_detail(source.last_error)})" if source.last_error else ""
        lines.append(f"Source {source.name}: {source.state}{detail}")
    for issue in readiness_issues:
        lines.append(f"{issue.area.capitalize()}: {_safe_detail(issue.message)}")
    return sorted(set(lines), key=str.casefold)


def health_digest(issues: Iterable[str]) -> str:
    canonical = "\n".join(sorted(str(item).strip() for item in issues if str(item).strip()))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest() if canonical else ""


def load_health_state(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def save_health_state(path: Path, *, digest: str, issues: Iterable[str], checked_at: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "digest": digest,
        "issues": list(issues),
        "checked_at": checked_at,
    }
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.chmod(0o600)
    temporary.replace(path)
    path.chmod(0o600)


def notification_for_change(
    previous: dict[str, Any],
    *,
    issues: tuple[str, ...],
) -> dict[str, Any] | None:
    """Create a push payload only when the actionable issue set changes."""

    digest = health_digest(issues)
    previous_digest = str(previous.get("digest") or "")
    if digest == previous_digest:
        return None
    if issues:
        return {
            "title": "Sabi Boy health warning",
            "body": "\n".join(issues)[:1200],
            "tag": "sabi-boy-health",
            "url": "/system",
            "renotify": True,
        }
    if previous_digest:
        return {
            "title": "Sabi Boy health recovered",
            "body": "Source and system checks are back within normal range.",
            "tag": "sabi-boy-health",
            "url": "/system",
            "renotify": False,
        }
    return None


def run_health_heartbeat(settings: Settings) -> dict[str, Any]:
    """Run one local health pass and optionally deliver a Web Push alert."""

    database = SabiDatabase(settings.v2_db)
    if not settings.v2_db.exists():
        database.initialize()

    jobs = JobService(database)
    jobs.register(
        "source-health",
        description="Read local source health and system readiness without provider calls.",
        expected_interval_seconds=1800,
    )
    jobs.start("source-health")
    state_path = settings.data_dir / "sabi-boy-health-state.json"
    previous = load_health_state(state_path)
    try:
        snapshot = collect_snapshot(database)
        digest = health_digest(snapshot.issues)
        push_payload = notification_for_change(previous, issues=snapshot.issues)
        delivery: PushDeliveryReport | None = None
        if push_payload is not None:
            delivery = WebPushService(database, settings).send(push_payload)
        save_health_state(
            state_path,
            digest=digest,
            issues=snapshot.issues,
            checked_at=snapshot.checked_at,
        )
        jobs.success("source-health")
    except Exception as exc:
        jobs.failure("source-health", f"{type(exc).__name__}: {str(exc)[:500]}")
        raise

    source_states = {source.name: source.state for source in snapshot.sources}
    payload: dict[str, Any] = {
        "ok": True,
        "checked_at": snapshot.checked_at,
        "readiness": snapshot.readiness.label,
        "issues": list(snapshot.issues),
        "source_states": source_states,
        "job_count": len(snapshot.jobs),
    }
    if delivery is not None:
        payload["push"] = {
            "enabled": delivery.enabled,
            "attempted": delivery.attempted,
            "delivered": delivery.delivered,
            "expired": delivery.expired,
            "failed": delivery.failed,
        }
    return payload


def _safe_detail(value: object) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    text = re.sub(
        r"(?i)(api[-_]?key|token|authorization|secret|password)(\s*[:=]\s*)[^\s,;]+",
        r"\1\2[redacted]",
        text,
    )
    text = re.sub(r"(?i)\bbearer\s+[^\s,;]+", "Bearer [redacted]", text)
    text = re.sub(r"\b(?:pmx|sbma)_[A-Za-z0-9_-]+\b", "[redacted]", text)
    return text[:500]
