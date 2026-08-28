from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sabiai.storage import SabiDatabase


class NotificationHistory:
    """Read model for push events, without retaining browser endpoint secrets."""

    def __init__(self, database: SabiDatabase | str | Path):
        self.db = database if isinstance(database, SabiDatabase) else SabiDatabase(database)

    def record(
        self,
        payload: dict[str, Any],
        *,
        enabled: bool,
        attempted: int,
        delivered: int,
        expired: int,
        failed: int,
    ) -> int:
        safe_payload = _safe_payload(payload)
        with self.db.transaction() as conn:
            cursor = conn.execute(
                """INSERT INTO notification_history(
                       title,body,tag,url,payload_json,enabled,
                       attempted,delivered,expired,failed
                   ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (
                    safe_payload["title"],
                    safe_payload["body"],
                    safe_payload["tag"],
                    safe_payload["url"],
                    json.dumps(safe_payload, ensure_ascii=False, separators=(",", ":")),
                    int(bool(enabled)),
                    max(0, int(attempted)),
                    max(0, int(delivered)),
                    max(0, int(expired)),
                    max(0, int(failed)),
                ),
            )
            return int(cursor.lastrowid)

    def list(self, *, limit: int = 100, tag: str | None = None) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 500))
        where = ""
        params: list[Any] = []
        if tag and str(tag).strip():
            where = "WHERE tag=?"
            params.append(str(tag).strip()[:200])
        params.append(limit)
        with self.db.connect() as conn:
            rows = conn.execute(
                f"""SELECT id,title,body,tag,url,enabled,attempted,delivered,expired,failed,created_at
                    FROM notification_history
                    {where}
                    ORDER BY created_at DESC, id DESC
                    LIMIT ?""",
                tuple(params),
            ).fetchall()
        return [
            {
                "id": int(row["id"]),
                "title": row["title"],
                "body": row["body"],
                "tag": row["tag"],
                "url": row["url"],
                "enabled": bool(row["enabled"]),
                "attempted": int(row["attempted"] or 0),
                "delivered": int(row["delivered"] or 0),
                "expired": int(row["expired"] or 0),
                "failed": int(row["failed"] or 0),
                "created_at": row["created_at"],
            }
            for row in rows
        ]


def _safe_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Keep only user-facing notification fields; never persist endpoint/key data."""

    return {
        "title": str(payload.get("title") or "Sabi Boy notification")[:256],
        "body": str(payload.get("body") or "")[:2000],
        "tag": str(payload.get("tag") or "")[:200] or None,
        "url": str(payload.get("url") or "")[:500] or None,
        "renotify": bool(payload.get("renotify", False)),
    }
