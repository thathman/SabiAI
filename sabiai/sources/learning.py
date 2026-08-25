from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from sabiai.storage import SabiDatabase


@dataclass(slots=True)
class LearnedSource:
    id: str
    name: str
    url: str
    kind: str
    status: str = "candidate"
    sports: list[str] = field(default_factory=list)
    capabilities: list[str] = field(default_factory=list)
    reliability: str = "unknown"
    notes: str | None = None
    discovered_at: str | None = None
    verified_at: str | None = None
    last_checked_at: str | None = None
    last_check_ok: bool | None = None
    last_error: str | None = None


class SourceLearningService:
    """Persist source discoveries so niche-sport research improves over time."""

    _statuses = {"candidate", "verified", "rejected", "retired"}
    _kinds = {"official", "federation", "league", "team", "public_endpoint", "public_web", "open_data", "news", "other"}

    def __init__(self, database: SabiDatabase | str | Path):
        self.db = database if isinstance(database, SabiDatabase) else SabiDatabase(database)

    @staticmethod
    def stable_id(url: str) -> str:
        normalized = str(url or "").strip().casefold()
        return "source_discovery_" + hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:24]

    def discover(
        self,
        *,
        name: str,
        url: str,
        kind: str = "official",
        sports: list[str] | None = None,
        capabilities: list[str] | None = None,
        reliability: str = "unknown",
        notes: str | None = None,
    ) -> LearnedSource:
        name = str(name or "").strip()
        url = str(url or "").strip()
        if not name or not url:
            raise ValueError("Source discovery needs name and URL.")
        kind = str(kind or "other").strip().casefold()
        if kind not in self._kinds:
            kind = "other"
        source_id = self.stable_id(url)
        sport_values = sorted({str(item).strip() for item in (sports or []) if str(item).strip()})
        capability_values = sorted({str(item).strip() for item in (capabilities or []) if str(item).strip()})
        with self.db.transaction() as conn:
            conn.execute(
                """INSERT INTO source_discoveries(
                       id,name,url,kind,status,sports_json,capabilities_json,reliability,notes
                   ) VALUES(?,?,?,?,'candidate',?,?,?,?)
                   ON CONFLICT(url) DO UPDATE SET
                       name=excluded.name,
                       kind=excluded.kind,
                       sports_json=excluded.sports_json,
                       capabilities_json=excluded.capabilities_json,
                       reliability=CASE
                           WHEN source_discoveries.status='verified' THEN source_discoveries.reliability
                           ELSE excluded.reliability
                       END,
                       notes=COALESCE(excluded.notes,source_discoveries.notes)""",
                (
                    source_id,
                    name,
                    url,
                    kind,
                    json.dumps(sport_values, ensure_ascii=False),
                    json.dumps(capability_values, ensure_ascii=False),
                    str(reliability or "unknown").strip(),
                    notes,
                ),
            )
        result = self.get(source_id) or self.get_by_url(url)
        if result is None:
            raise RuntimeError("Learned source could not be reloaded after discovery.")
        return result

    def verify(
        self,
        source_id: str,
        *,
        status: str = "verified",
        reliability: str | None = None,
        notes: str | None = None,
    ) -> LearnedSource:
        status = str(status or "").strip().casefold()
        if status not in self._statuses:
            raise ValueError(f"Unsupported source discovery status: {status}")
        current = self.get(source_id)
        if current is None:
            raise KeyError(f"Unknown learned source: {source_id}")
        verified_at = datetime.now(timezone.utc).isoformat() if status == "verified" else current.verified_at
        with self.db.transaction() as conn:
            conn.execute(
                """UPDATE source_discoveries
                   SET status=?, reliability=?, notes=?, verified_at=?
                   WHERE id=?""",
                (
                    status,
                    str(reliability or current.reliability or "unknown").strip(),
                    notes if notes is not None else current.notes,
                    verified_at,
                    source_id,
                ),
            )
        result = self.get(source_id)
        if result is None:
            raise RuntimeError("Learned source disappeared during verification.")
        return result

    def record_check(self, source_id: str, *, ok: bool, error: str | None = None) -> LearnedSource:
        if self.get(source_id) is None:
            raise KeyError(f"Unknown learned source: {source_id}")
        with self.db.transaction() as conn:
            conn.execute(
                """UPDATE source_discoveries
                   SET last_checked_at=?, last_check_ok=?, last_error=?
                   WHERE id=?""",
                (
                    datetime.now(timezone.utc).isoformat(),
                    1 if ok else 0,
                    None if ok else (str(error or "check failed").strip()),
                    source_id,
                ),
            )
        result = self.get(source_id)
        if result is None:
            raise RuntimeError("Learned source disappeared during check update.")
        return result

    def get(self, source_id: str) -> LearnedSource | None:
        with self.db.connect() as conn:
            row = conn.execute("SELECT * FROM source_discoveries WHERE id=?", (source_id,)).fetchone()
        return self._row(row) if row else None

    def get_by_url(self, url: str) -> LearnedSource | None:
        with self.db.connect() as conn:
            row = conn.execute("SELECT * FROM source_discoveries WHERE url=?", (str(url).strip(),)).fetchone()
        return self._row(row) if row else None

    def list(
        self,
        *,
        status: str | None = None,
        sport: str | None = None,
        capability: str | None = None,
        limit: int = 100,
    ) -> list[LearnedSource]:
        limit = max(1, min(int(limit), 1000))
        sql = "SELECT * FROM source_discoveries"
        params: list[object] = []
        if status:
            normalized = str(status).strip().casefold()
            if normalized not in self._statuses:
                raise ValueError(f"Unsupported source discovery status: {status}")
            sql += " WHERE status=?"
            params.append(normalized)
        sql += " ORDER BY CASE status WHEN 'verified' THEN 0 WHEN 'candidate' THEN 1 WHEN 'rejected' THEN 2 ELSE 3 END, COALESCE(last_checked_at,verified_at,discovered_at) DESC LIMIT ?"
        params.append(limit)
        with self.db.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        result = [self._row(row) for row in rows]
        if sport:
            target = str(sport).strip().casefold()
            result = [row for row in result if not row.sports or target in {item.casefold() for item in row.sports}]
        if capability:
            target = str(capability).strip().casefold()
            result = [row for row in result if not row.capabilities or target in {item.casefold() for item in row.capabilities}]
        return result

    def best(
        self,
        *,
        sport: str | None = None,
        capability: str | None = None,
        limit: int = 20,
    ) -> list[LearnedSource]:
        verified = self.list(status="verified", sport=sport, capability=capability, limit=limit)
        return sorted(
            verified,
            key=lambda row: (
                row.last_check_ok is False,
                row.reliability.casefold() not in {"official", "high", "strong", "primary"},
                row.name.casefold(),
            ),
        )[:limit]

    @staticmethod
    def discovery_questions(sport: str, capability: str | None = None) -> list[str]:
        subject = str(sport or "this sport").strip()
        need = str(capability or "results, schedules, participants and relevant statistics").strip()
        return [
            f"Find the official federation/governing-body site for {subject}.",
            f"Find the official league/competition site that publishes {need} for {subject}.",
            f"Check whether official team/participant pages expose {need}.",
            "Prefer public structured feeds/endpoints when they are intended for public use; otherwise use normal public pages through OpenClaw.",
            "Record candidate URL, coverage, freshness, reliability and access constraints before marking the source verified.",
        ]

    @staticmethod
    def _row(row) -> LearnedSource:
        return LearnedSource(
            id=row["id"],
            name=row["name"],
            url=row["url"],
            kind=row["kind"],
            status=row["status"],
            sports=json.loads(row["sports_json"] or "[]"),
            capabilities=json.loads(row["capabilities_json"] or "[]"),
            reliability=row["reliability"],
            notes=row["notes"],
            discovered_at=row["discovered_at"],
            verified_at=row["verified_at"],
            last_checked_at=row["last_checked_at"],
            last_check_ok=(bool(row["last_check_ok"]) if row["last_check_ok"] is not None else None),
            last_error=row["last_error"],
        )
