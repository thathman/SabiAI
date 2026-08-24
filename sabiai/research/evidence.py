from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from uuid import uuid4

from sabiai.storage.sqlite import SabiDatabase


@dataclass(frozen=True, slots=True)
class Evidence:
    evidence_type: str
    summary: str
    event_id: str | None = None
    sport_id: str | None = None
    subject: str | None = None
    source_name: str | None = None
    source_url: str | None = None
    observed_at: str | None = None
    freshness_seconds: int | None = None
    reliability: str | None = None
    raw: dict | list | None = None
    id: str | None = None


class EvidenceStore:
    """Persist and reuse research evidence without coupling Sabi to one provider."""

    def __init__(self, database: SabiDatabase | str | Path):
        self.db = database if isinstance(database, SabiDatabase) else SabiDatabase(database)

    def save(self, evidence: Evidence) -> str:
        if not evidence.evidence_type.strip():
            raise ValueError("Evidence needs a type.")
        if not evidence.summary.strip():
            raise ValueError("Evidence needs a plain-language summary.")
        evidence_id = evidence.id or f"evidence_{uuid4().hex}"
        fetched_at = datetime.now(timezone.utc).isoformat()
        with self.db.transaction() as conn:
            conn.execute(
                """INSERT INTO research_evidence(
                    id, event_id, sport_id, evidence_type, subject, summary, source_name,
                    source_url, observed_at, fetched_at, freshness_seconds, reliability, raw_json
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET
                    event_id=excluded.event_id,
                    sport_id=excluded.sport_id,
                    evidence_type=excluded.evidence_type,
                    subject=excluded.subject,
                    summary=excluded.summary,
                    source_name=excluded.source_name,
                    source_url=excluded.source_url,
                    observed_at=excluded.observed_at,
                    fetched_at=excluded.fetched_at,
                    freshness_seconds=excluded.freshness_seconds,
                    reliability=excluded.reliability,
                    raw_json=excluded.raw_json""",
                (
                    evidence_id,
                    evidence.event_id,
                    evidence.sport_id,
                    evidence.evidence_type,
                    evidence.subject,
                    evidence.summary.strip(),
                    evidence.source_name,
                    evidence.source_url,
                    evidence.observed_at,
                    fetched_at,
                    evidence.freshness_seconds,
                    evidence.reliability,
                    json.dumps(evidence.raw, ensure_ascii=False) if evidence.raw is not None else None,
                ),
            )
        return evidence_id

    def for_event(self, event_id: str, *, evidence_type: str | None = None) -> list[dict]:
        sql = """SELECT id, evidence_type, subject, summary, source_name, source_url,
                        observed_at, fetched_at, freshness_seconds, reliability, raw_json
                 FROM research_evidence WHERE event_id=?"""
        params: list[object] = [event_id]
        if evidence_type:
            sql += " AND evidence_type=?"
            params.append(evidence_type)
        sql += " ORDER BY fetched_at DESC"
        with self.db.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row(row) for row in rows]

    def latest_by_type(self, event_id: str) -> dict[str, dict]:
        result: dict[str, dict] = {}
        for item in self.for_event(event_id):
            result.setdefault(item["evidence_type"], item)
        return result

    def reusable(
        self,
        event_id: str,
        evidence_type: str,
        *,
        max_age_seconds: int,
        now: datetime | None = None,
    ) -> dict | None:
        if max_age_seconds < 0:
            raise ValueError("max_age_seconds cannot be negative.")
        now = now or datetime.now(timezone.utc)
        items = self.for_event(event_id, evidence_type=evidence_type)
        for item in items:
            fetched = datetime.fromisoformat(item["fetched_at"])
            if fetched.tzinfo is None:
                fetched = fetched.replace(tzinfo=timezone.utc)
            age = int((now - fetched).total_seconds())
            if age <= max_age_seconds:
                return {**item, "age_seconds": max(age, 0)}
        return None

    @staticmethod
    def _row(row) -> dict:
        return {
            "id": row["id"],
            "evidence_type": row["evidence_type"],
            "subject": row["subject"],
            "summary": row["summary"],
            "source_name": row["source_name"],
            "source_url": row["source_url"],
            "observed_at": row["observed_at"],
            "fetched_at": row["fetched_at"],
            "freshness_seconds": row["freshness_seconds"],
            "reliability": row["reliability"],
            "raw": json.loads(row["raw_json"]) if row["raw_json"] else None,
        }
