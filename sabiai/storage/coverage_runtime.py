from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from typing import Any

from .coverage import CoverageStore as BaseCoverageStore, _iso, _json


class CoverageStore(BaseCoverageStore):
    """V2.4 hardened coverage store.

    Provider event identifiers are source-scoped stable identities and are checked before
    fuzzy participant/time matching. Radar pricing telemetry is freshness-aware while the
    longer market catalogue/history remains available for audit and learning.
    """

    DEFAULT_PRICE_MAX_AGE_SECONDS = 7200

    def upsert_event(
        self,
        event: dict[str, Any],
        *,
        source_name: str,
        provider_sport_key: str | None = None,
        source_payload: object | None = None,
        now: datetime | None = None,
    ) -> str:
        now = now or datetime.now(timezone.utc)
        source_event_id = str(event.get("event_id") or "").strip() or None
        if source_event_id:
            with self.database.connect() as conn:
                row = conn.execute(
                    """SELECT event_id FROM coverage_event_sources
                       WHERE source_name=? AND source_event_id=?
                       ORDER BY last_seen_at DESC LIMIT 1""",
                    (source_name, source_event_id),
                ).fetchone()
            if row:
                event_id = str(row["event_id"])
                self._refresh_known_event(
                    event_id,
                    event,
                    source_name=source_name,
                    source_event_id=source_event_id,
                    provider_sport_key=provider_sport_key,
                    source_payload=source_payload,
                    now=now,
                )
                return event_id
        return super().upsert_event(
            event,
            source_name=source_name,
            provider_sport_key=provider_sport_key,
            source_payload=source_payload,
            now=now,
        )

    def _refresh_known_event(
        self,
        event_id: str,
        event: dict[str, Any],
        *,
        source_name: str,
        source_event_id: str,
        provider_sport_key: str | None,
        source_payload: object | None,
        now: datetime,
    ) -> None:
        event_name = str(event.get("event") or event.get("event_name") or "").strip()
        if not event_name:
            raise ValueError("Coverage event needs an explicit event name.")
        with self.database.transaction() as conn:
            conn.execute(
                """UPDATE coverage_events SET
                       competition=COALESCE(?,competition),
                       country=COALESCE(?,country),
                       division=COALESCE(?,division),
                       event_name=?,
                       home=COALESCE(?,home),
                       away=COALESCE(?,away),
                       starts_at=COALESCE(?,starts_at),
                       status=?,
                       last_seen_at=?
                   WHERE id=?""",
                (
                    event.get("competition"),
                    event.get("country"),
                    event.get("division"),
                    event_name,
                    event.get("home"),
                    event.get("away"),
                    _iso(event.get("starts_at")),
                    str(event.get("status") or "scheduled"),
                    now.isoformat(),
                    event_id,
                ),
            )
            conn.execute(
                """UPDATE coverage_event_sources SET
                       provider_sport_key=COALESCE(?,provider_sport_key),
                       source_event_name=?,
                       source_payload_json=?,
                       last_seen_at=?
                   WHERE event_id=? AND source_name=?""",
                (
                    provider_sport_key,
                    event_name,
                    _json(source_payload if source_payload is not None else event),
                    now.isoformat(),
                    event_id,
                    source_name,
                ),
            )

    def radar(
        self,
        *,
        now: datetime | None = None,
        horizon_hours: int = 72,
        sport: str | None = None,
        limit: int = 500,
        priced_only: bool = False,
        max_price_age_seconds: int = DEFAULT_PRICE_MAX_AGE_SECONDS,
    ) -> list[dict[str, Any]]:
        now = now or datetime.now(timezone.utc)
        rows = super().radar(
            now=now,
            horizon_hours=horizon_hours,
            sport=sport,
            limit=limit,
            priced_only=False,
        )
        if not rows:
            return []
        cutoff = (now.astimezone(timezone.utc) - timedelta(seconds=max(60, int(max_price_age_seconds)))).isoformat()
        ids = [str(row["id"]) for row in rows]
        placeholders = ",".join("?" for _ in ids)
        with self.database.connect() as conn:
            fresh_rows = conn.execute(
                f"""SELECT event_id,COUNT(*) AS observations,COUNT(DISTINCT family) AS families,
                           COUNT(DISTINCT COALESCE(bookmaker,source_name)) AS bookmakers,
                           MAX(observed_at) AS latest_price_at
                    FROM coverage_market_offers
                    WHERE event_id IN ({placeholders}) AND observed_at>=?
                    GROUP BY event_id""",
                (*ids, cutoff),
            ).fetchall()
        fresh = {str(row["event_id"]): dict(row) for row in fresh_rows}
        output = []
        for row in rows:
            current = fresh.get(str(row["id"]), {})
            row = dict(row)
            row["offer_observation_count"] = int(current.get("observations") or 0)
            row["priced_family_count"] = int(current.get("families") or 0)
            row["fresh_bookmaker_count"] = int(current.get("bookmakers") or 0)
            row["latest_price_at"] = current.get("latest_price_at")
            if priced_only and row["offer_observation_count"] <= 0:
                continue
            output.append(row)
        return output

    def current_counts(
        self,
        *,
        now: datetime | None = None,
        horizon_hours: int = 72,
        max_price_age_seconds: int = DEFAULT_PRICE_MAX_AGE_SECONDS,
    ) -> dict[str, int]:
        now = now or datetime.now(timezone.utc)
        rows = self.radar(
            now=now,
            horizon_hours=horizon_hours,
            limit=5000,
            max_price_age_seconds=max_price_age_seconds,
        )
        ids = [str(row["id"]) for row in rows]
        if not ids:
            return {"events": 0, "priced_events": 0, "market_catalogue": 0, "market_offers": 0}
        placeholders = ",".join("?" for _ in ids)
        cutoff = (now.astimezone(timezone.utc) - timedelta(seconds=max(60, int(max_price_age_seconds)))).isoformat()
        with self.database.connect() as conn:
            catalogue = conn.execute(
                f"SELECT COUNT(*) FROM coverage_market_catalogue WHERE event_id IN ({placeholders})",
                ids,
            ).fetchone()[0]
            offers = conn.execute(
                f"SELECT COUNT(*) FROM coverage_market_offers WHERE event_id IN ({placeholders}) AND observed_at>=?",
                (*ids, cutoff),
            ).fetchone()[0]
        return {
            "events": len(ids),
            "priced_events": sum(1 for row in rows if int(row.get("offer_observation_count") or 0) > 0),
            "market_catalogue": int(catalogue or 0),
            "market_offers": int(offers or 0),
        }
