from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sabiai.storage.sqlite import SabiDatabase


@dataclass(frozen=True, slots=True)
class SourceHealth:
    name: str
    kind: str
    cost: str
    enabled: bool
    requests: int
    successes: int
    failures: int
    success_pct: float | None
    cache_hits: int
    paid_calls: int
    last_requested_at: str | None
    last_success_at: str | None
    last_error_at: str | None
    last_error: str | None
    state: str


class SourceHealthService:
    """Read source reliability and spend signals from V2's own fetch log."""

    def __init__(self, database: SabiDatabase | str | Path):
        self.db = database if isinstance(database, SabiDatabase) else SabiDatabase(database)

    def sources(self, *, recent_limit_per_source: int = 100) -> list[SourceHealth]:
        limit = max(1, min(int(recent_limit_per_source), 1000))
        with self.db.connect() as conn:
            source_rows = conn.execute(
                "SELECT name, kind, cost, enabled FROM sources ORDER BY name COLLATE NOCASE"
            ).fetchall()
            result = []
            for source in source_rows:
                rows = conn.execute(
                    """SELECT requested_at, cache_hit, success, paid, error
                       FROM source_fetch_log
                       WHERE source_name=?
                       ORDER BY id DESC LIMIT ?""",
                    (source["name"], limit),
                ).fetchall()
                requests = len(rows)
                successes = sum(int(row["success"] or 0) for row in rows)
                failures = requests - successes
                cache_hits = sum(int(row["cache_hit"] or 0) for row in rows)
                paid_calls = sum(
                    1
                    for row in rows
                    if int(row["paid"] or 0) and int(row["success"] or 0) and not int(row["cache_hit"] or 0)
                )
                last_requested = rows[0]["requested_at"] if rows else None
                last_success = next((row["requested_at"] for row in rows if int(row["success"] or 0)), None)
                last_error_row = next((row for row in rows if not int(row["success"] or 0)), None)
                last_error_at = last_error_row["requested_at"] if last_error_row else None
                last_error = last_error_row["error"] if last_error_row else None
                success_pct = round((successes / requests) * 100, 1) if requests else None
                state = self._state(
                    enabled=bool(source["enabled"]),
                    requests=requests,
                    success_pct=success_pct,
                    rows=rows,
                )
                result.append(
                    SourceHealth(
                        name=source["name"],
                        kind=source["kind"],
                        cost=source["cost"],
                        enabled=bool(source["enabled"]),
                        requests=requests,
                        successes=successes,
                        failures=failures,
                        success_pct=success_pct,
                        cache_hits=cache_hits,
                        paid_calls=paid_calls,
                        last_requested_at=last_requested,
                        last_success_at=last_success,
                        last_error_at=last_error_at,
                        last_error=last_error,
                        state=state,
                    )
                )
        return result

    def economy(self) -> dict:
        with self.db.connect() as conn:
            row = conn.execute(
                """SELECT
                       COUNT(*) AS requests,
                       SUM(CASE WHEN cache_hit=1 AND success=1 THEN 1 ELSE 0 END) AS cache_hits,
                       SUM(CASE WHEN paid=1 AND success=1 AND cache_hit=0 THEN 1 ELSE 0 END) AS paid_calls,
                       SUM(CASE WHEN paid=0 AND success=1 AND cache_hit=0 THEN 1 ELSE 0 END) AS free_fetches,
                       SUM(CASE WHEN success=0 THEN 1 ELSE 0 END) AS failures
                   FROM source_fetch_log"""
            ).fetchone()
        requests = int(row["requests"] or 0)
        cache_hits = int(row["cache_hits"] or 0)
        return {
            "requests": requests,
            "cache_hits": cache_hits,
            "cache_hit_pct": round((cache_hits / requests) * 100, 1) if requests else 0.0,
            "free_fetches": int(row["free_fetches"] or 0),
            "paid_calls": int(row["paid_calls"] or 0),
            "failures": int(row["failures"] or 0),
        }

    @staticmethod
    def _state(*, enabled: bool, requests: int, success_pct: float | None, rows) -> str:
        if not enabled:
            return "disabled"
        if requests == 0:
            return "not_used_yet"
        recent = list(rows[:5])
        recent_failures = sum(1 for row in recent if not int(row["success"] or 0))
        if recent and recent_failures == len(recent):
            return "down"
        if success_pct is not None and success_pct < 70:
            return "degraded"
        return "healthy"
