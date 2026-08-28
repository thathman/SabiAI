from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from sabiai.config import Settings
from sabiai.storage import SabiDatabase

from .history import NotificationHistory


@dataclass(frozen=True, slots=True)
class PushDeliveryReport:
    enabled: bool
    attempted: int
    delivered: int
    expired: int
    failed: int


class WebPushService:
    """Persist browser push subscriptions and deliver narrow Sabi Boy alerts."""

    MAX_ACTIVE_SUBSCRIPTIONS = 2000

    def __init__(
        self,
        database: SabiDatabase | str | Path,
        settings: Settings | None = None,
    ):
        self.db = database if isinstance(database, SabiDatabase) else SabiDatabase(database)
        self.settings = settings or Settings.from_env()

    @property
    def enabled(self) -> bool:
        key_file = self.settings.vapid_private_key_file
        return bool(
            self.settings.vapid_public_key
            and key_file
            and key_file.is_file()
            and self.settings.vapid_subject
        )

    def subscribe(
        self,
        *,
        endpoint: str,
        p256dh: str,
        auth: str,
        user_agent: str | None = None,
    ) -> None:
        with self.db.transaction() as conn:
            existing = conn.execute(
                "SELECT disabled_at FROM push_subscriptions WHERE endpoint=?", (endpoint,)
            ).fetchone()
            if existing is None or existing["disabled_at"] is not None:
                active = conn.execute(
                    "SELECT COUNT(*) FROM push_subscriptions WHERE disabled_at IS NULL"
                ).fetchone()[0]
                if int(active or 0) >= self.MAX_ACTIVE_SUBSCRIPTIONS:
                    raise ValueError("The dashboard push-subscription limit has been reached.")
            conn.execute(
                """INSERT INTO push_subscriptions(endpoint,p256dh,auth,user_agent)
                   VALUES(?,?,?,?)
                   ON CONFLICT(endpoint) DO UPDATE SET
                     p256dh=excluded.p256dh,
                     auth=excluded.auth,
                     user_agent=excluded.user_agent,
                     updated_at=CURRENT_TIMESTAMP,
                     disabled_at=NULL,
                     consecutive_failures=0,
                     last_error=NULL""",
                (endpoint, p256dh, auth, (user_agent or "")[:512] or None),
            )

    def unsubscribe(self, endpoint: str) -> bool:
        with self.db.transaction() as conn:
            cursor = conn.execute(
                "DELETE FROM push_subscriptions WHERE endpoint=?", (endpoint,)
            )
        return cursor.rowcount > 0

    def send(self, payload: dict[str, Any]) -> PushDeliveryReport:
        if not self.enabled:
            report = PushDeliveryReport(False, 0, 0, 0, 0)
            self._record_history(payload, report)
            return report

        from pywebpush import WebPushException, webpush

        with self.db.connect() as conn:
            rows = conn.execute(
                """SELECT endpoint,p256dh,auth
                   FROM push_subscriptions
                   WHERE disabled_at IS NULL
                   ORDER BY id"""
            ).fetchall()

        delivered = expired = failed = 0
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        key_path = str(self.settings.vapid_private_key_file)
        for row in rows:
            endpoint = row["endpoint"]
            try:
                webpush(
                    subscription_info={
                        "endpoint": endpoint,
                        "keys": {"p256dh": row["p256dh"], "auth": row["auth"]},
                    },
                    data=body,
                    vapid_private_key=key_path,
                    vapid_claims={"sub": self.settings.vapid_subject},
                    ttl=600,
                )
            except WebPushException as exc:
                status = getattr(getattr(exc, "response", None), "status_code", None)
                if status in {404, 410}:
                    expired += 1
                    self._mark_disabled(endpoint, f"push endpoint expired ({status})")
                else:
                    failed += 1
                    self._mark_failure(endpoint, self._safe_error(exc))
            except Exception as exc:
                failed += 1
                self._mark_failure(endpoint, self._safe_error(exc))
            else:
                delivered += 1
                self._mark_success(endpoint)

        report = PushDeliveryReport(True, len(rows), delivered, expired, failed)
        self._record_history(payload, report)
        return report

    def _record_history(self, payload: dict[str, Any], report: PushDeliveryReport) -> None:
        # Notification history is observability. A logging failure must never turn a
        # successful push into an application failure or expose endpoint material.
        try:
            NotificationHistory(self.db).record(
                payload,
                enabled=report.enabled,
                attempted=report.attempted,
                delivered=report.delivered,
                expired=report.expired,
                failed=report.failed,
            )
        except Exception:
            pass

    def _mark_success(self, endpoint: str) -> None:
        stamp = datetime.now(timezone.utc).isoformat()
        with self.db.transaction() as conn:
            conn.execute(
                """UPDATE push_subscriptions SET
                     last_success_at=?, consecutive_failures=0, last_error=NULL
                   WHERE endpoint=?""",
                (stamp, endpoint),
            )

    def _mark_failure(self, endpoint: str, error: str) -> None:
        stamp = datetime.now(timezone.utc).isoformat()
        with self.db.transaction() as conn:
            conn.execute(
                """UPDATE push_subscriptions SET
                     last_error_at=?, last_error=?,
                     consecutive_failures=consecutive_failures+1
                   WHERE endpoint=?""",
                (stamp, error[:500], endpoint),
            )

    def _mark_disabled(self, endpoint: str, error: str) -> None:
        stamp = datetime.now(timezone.utc).isoformat()
        with self.db.transaction() as conn:
            conn.execute(
                """UPDATE push_subscriptions SET
                     disabled_at=?, last_error_at=?, last_error=?
                   WHERE endpoint=?""",
                (stamp, stamp, error[:500], endpoint),
            )

    @staticmethod
    def _safe_error(exc: Exception) -> str:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        return f"web push delivery failed{f' ({status})' if status else ''}"
