from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from sabiai.storage import SabiDatabase


@dataclass(slots=True)
class PersistentResearchCase:
    id: str
    title: str
    sport: str
    event: str
    market: str | None = None
    home: str | None = None
    away: str | None = None
    event_id: str | None = None
    objective: str | None = None
    status: str = "open"
    notes: list[str] = field(default_factory=list)
    assessment: dict | None = None
    created_at: str | None = None
    updated_at: str | None = None
    last_assessed_at: str | None = None
    evidence_ids: list[str] = field(default_factory=list)


class ResearchCaseStore:
    """Durable named research cases that survive OpenClaw/session boundaries."""

    _allowed_statuses = {"open", "watch", "ready", "closed", "archived"}

    def __init__(self, database: SabiDatabase | str | Path):
        self.db = database if isinstance(database, SabiDatabase) else SabiDatabase(database)

    @staticmethod
    def stable_id(*, sport: str, event: str, market: str | None = None, objective: str | None = None) -> str:
        identity = "|".join(
            value.strip().casefold()
            for value in (sport, event, market or "", objective or "")
        )
        return "research_case_" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]

    def create(
        self,
        *,
        sport: str,
        event: str,
        market: str | None = None,
        home: str | None = None,
        away: str | None = None,
        event_id: str | None = None,
        title: str | None = None,
        objective: str | None = None,
        notes: list[str] | None = None,
        case_id: str | None = None,
    ) -> PersistentResearchCase:
        sport = str(sport or "").strip()
        event = str(event or "").strip()
        if not sport or not event:
            raise ValueError("Persistent research case needs sport and explicit event.")
        case_id = case_id or self.stable_id(sport=sport, event=event, market=market, objective=objective)
        title = str(title or f"{event}{' — ' + market if market else ''}").strip()
        payload_notes = [str(item).strip() for item in (notes or []) if str(item).strip()]
        with self.db.transaction() as conn:
            conn.execute(
                """INSERT INTO research_cases(
                       id,title,sport,event,market,home,away,event_id,objective,status,notes_json
                   ) VALUES(?,?,?,?,?,?,?,?,?,'open',?)
                   ON CONFLICT(id) DO UPDATE SET
                       title=excluded.title,
                       sport=excluded.sport,
                       event=excluded.event,
                       market=excluded.market,
                       home=COALESCE(excluded.home,research_cases.home),
                       away=COALESCE(excluded.away,research_cases.away),
                       event_id=COALESCE(excluded.event_id,research_cases.event_id),
                       objective=COALESCE(excluded.objective,research_cases.objective),
                       notes_json=CASE WHEN excluded.notes_json='[]' THEN research_cases.notes_json ELSE excluded.notes_json END,
                       updated_at=CURRENT_TIMESTAMP""",
                (
                    case_id,
                    title,
                    sport,
                    event,
                    market,
                    home,
                    away,
                    event_id,
                    objective,
                    json.dumps(payload_notes, ensure_ascii=False),
                ),
            )
        result = self.get(case_id)
        if result is None:
            raise RuntimeError("Research case could not be reloaded after create/update.")
        return result

    def get(self, case_id: str) -> PersistentResearchCase | None:
        with self.db.connect() as conn:
            row = conn.execute("SELECT * FROM research_cases WHERE id=?", (case_id,)).fetchone()
            evidence = conn.execute(
                "SELECT evidence_id FROM research_case_evidence WHERE case_id=? ORDER BY added_at,evidence_id",
                (case_id,),
            ).fetchall() if row else []
        return self._row(row, [item["evidence_id"] for item in evidence]) if row else None

    def list(
        self,
        *,
        status: str | None = None,
        limit: int = 50,
    ) -> list[PersistentResearchCase]:
        limit = max(1, min(int(limit), 500))
        sql = "SELECT * FROM research_cases"
        params: list[object] = []
        if status:
            normalized = self._status(status)
            sql += " WHERE status=?"
            params.append(normalized)
        sql += " ORDER BY updated_at DESC, created_at DESC LIMIT ?"
        params.append(limit)
        with self.db.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
            result = []
            for row in rows:
                evidence = conn.execute(
                    "SELECT evidence_id FROM research_case_evidence WHERE case_id=? ORDER BY added_at,evidence_id",
                    (row["id"],),
                ).fetchall()
                result.append(self._row(row, [item["evidence_id"] for item in evidence]))
        return result

    def update(
        self,
        case_id: str,
        *,
        status: str | None = None,
        title: str | None = None,
        objective: str | None = None,
        notes: list[str] | None = None,
        append_note: str | None = None,
        assessment: dict | None = None,
    ) -> PersistentResearchCase:
        current = self.get(case_id)
        if current is None:
            raise KeyError(f"Unknown research case: {case_id}")
        final_notes = list(current.notes)
        if notes is not None:
            final_notes = [str(item).strip() for item in notes if str(item).strip()]
        if append_note and str(append_note).strip():
            final_notes.append(str(append_note).strip())
        final_status = self._status(status) if status is not None else current.status
        final_assessment = assessment if assessment is not None else current.assessment
        now = datetime.now(timezone.utc).isoformat()
        with self.db.transaction() as conn:
            conn.execute(
                """UPDATE research_cases SET
                       title=?, objective=?, status=?, notes_json=?, assessment_json=?,
                       last_assessed_at=?, updated_at=CURRENT_TIMESTAMP
                   WHERE id=?""",
                (
                    str(title).strip() if title is not None else current.title,
                    objective if objective is not None else current.objective,
                    final_status,
                    json.dumps(final_notes, ensure_ascii=False),
                    json.dumps(final_assessment, ensure_ascii=False) if final_assessment is not None else None,
                    now if assessment is not None else current.last_assessed_at,
                    case_id,
                ),
            )
        updated = self.get(case_id)
        if updated is None:
            raise RuntimeError("Research case disappeared during update.")
        return updated

    def attach_evidence(self, case_id: str, evidence_ids: list[str]) -> PersistentResearchCase:
        if self.get(case_id) is None:
            raise KeyError(f"Unknown research case: {case_id}")
        clean_ids = [str(item).strip() for item in evidence_ids if str(item).strip()]
        with self.db.transaction() as conn:
            for evidence_id in dict.fromkeys(clean_ids):
                exists = conn.execute("SELECT 1 FROM research_evidence WHERE id=?", (evidence_id,)).fetchone()
                if not exists:
                    raise KeyError(f"Unknown research evidence: {evidence_id}")
                conn.execute(
                    "INSERT OR IGNORE INTO research_case_evidence(case_id,evidence_id) VALUES(?,?)",
                    (case_id, evidence_id),
                )
            conn.execute("UPDATE research_cases SET updated_at=CURRENT_TIMESTAMP WHERE id=?", (case_id,))
        result = self.get(case_id)
        if result is None:
            raise RuntimeError("Research case could not be reloaded after evidence attachment.")
        return result

    def evidence(self, case_id: str) -> list[dict]:
        with self.db.connect() as conn:
            rows = conn.execute(
                """SELECT e.*
                   FROM research_case_evidence ce
                   JOIN research_evidence e ON e.id=ce.evidence_id
                   WHERE ce.case_id=?
                   ORDER BY COALESCE(e.observed_at,e.fetched_at) DESC, e.id""",
                (case_id,),
            ).fetchall()
        result = []
        for row in rows:
            result.append(
                {
                    "id": row["id"],
                    "event_id": row["event_id"],
                    "sport_id": row["sport_id"],
                    "evidence_type": row["evidence_type"],
                    "subject": row["subject"],
                    "summary": row["summary"],
                    "source_name": row["source_name"],
                    "source_url": row["source_url"],
                    "observed_at": row["observed_at"],
                    "fetched_at": row["fetched_at"],
                    "freshness_seconds": row["freshness_seconds"],
                    "reliability": row["reliability"],
                    "raw": json.loads(row["raw_json"] or "{}"),
                }
            )
        return result

    @classmethod
    def _status(cls, value: str) -> str:
        status = str(value or "").strip().casefold().replace("_", " ")
        aliases = {"watching": "watch", "done": "closed", "complete": "closed"}
        status = aliases.get(status, status)
        if status not in cls._allowed_statuses:
            raise ValueError(f"Unsupported research case status: {value}")
        return status

    @staticmethod
    def _row(row, evidence_ids: list[str]) -> PersistentResearchCase:
        return PersistentResearchCase(
            id=row["id"],
            title=row["title"],
            sport=row["sport"],
            event=row["event"],
            market=row["market"],
            home=row["home"],
            away=row["away"],
            event_id=row["event_id"],
            objective=row["objective"],
            status=row["status"],
            notes=json.loads(row["notes_json"] or "[]"),
            assessment=json.loads(row["assessment_json"]) if row["assessment_json"] else None,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            last_assessed_at=row["last_assessed_at"],
            evidence_ids=evidence_ids,
        )
