from __future__ import annotations

from dataclasses import dataclass
import json
from uuid import uuid4

from .sqlite import SabiDatabase


@dataclass(frozen=True, slots=True)
class TicketDraft:
    id: str
    parent_draft_id: str | None
    source_type: str
    source_reference: str | None
    source_bookmaker_slug: str | None
    target_bookmaker_slug: str | None
    status: str
    payload: dict
    issues: list[dict]
    created_at: str
    updated_at: str


class TicketDraftStore:
    """Persist unresolved/imported ticket versions before canonical event resolution."""

    def __init__(self, database: SabiDatabase):
        self.database = database

    def create(
        self,
        payload: dict,
        *,
        source_type: str,
        source_reference: str | None = None,
        source_bookmaker_slug: str | None = None,
        target_bookmaker_slug: str | None = None,
        status: str = "draft",
        issues: list[dict] | None = None,
        parent_draft_id: str | None = None,
        draft_id: str | None = None,
    ) -> TicketDraft:
        if not isinstance(payload, dict):
            raise ValueError("Ticket draft payload must be an object.")
        if not source_type.strip():
            raise ValueError("Ticket draft needs a source_type.")
        if parent_draft_id and self.get(parent_draft_id) is None:
            raise ValueError("Parent ticket draft does not exist.")

        draft_id = draft_id or f"draft_{uuid4().hex}"
        with self.database.transaction() as conn:
            conn.execute(
                """INSERT INTO ticket_drafts(
                       id,parent_draft_id,source_type,source_reference,
                       source_bookmaker_slug,target_bookmaker_slug,status,
                       payload_json,issues_json
                   ) VALUES(?,?,?,?,?,?,?,?,?)""",
                (
                    draft_id,
                    parent_draft_id,
                    source_type,
                    source_reference,
                    source_bookmaker_slug,
                    target_bookmaker_slug,
                    status,
                    json.dumps(payload, ensure_ascii=False),
                    json.dumps(issues or [], ensure_ascii=False),
                ),
            )
        draft = self.get(draft_id)
        if draft is None:
            raise RuntimeError("Ticket draft could not be reloaded after creation.")
        return draft

    def revise(
        self,
        draft_id: str,
        payload: dict,
        *,
        issues: list[dict] | None = None,
        status: str = "draft",
        target_bookmaker_slug: str | None = None,
    ) -> TicketDraft:
        parent = self.get(draft_id)
        if parent is None:
            raise KeyError(f"Unknown ticket draft: {draft_id}")
        return self.create(
            payload,
            source_type="revision",
            source_reference=parent.source_reference,
            source_bookmaker_slug=parent.source_bookmaker_slug,
            target_bookmaker_slug=target_bookmaker_slug or parent.target_bookmaker_slug,
            status=status,
            issues=issues,
            parent_draft_id=parent.id,
        )

    def get(self, draft_id: str) -> TicketDraft | None:
        with self.database.connect() as conn:
            row = conn.execute(
                "SELECT * FROM ticket_drafts WHERE id=?",
                (draft_id,),
            ).fetchone()
        return self._row(row) if row else None

    def recent(self, limit: int = 25) -> list[TicketDraft]:
        limit = max(1, min(int(limit), 250))
        with self.database.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM ticket_drafts ORDER BY created_at DESC, id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._row(row) for row in rows]

    def lineage(self, draft_id: str) -> list[TicketDraft]:
        current = self.get(draft_id)
        if current is None:
            return []
        lineage = [current]
        seen = {current.id}
        while current.parent_draft_id:
            if current.parent_draft_id in seen:
                raise RuntimeError("Ticket draft lineage contains a cycle.")
            current = self.get(current.parent_draft_id)
            if current is None:
                break
            lineage.append(current)
            seen.add(current.id)
        lineage.reverse()
        return lineage

    @staticmethod
    def _row(row) -> TicketDraft:
        return TicketDraft(
            id=row["id"],
            parent_draft_id=row["parent_draft_id"],
            source_type=row["source_type"],
            source_reference=row["source_reference"],
            source_bookmaker_slug=row["source_bookmaker_slug"],
            target_bookmaker_slug=row["target_bookmaker_slug"],
            status=row["status"],
            payload=json.loads(row["payload_json"] or "{}"),
            issues=json.loads(row["issues_json"] or "[]"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
