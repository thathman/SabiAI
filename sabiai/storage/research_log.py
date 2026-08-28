from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .sqlite import SabiDatabase


class DailyResearchLog:
    """Canonical read model for direct daily scans and recommendations."""

    def __init__(self, database: SabiDatabase | str | Path):
        self.db = database if isinstance(database, SabiDatabase) else SabiDatabase(database)

    def save(self, report: dict[str, Any]) -> dict[str, Any]:
        run_key = str(report.get("run_id") or report.get("generated_at") or "").strip()
        if not run_key:
            raise ValueError("Daily research report needs run_id or generated_at.")
        with self.db.transaction() as conn:
            conn.execute(
                """INSERT INTO daily_research_runs(
                       run_key,scan_date,generated_at,model,events_considered,
                       source_failures_json,recommendations_json,notes_json,usage_json,push_json
                   ) VALUES(?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(run_key) DO UPDATE SET
                       scan_date=excluded.scan_date,
                       generated_at=excluded.generated_at,
                       model=excluded.model,
                       events_considered=excluded.events_considered,
                       source_failures_json=excluded.source_failures_json,
                       recommendations_json=excluded.recommendations_json,
                       notes_json=excluded.notes_json,
                       usage_json=excluded.usage_json,
                       push_json=excluded.push_json""",
                (
                    run_key,
                    str(report.get("date") or ""),
                    str(report.get("generated_at") or ""),
                    str(report.get("model") or "") or None,
                    int(report.get("events_considered") or 0),
                    _json(report.get("source_failures") or []),
                    _json(report.get("recommendations") or []),
                    _json(report.get("notes") or []),
                    _json(report.get("usage") or {}),
                    _json(report.get("push") or {}),
                ),
            )
        return self.get(run_key) or {}

    def latest(self) -> dict[str, Any] | None:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM daily_research_runs ORDER BY generated_at DESC, id DESC LIMIT 1"
            ).fetchone()
        return self._row(row) if row else None

    def list(self, limit: int = 20) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 100))
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM daily_research_runs ORDER BY generated_at DESC, id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._row(row) for row in rows]

    def get(self, run_key: str) -> dict[str, Any] | None:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM daily_research_runs WHERE run_key=?", (run_key,)
            ).fetchone()
        return self._row(row) if row else None

    def context(self, limit: int = 5) -> dict[str, Any]:
        rows = self.list(limit)
        return {
            "latest": rows[0] if rows else None,
            "recent_scans": rows,
            "note": (
                "These are direct system scans, not placed wagers. Recommendations are observations to verify "
                "with fresh prices and research before ticket work."
            ),
        }

    @staticmethod
    def _row(row) -> dict[str, Any]:
        return {
            "run_id": row["run_key"],
            "date": row["scan_date"],
            "generated_at": row["generated_at"],
            "model": row["model"],
            "events_considered": int(row["events_considered"] or 0),
            "source_failures": _load(row["source_failures_json"], []),
            "recommendations": _load(row["recommendations_json"], []),
            "notes": _load(row["notes_json"], []),
            "usage": _load(row["usage_json"], {}),
            "push": _load(row["push_json"], {}),
        }


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _load(value: object, default: Any) -> Any:
    try:
        parsed = json.loads(str(value or ""))
    except (TypeError, ValueError, json.JSONDecodeError):
        return default
    return parsed
