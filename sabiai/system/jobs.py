from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sabiai.storage import SabiDatabase


@dataclass(frozen=True, slots=True)
class JobState:
    name: str
    description: str | None
    enabled: bool
    expected_interval_seconds: int | None
    last_started_at: str | None
    last_finished_at: str | None
    last_success_at: str | None
    last_error_at: str | None
    last_error: str | None
    consecutive_failures: int
    due: bool
    retry_after_seconds: int | None


class JobService:
    """Canonical lifecycle/retry bookkeeping for Sabi Boy background work."""

    def __init__(self, database: SabiDatabase | str | Path):
        self.db = database if isinstance(database, SabiDatabase) else SabiDatabase(database)

    def register(
        self,
        name: str,
        *,
        description: str | None = None,
        expected_interval_seconds: int | None = None,
        enabled: bool = True,
    ) -> JobState:
        name = self._name(name)
        if expected_interval_seconds is not None and int(expected_interval_seconds) <= 0:
            raise ValueError("expected_interval_seconds must be positive when supplied.")
        with self.db.transaction() as conn:
            conn.execute(
                """INSERT INTO jobs(name,description,enabled,expected_interval_seconds)
                   VALUES(?,?,?,?)
                   ON CONFLICT(name) DO UPDATE SET
                       description=COALESCE(excluded.description,jobs.description),
                       enabled=excluded.enabled,
                       expected_interval_seconds=COALESCE(excluded.expected_interval_seconds,jobs.expected_interval_seconds)""",
                (name, description, 1 if enabled else 0, expected_interval_seconds),
            )
        return self.get(name)

    def start(self, name: str) -> JobState:
        name = self._name(name)
        self._ensure(name)
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE jobs SET last_started_at=? WHERE name=?",
                (datetime.now(timezone.utc).isoformat(), name),
            )
        return self.get(name)

    def success(self, name: str) -> JobState:
        name = self._name(name)
        self._ensure(name)
        stamp = datetime.now(timezone.utc).isoformat()
        with self.db.transaction() as conn:
            conn.execute(
                """UPDATE jobs SET
                       last_finished_at=?, last_success_at=?, last_error=NULL,
                       consecutive_failures=0
                   WHERE name=?""",
                (stamp, stamp, name),
            )
        return self.get(name)

    def failure(self, name: str, error: str) -> JobState:
        name = self._name(name)
        self._ensure(name)
        message = str(error or "job failed").strip()
        stamp = datetime.now(timezone.utc).isoformat()
        with self.db.transaction() as conn:
            conn.execute(
                """UPDATE jobs SET
                       last_finished_at=?, last_error_at=?, last_error=?,
                       consecutive_failures=consecutive_failures+1
                   WHERE name=?""",
                (stamp, stamp, message, name),
            )
        return self.get(name)

    def set_enabled(self, name: str, enabled: bool) -> JobState:
        name = self._name(name)
        self._ensure(name)
        with self.db.transaction() as conn:
            conn.execute("UPDATE jobs SET enabled=? WHERE name=?", (1 if enabled else 0, name))
        return self.get(name)

    def get(self, name: str, *, now: datetime | None = None) -> JobState:
        name = self._name(name)
        with self.db.connect() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE name=?", (name,)).fetchone()
        if row is None:
            raise KeyError(f"Unknown job: {name}")
        return self._row(row, now=now)

    def list(self, *, enabled_only: bool = False, now: datetime | None = None) -> list[JobState]:
        sql = "SELECT * FROM jobs"
        if enabled_only:
            sql += " WHERE enabled=1"
        sql += " ORDER BY name"
        with self.db.connect() as conn:
            rows = conn.execute(sql).fetchall()
        return [self._row(row, now=now) for row in rows]

    def seed_defaults(self) -> list[JobState]:
        defaults = (
            ("verified-backup", "Verified V1/V2 SQLite snapshot and retention run.", 86400),
            ("auto-settlement", "Poll live/final event results and settle supported pending selections.", 600),
            ("settlement-review", "Review pending outcomes and settlement backlog.", 3600),
            ("source-health", "Refresh source health and stale-source awareness.", 3600),
            ("sabi-boy-daily-reflection", "Daily Sabi Boy Blog reflection automation.", 86400),
            ("sabi-boy-weekly-reflection", "Weekly Sabi Boy Blog reflection automation.", 604800),
        )
        return [
            self.register(name, description=description, expected_interval_seconds=interval)
            for name, description, interval in defaults
        ]

    def _ensure(self, name: str) -> None:
        with self.db.connect() as conn:
            exists = conn.execute("SELECT 1 FROM jobs WHERE name=?", (name,)).fetchone()
        if not exists:
            self.register(name)

    @staticmethod
    def _name(value: str) -> str:
        name = str(value or "").strip()
        if not name:
            raise ValueError("Job name cannot be empty.")
        return name

    @staticmethod
    def _parse(value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        return stamp.astimezone(timezone.utc)

    @classmethod
    def _row(cls, row, *, now: datetime | None = None) -> JobState:
        now = now or datetime.now(timezone.utc)
        interval = int(row["expected_interval_seconds"]) if row["expected_interval_seconds"] else None
        last_success = cls._parse(row["last_success_at"])
        enabled = bool(row["enabled"])
        due = bool(enabled and interval and (last_success is None or now - last_success >= timedelta(seconds=interval)))
        failures = int(row["consecutive_failures"] or 0)
        retry_after = min(3600, 60 * (2 ** min(max(failures - 1, 0), 6))) if failures else None
        return JobState(
            name=row["name"],
            description=row["description"],
            enabled=enabled,
            expected_interval_seconds=interval,
            last_started_at=row["last_started_at"],
            last_finished_at=row["last_finished_at"],
            last_success_at=row["last_success_at"],
            last_error_at=row["last_error_at"],
            last_error=row["last_error"],
            consecutive_failures=failures,
            due=due,
            retry_after_seconds=retry_after,
        )
