from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable
from uuid import uuid4

from .sqlite import SabiDatabase


class ResearchSliceStore:
    """Durable cache and audit log for bounded daily research slices."""

    def __init__(self, database: SabiDatabase | str | Path):
        self.db = database if isinstance(database, SabiDatabase) else SabiDatabase(database)

    @staticmethod
    def cache_key(scan_date: str, scope: dict[str, str], events: Iterable[dict]) -> str:
        packet = {
            "date": scan_date,
            "scope": {key: str(scope.get(key) or "Unresolved") for key in ("sport", "country", "competition", "division")},
            "events": [
                {
                    "id": item.get("event_id"),
                    "event": item.get("event"),
                    "starts_at": item.get("starts_at"),
                    "odds": item.get("odds") or [],
                }
                for item in sorted(events, key=lambda row: (str(row.get("event_id") or ""), str(row.get("event") or "")))
            ],
        }
        digest = hashlib.sha256(json.dumps(packet, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
        return f"research-slice:{digest}"

    def get_cached(self, cache_key: str, *, now: datetime | None = None) -> dict[str, Any] | None:
        now = now or datetime.now(timezone.utc)
        with self.db.connect() as conn:
            row = conn.execute("SELECT * FROM research_slice_cache WHERE cache_key=?", (cache_key,)).fetchone()
        if not row:
            return None
        expires = _parse_dt(row["expires_at"])
        if expires <= now:
            return None
        return _cache_row(row)

    def put_cached(
        self,
        *,
        cache_key: str,
        scan_date: str,
        scope: dict[str, str],
        events: list[dict],
        recommendations: list[dict],
        model: str | None,
        usage: dict | None,
        ttl_seconds: int = 86400,
        fetched_at: datetime | None = None,
    ) -> None:
        fetched = fetched_at or datetime.now(timezone.utc)
        expires = fetched + timedelta(seconds=max(60, int(ttl_seconds)))
        with self.db.transaction() as conn:
            conn.execute(
                """INSERT INTO research_slice_cache(
                    cache_key,scan_date,sport,country,competition,division,events_json,
                    recommendations_json,model,usage_json,fetched_at,expires_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    events_json=excluded.events_json,recommendations_json=excluded.recommendations_json,
                    model=excluded.model,usage_json=excluded.usage_json,fetched_at=excluded.fetched_at,
                    expires_at=excluded.expires_at""",
                (
                    cache_key, scan_date, _scope(scope, "sport"), _scope(scope, "country"),
                    _scope(scope, "competition"), _scope(scope, "division"),
                    _json(events), _json(recommendations), model, _json(usage or {}),
                    fetched.isoformat(), expires.isoformat(),
                ),
            )

    def record_run(self, *, run_id: str, scan_date: str, scope: dict[str, str], event_count: int,
                   status: str, cache_hit: bool, events: list[dict], recommendations: list[dict],
                   source_failures: list[str] | None = None, model: str | None = None,
                   usage: dict | None = None, error: str | None = None,
                   started_at: str | None = None, finished_at: str | None = None) -> dict[str, Any]:
        row_id = f"{run_id}:{uuid4().hex[:10]}"
        with self.db.transaction() as conn:
            conn.execute(
                """INSERT INTO research_slice_runs(
                    id,run_id,scan_date,sport,country,competition,division,event_count,status,cache_hit,
                    model,events_json,recommendations_json,source_failures_json,usage_json,error,started_at,finished_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    row_id, run_id, scan_date, _scope(scope, "sport"), _scope(scope, "country"),
                    _scope(scope, "competition"), _scope(scope, "division"), int(event_count), status,
                    1 if cache_hit else 0, model, _json(events), _json(recommendations),
                    _json(source_failures or []), _json(usage or {}), error, started_at, finished_at,
                ),
            )
        return {"id": row_id, "run_id": run_id, "scan_date": scan_date, **{key: _scope(scope, key) for key in ("sport", "country", "competition", "division")},
                "event_count": int(event_count), "status": status, "cache_hit": bool(cache_hit),
                "model": model, "events": events, "recommendations": recommendations,
                "source_failures": source_failures or [], "usage": usage or {}, "error": error}

    def list_run(self, run_id: str) -> list[dict[str, Any]]:
        with self.db.connect() as conn:
            rows = conn.execute("SELECT * FROM research_slice_runs WHERE run_id=? ORDER BY sport,country,competition,division", (run_id,)).fetchall()
        return [_run_row(row) for row in rows]

    def coverage(self, run_id: str | None = None) -> dict[str, Any]:
        if run_id:
            rows = self.list_run(run_id)
        else:
            with self.db.connect() as conn:
                latest = conn.execute("SELECT run_id FROM research_slice_runs ORDER BY created_at DESC LIMIT 1").fetchone()
            rows = self.list_run(str(latest[0])) if latest else []
            run_id = rows[0]["run_id"] if rows else None
        by_sport: dict[str, dict[str, Any]] = {}
        gaps: list[dict[str, Any]] = []
        for row in rows:
            sport = row["sport"]
            bucket = by_sport.setdefault(sport, {"sport": sport, "slices": 0, "events": 0, "recommendations": 0, "cache_hits": 0, "failures": 0})
            bucket["slices"] += 1
            bucket["events"] += row["event_count"]
            bucket["recommendations"] += len(row.get("recommendations") or [])
            bucket["cache_hits"] += 1 if row.get("cache_hit") else 0
            bucket["failures"] += len(row.get("source_failures") or []) + (1 if row.get("status") == "failed" else 0)
            if row.get("status") in {"failed", "empty", "skipped_no_price"} or row.get("country") == "Unresolved" or row.get("division") == "Unresolved":
                gaps.append({key: row.get(key) for key in ("sport", "country", "competition", "division", "status", "error")})
        return {"run_id": run_id, "slices": rows, "by_sport": list(by_sport.values()), "gaps": gaps,
                "slice_count": len(rows), "cache_hits": sum(1 for row in rows if row.get("cache_hit")),
                "event_count": sum(row["event_count"] for row in rows)}

    def find_event(self, event: str, *, scan_date: str | None = None, max_age_seconds: int = 86400) -> dict[str, Any] | None:
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=max(60, int(max_age_seconds)))
        clauses = ["created_at >= ?"]
        params: list[Any] = [cutoff.isoformat()]
        if scan_date:
            clauses.append("scan_date = ?")
            params.append(scan_date)
        with self.db.connect() as conn:
            where = ["datetime(created_at) >= datetime(?)"] + clauses[1:]
            rows = conn.execute(f"SELECT * FROM research_slice_cache WHERE {' AND '.join(where)} ORDER BY fetched_at DESC", params).fetchall()
        target = _norm(event)
        for row in rows:
            events = _load(row["events_json"], [])
            for item in events:
                if _norm(str(item.get("event") or "")) == target:
                    return {"cache_hit": True, "cache": _cache_row(row), "event": item, "recommendations": _load(row["recommendations_json"], [])}
        return None


def _scope(scope: dict[str, str], key: str) -> str:
    return str(scope.get(key) or "Unresolved").strip() or "Unresolved"


def _cache_row(row) -> dict[str, Any]:
    return {"cache_key": row["cache_key"], "scan_date": row["scan_date"], "sport": row["sport"], "country": row["country"], "competition": row["competition"], "division": row["division"], "events": _load(row["events_json"], []), "recommendations": _load(row["recommendations_json"], []), "model": row["model"], "usage": _load(row["usage_json"], {}), "fetched_at": row["fetched_at"], "expires_at": row["expires_at"]}


def _run_row(row) -> dict[str, Any]:
    return {"id": row["id"], "run_id": row["run_id"], "scan_date": row["scan_date"], "sport": row["sport"], "country": row["country"], "competition": row["competition"], "division": row["division"], "event_count": int(row["event_count"] or 0), "status": row["status"], "cache_hit": bool(row["cache_hit"]), "model": row["model"], "events": _load(row["events_json"], []), "recommendations": _load(row["recommendations_json"], []), "source_failures": _load(row["source_failures_json"], []), "usage": _load(row["usage_json"], {}), "error": row["error"], "started_at": row["started_at"], "finished_at": row["finished_at"]}


def _parse_dt(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _load(value: object, default: Any) -> Any:
    try:
        parsed = json.loads(str(value or ""))
    except (TypeError, ValueError, json.JSONDecodeError):
        return default
    return parsed


def _norm(value: str) -> str:
    return "".join(char for char in value.casefold() if char.isalnum())
