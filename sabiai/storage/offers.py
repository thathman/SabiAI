from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

from .sqlite import SabiDatabase


@dataclass(frozen=True, slots=True)
class OfferObservation:
    id: str
    target_bookmaker_slug: str
    sport: str | None
    event: str
    home: str | None
    away: str | None
    event_ref: str | None
    market: str
    market_ref: str | None
    decimal_odds: str
    observed_at: str
    ingested_at: str
    source: str
    source_draft_id: str | None
    raw: dict


class OfferObservationStore:
    """Audit trail for bookmaker prices observed by browser/adapters before conversion."""

    def __init__(self, database: SabiDatabase | str | Path):
        self.db = database if isinstance(database, SabiDatabase) else SabiDatabase(database)

    def save(
        self,
        *,
        target_bookmaker_slug: str,
        event: str,
        market: str,
        decimal_odds: str,
        observed_at: str,
        source: str,
        sport: str | None = None,
        home: str | None = None,
        away: str | None = None,
        event_ref: str | None = None,
        market_ref: str | None = None,
        source_draft_id: str | None = None,
        raw: dict | None = None,
    ) -> OfferObservation:
        identity = "|".join(
            str(value or "").strip().casefold()
            for value in (
                target_bookmaker_slug,
                event_ref or event,
                market_ref or market,
                decimal_odds,
                observed_at,
                source,
            )
        )
        observation_id = f"offer_{hashlib.sha256(identity.encode('utf-8')).hexdigest()[:32]}"
        payload = raw or {}
        with self.db.transaction() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO bookmaker_offer_observations(
                       id,target_bookmaker_slug,sport,event,home,away,event_ref,
                       market,market_ref,decimal_odds,observed_at,source,source_draft_id,raw_json
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    observation_id,
                    target_bookmaker_slug,
                    sport,
                    event,
                    home,
                    away,
                    event_ref,
                    market,
                    market_ref,
                    decimal_odds,
                    observed_at,
                    source,
                    source_draft_id,
                    json.dumps(payload, ensure_ascii=False),
                ),
            )
        saved = self.get(observation_id)
        if saved is None:
            raise RuntimeError("Bookmaker offer observation could not be reloaded after save.")
        return saved

    def get(self, observation_id: str) -> OfferObservation | None:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM bookmaker_offer_observations WHERE id=?", (observation_id,)
            ).fetchone()
        return self._row(row) if row else None

    def recent(
        self,
        *,
        bookmaker_slug: str | None = None,
        limit: int = 100,
    ) -> list[OfferObservation]:
        limit = max(1, min(int(limit), 1000))
        sql = "SELECT * FROM bookmaker_offer_observations"
        params: list[object] = []
        if bookmaker_slug:
            sql += " WHERE target_bookmaker_slug=?"
            params.append(bookmaker_slug)
        sql += " ORDER BY observed_at DESC, ingested_at DESC LIMIT ?"
        params.append(limit)
        with self.db.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row(row) for row in rows]

    @staticmethod
    def _row(row) -> OfferObservation:
        return OfferObservation(
            id=row["id"],
            target_bookmaker_slug=row["target_bookmaker_slug"],
            sport=row["sport"],
            event=row["event"],
            home=row["home"],
            away=row["away"],
            event_ref=row["event_ref"],
            market=row["market"],
            market_ref=row["market_ref"],
            decimal_odds=row["decimal_odds"],
            observed_at=row["observed_at"],
            ingested_at=row["ingested_at"],
            source=row["source"],
            source_draft_id=row["source_draft_id"],
            raw=json.loads(row["raw_json"] or "{}"),
        )
