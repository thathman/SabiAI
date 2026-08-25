from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from enum import IntEnum
import json
from pathlib import Path

from sabiai.sources import SourceHealthService
from sabiai.storage import SabiDatabase


class ReadinessState(IntEnum):
    READY = 0
    DEGRADED = 1
    OBSERVE_ONLY = 2
    ACTION_LOCKED = 3

    @property
    def label(self) -> str:
        return {
            self.READY: "READY",
            self.DEGRADED: "DEGRADED",
            self.OBSERVE_ONLY: "OBSERVE ONLY",
            self.ACTION_LOCKED: "ACTION LOCKED",
        }[self]


@dataclass(frozen=True, slots=True)
class ReadinessIssue:
    severity: ReadinessState
    area: str
    message: str


@dataclass(frozen=True, slots=True)
class ReadinessReport:
    state: ReadinessState
    issues: tuple[ReadinessIssue, ...]
    database_ok: bool
    bankroll_ok: bool
    stale_settlements: int
    source_states: dict[str, str]
    checked_at: str

    @property
    def label(self) -> str:
        return self.state.label

    @property
    def can_research(self) -> bool:
        return self.state < ReadinessState.ACTION_LOCKED

    @property
    def can_build_ticket(self) -> bool:
        return self.state < ReadinessState.OBSERVE_ONLY


class SystemReadinessService:
    """Turn infrastructure/data health into Sabi Boy's operational state."""

    def __init__(self, database: SabiDatabase | str | Path):
        self.db = database if isinstance(database, SabiDatabase) else SabiDatabase(database)

    def assess(
        self,
        *,
        required_capabilities: tuple[str, ...] = (),
        stale_settlement_hours: int = 24,
        now: datetime | None = None,
    ) -> ReadinessReport:
        now = now or datetime.now(timezone.utc)
        issues: list[ReadinessIssue] = []

        database_ok, database_message = self._database_integrity()
        if not database_ok:
            issues.append(
                ReadinessIssue(
                    ReadinessState.ACTION_LOCKED,
                    "database",
                    database_message,
                )
            )

        bankroll_ok, bankroll_message = self._bankroll_integrity()
        if not bankroll_ok:
            issues.append(
                ReadinessIssue(
                    ReadinessState.ACTION_LOCKED,
                    "bankroll",
                    bankroll_message,
                )
            )

        source_health = SourceHealthService(self.db).sources()
        source_states = {item.name: item.state for item in source_health}
        health_by_name = {item.name: item for item in source_health}
        registered = self._registered_sources()

        for capability in required_capabilities:
            matching = [
                row
                for row in registered
                if row["enabled"]
                and (not row["capabilities"] or capability.casefold() in row["capabilities"])
            ]
            if not matching:
                issues.append(
                    ReadinessIssue(
                        ReadinessState.OBSERVE_ONLY,
                        "sources",
                        f"No enabled source is registered for required capability '{capability}'.",
                    )
                )
                continue
            known = [health_by_name.get(row["name"]) for row in matching]
            if all(item is not None and item.state in {"down", "disabled"} for item in known):
                issues.append(
                    ReadinessIssue(
                        ReadinessState.OBSERVE_ONLY,
                        "sources",
                        f"All known sources for '{capability}' are currently unavailable.",
                    )
                )
            elif any(item is not None and item.state == "degraded" for item in known):
                issues.append(
                    ReadinessIssue(
                        ReadinessState.DEGRADED,
                        "sources",
                        f"At least one source used for '{capability}' is degraded.",
                    )
                )

        issues.extend(self._job_issues(now))
        stale_settlements = self._stale_settlements(
            now=now,
            hours=max(1, int(stale_settlement_hours)),
        )
        if stale_settlements:
            issues.append(
                ReadinessIssue(
                    ReadinessState.DEGRADED,
                    "settlement",
                    f"{stale_settlements} pending selection(s) started more than {stale_settlement_hours} hours ago and need settlement review.",
                )
            )

        state = max((issue.severity for issue in issues), default=ReadinessState.READY)
        return ReadinessReport(
            state=state,
            issues=tuple(issues),
            database_ok=database_ok,
            bankroll_ok=bankroll_ok,
            stale_settlements=stale_settlements,
            source_states=source_states,
            checked_at=now.isoformat(),
        )

    def _database_integrity(self) -> tuple[bool, str]:
        try:
            with self.db.connect() as conn:
                row = conn.execute("PRAGMA quick_check").fetchone()
            result = str(row[0]) if row else "no result"
            return result.casefold() == "ok", f"SQLite quick_check returned: {result}"
        except Exception as exc:
            return False, f"Database integrity check could not run: {exc}"

    def _bankroll_integrity(self) -> tuple[bool, str]:
        try:
            with self.db.connect() as conn:
                rows = conn.execute(
                    "SELECT id, amount, balance_after FROM bankroll_ledger ORDER BY id"
                ).fetchall()
        except Exception as exc:
            return False, f"Bankroll ledger could not be read: {exc}"

        running = Decimal("0.00")
        for row in rows:
            try:
                running += Decimal(str(row["amount"])).quantize(Decimal("0.01"))
                recorded = (
                    Decimal(str(row["balance_after"])).quantize(Decimal("0.01"))
                    if row["balance_after"] is not None
                    else None
                )
            except (InvalidOperation, ValueError, TypeError) as exc:
                return False, f"Bankroll ledger row {row['id']} contains invalid money data: {exc}"
            if recorded is not None and recorded != running:
                return (
                    False,
                    f"Bankroll ledger row {row['id']} does not reconcile: expected {running}, recorded {recorded}.",
                )
        return True, "Bankroll ledger reconciles."

    def _registered_sources(self) -> list[dict]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT name, enabled, capabilities_json FROM sources"
            ).fetchall()
        result = []
        for row in rows:
            try:
                capabilities = {
                    str(item).casefold() for item in json.loads(row["capabilities_json"] or "[]")
                }
            except (TypeError, ValueError, json.JSONDecodeError):
                capabilities = set()
            result.append(
                {
                    "name": row["name"],
                    "enabled": bool(row["enabled"]),
                    "capabilities": capabilities,
                }
            )
        return result

    def _job_issues(self, now: datetime) -> list[ReadinessIssue]:
        with self.db.connect() as conn:
            rows = conn.execute(
                """SELECT name, expected_interval_seconds, last_success_at,
                          consecutive_failures, last_error
                   FROM jobs WHERE enabled=1"""
            ).fetchall()
        issues: list[ReadinessIssue] = []
        for row in rows:
            name = str(row["name"])
            failures = int(row["consecutive_failures"] or 0)
            critical_settlement = "settle" in name.casefold() or "settlement" in name.casefold()
            if failures >= 3:
                issues.append(
                    ReadinessIssue(
                        ReadinessState.OBSERVE_ONLY if critical_settlement else ReadinessState.DEGRADED,
                        "jobs",
                        f"Job '{name}' has failed {failures} consecutive times"
                        + (f": {row['last_error']}" if row["last_error"] else "."),
                    )
                )
            interval = row["expected_interval_seconds"]
            last_success = row["last_success_at"]
            if interval and last_success:
                try:
                    stamp = datetime.fromisoformat(str(last_success).replace("Z", "+00:00"))
                    if stamp.tzinfo is None:
                        stamp = stamp.replace(tzinfo=timezone.utc)
                    stale_after = timedelta(seconds=int(interval) * 3)
                    if now - stamp > stale_after:
                        issues.append(
                            ReadinessIssue(
                                ReadinessState.DEGRADED,
                                "jobs",
                                f"Job '{name}' is overdue relative to its expected interval.",
                            )
                        )
                except (ValueError, TypeError):
                    issues.append(
                        ReadinessIssue(
                            ReadinessState.DEGRADED,
                            "jobs",
                            f"Job '{name}' has an unreadable last-success timestamp.",
                        )
                    )
        return issues

    def _stale_settlements(self, *, now: datetime, hours: int) -> int:
        cutoff = (now - timedelta(hours=hours)).isoformat()
        try:
            with self.db.connect() as conn:
                row = conn.execute(
                    """SELECT COUNT(*)
                       FROM picks_v2 p
                       JOIN events e ON e.id=p.event_id
                       WHERE p.outcome='pending' AND e.starts_at < ?""",
                    (cutoff,),
                ).fetchone()
            return int(row[0] or 0)
        except Exception:
            return 0
