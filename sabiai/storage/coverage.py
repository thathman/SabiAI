from __future__ import annotations

from collections import defaultdict, deque
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import re
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from .sqlite import SabiDatabase


_WORDS = re.compile(r"[^a-z0-9]+")


def _norm(value: object) -> str:
    return _WORDS.sub("", str(value or "").casefold())


def _utc(value: object) -> datetime | None:
    if value is None or not str(value).strip():
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        number = float(value)
        if number > 100_000_000_000:
            number /= 1000
        try:
            return datetime.fromtimestamp(number, timezone.utc)
        except (ValueError, OSError, OverflowError):
            return None
    text = str(value).strip()
    if text.isdigit():
        return _utc(float(text))
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = datetime.combine(date.fromisoformat(text), datetime.min.time())
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _iso(value: object) -> str | None:
    parsed = _utc(value)
    return parsed.isoformat() if parsed else (str(value).strip() or None if value is not None else None)


def _json(value: object) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False, separators=(",", ":"))


class CoverageStore:
    """Persistent discovery radar, provider identity map and market inventory.

    This is intentionally separate from settled/pick history. An event can be visible here
    without ever becoming a recommendation, ticket or ledger record.
    """

    def __init__(self, database: SabiDatabase):
        self.database = database

    def resolve_event_id(self, event: dict[str, Any]) -> str:
        sport = str(event.get("sport") or "unknown").strip().casefold()
        home = _norm(event.get("home"))
        away = _norm(event.get("away"))
        name = _norm(event.get("event") or event.get("event_name"))
        starts = _utc(event.get("starts_at"))
        if starts:
            lower = (starts - timedelta(minutes=30)).isoformat()
            upper = (starts + timedelta(minutes=30)).isoformat()
            with self.database.connect() as conn:
                rows = conn.execute(
                    """SELECT id,event_name,home,away,starts_at FROM coverage_events
                       WHERE sport=? AND starts_at BETWEEN ? AND ?""",
                    (sport, lower, upper),
                ).fetchall()
            for row in rows:
                row_home = _norm(row["home"])
                row_away = _norm(row["away"])
                row_name = _norm(row["event_name"])
                if home and away and row_home == home and row_away == away:
                    return str(row["id"])
                if name and row_name == name:
                    return str(row["id"])
        minute = starts.replace(second=0, microsecond=0).isoformat() if starts else "unknown-time"
        participants = f"{home}|{away}" if home or away else name
        digest = hashlib.sha256(f"{sport}|{participants}|{minute}".encode()).hexdigest()[:28]
        return f"coverage-event:{digest}"

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
        event_id = self.resolve_event_id(event)
        event_name = str(event.get("event") or event.get("event_name") or "").strip()
        if not event_name:
            raise ValueError("Coverage event needs an explicit event name.")
        sport = str(event.get("sport") or "unknown").strip().casefold()
        starts_at = _iso(event.get("starts_at"))
        with self.database.transaction() as conn:
            conn.execute(
                """INSERT INTO coverage_events(
                       id,sport,competition,country,division,event_name,home,away,starts_at,status,first_seen_at,last_seen_at
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET
                       competition=COALESCE(excluded.competition,coverage_events.competition),
                       country=COALESCE(excluded.country,coverage_events.country),
                       division=COALESCE(excluded.division,coverage_events.division),
                       event_name=excluded.event_name,
                       home=COALESCE(excluded.home,coverage_events.home),
                       away=COALESCE(excluded.away,coverage_events.away),
                       starts_at=COALESCE(excluded.starts_at,coverage_events.starts_at),
                       status=excluded.status,
                       last_seen_at=excluded.last_seen_at""",
                (
                    event_id,
                    sport,
                    event.get("competition"),
                    event.get("country"),
                    event.get("division"),
                    event_name,
                    event.get("home"),
                    event.get("away"),
                    starts_at,
                    str(event.get("status") or "scheduled"),
                    now.isoformat(),
                    now.isoformat(),
                ),
            )
            conn.execute(
                """INSERT INTO coverage_event_sources(
                       event_id,source_name,source_event_id,provider_sport_key,source_event_name,source_payload_json,first_seen_at,last_seen_at
                   ) VALUES(?,?,?,?,?,?,?,?)
                   ON CONFLICT(event_id,source_name) DO UPDATE SET
                       source_event_id=COALESCE(excluded.source_event_id,coverage_event_sources.source_event_id),
                       provider_sport_key=COALESCE(excluded.provider_sport_key,coverage_event_sources.provider_sport_key),
                       source_event_name=excluded.source_event_name,
                       source_payload_json=excluded.source_payload_json,
                       last_seen_at=excluded.last_seen_at""",
                (
                    event_id,
                    source_name,
                    str(event.get("event_id") or "").strip() or None,
                    provider_sport_key,
                    event_name,
                    _json(source_payload if source_payload is not None else event),
                    now.isoformat(),
                    now.isoformat(),
                ),
            )
        return event_id

    def event_sources(self, event_id: str) -> list[dict[str, Any]]:
        with self.database.connect() as conn:
            rows = conn.execute(
                """SELECT source_name,source_event_id,provider_sport_key,source_event_name,
                          first_seen_at,last_seen_at
                   FROM coverage_event_sources WHERE event_id=? ORDER BY source_name""",
                (event_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def upsert_market(self, event_id: str, market: dict[str, Any]) -> str:
        source_name = str(market.get("source_name") or "unknown").strip()
        family = str(market.get("family") or "other").strip().casefold()
        label = str(market.get("market_label") or market.get("source_market_key") or family).strip()
        fingerprint = "|".join(
            str(market.get(key) or "")
            for key in (
                "bookmaker",
                "source_market_key",
                "source_market_id",
                "family",
                "metric",
                "period",
                "participant",
                "line",
                "market_label",
            )
        )
        digest = hashlib.sha256(f"{event_id}|{source_name}|{fingerprint}".encode()).hexdigest()[:30]
        catalogue_id = f"coverage-market:{digest}"
        now = datetime.now(timezone.utc).isoformat()
        with self.database.transaction() as conn:
            conn.execute(
                """INSERT INTO coverage_market_catalogue(
                       id,event_id,source_name,bookmaker,source_market_key,source_market_id,family,metric,period,
                       participant,line,market_label,first_seen_at,last_seen_at,metadata_json
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET
                       bookmaker=excluded.bookmaker,
                       family=excluded.family,metric=excluded.metric,period=excluded.period,
                       participant=excluded.participant,line=excluded.line,market_label=excluded.market_label,
                       last_seen_at=excluded.last_seen_at,metadata_json=excluded.metadata_json""",
                (
                    catalogue_id,
                    event_id,
                    source_name,
                    market.get("bookmaker"),
                    market.get("source_market_key"),
                    market.get("source_market_id"),
                    family,
                    market.get("metric"),
                    market.get("period"),
                    market.get("participant"),
                    market.get("line"),
                    label,
                    now,
                    now,
                    _json(market.get("metadata") or {}),
                ),
            )
        return catalogue_id

    def record_offer(self, event_id: str, offer: dict[str, Any]) -> int:
        price = float(offer.get("decimal_odds") or 0)
        if price <= 1:
            raise ValueError("Coverage market offer needs decimal_odds > 1.0.")
        catalogue_id = offer.get("catalogue_id") or self.upsert_market(event_id, offer)
        observed_at = _iso(offer.get("observed_at")) or datetime.now(timezone.utc).isoformat()
        with self.database.transaction() as conn:
            cursor = conn.execute(
                """INSERT INTO coverage_market_offers(
                       event_id,catalogue_id,source_name,bookmaker,source_market_key,source_market_id,source_outcome_id,
                       family,metric,period,participant,side,line,selection_label,decimal_odds,observed_at,
                       source_last_update,rule_fingerprint,metadata_json
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    event_id,
                    catalogue_id,
                    str(offer.get("source_name") or "unknown"),
                    offer.get("bookmaker"),
                    offer.get("source_market_key"),
                    offer.get("source_market_id"),
                    offer.get("source_outcome_id"),
                    str(offer.get("family") or "other").casefold(),
                    offer.get("metric"),
                    offer.get("period"),
                    offer.get("participant"),
                    offer.get("side"),
                    offer.get("line"),
                    str(offer.get("selection_label") or "").strip(),
                    price,
                    observed_at,
                    _iso(offer.get("source_last_update")),
                    offer.get("rule_fingerprint"),
                    _json(offer.get("metadata") or {}),
                ),
            )
            return int(cursor.lastrowid)

    def prune_offers(self, *, keep_days: int = 21) -> int:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=max(1, keep_days))).isoformat()
        with self.database.transaction() as conn:
            cursor = conn.execute("DELETE FROM coverage_market_offers WHERE observed_at < ?", (cutoff,))
            return int(cursor.rowcount or 0)

    def market_inventory(self, event_id: str, *, max_age_seconds: int = 21600) -> dict[str, Any]:
        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=max(1, max_age_seconds))).isoformat()
        with self.database.connect() as conn:
            event = conn.execute("SELECT * FROM coverage_events WHERE id=?", (event_id,)).fetchone()
            catalogue = conn.execute(
                """SELECT * FROM coverage_market_catalogue WHERE event_id=?
                   ORDER BY family,market_label,bookmaker""",
                (event_id,),
            ).fetchall()
            offers = conn.execute(
                """WITH ranked AS (
                       SELECT o.*,
                              ROW_NUMBER() OVER (
                                  PARTITION BY event_id,COALESCE(bookmaker,''),family,COALESCE(metric,''),COALESCE(period,''),
                                               COALESCE(participant,''),COALESCE(side,''),COALESCE(line,-999999),selection_label
                                  ORDER BY observed_at DESC,id DESC
                              ) AS rn
                       FROM coverage_market_offers o
                       WHERE event_id=? AND observed_at>=?
                   ) SELECT * FROM ranked WHERE rn=1 ORDER BY family,bookmaker,selection_label""",
                (event_id, cutoff),
            ).fetchall()
        return {
            "event": dict(event) if event else None,
            "sources": self.event_sources(event_id) if event else [],
            "catalogue": [self._decode_market_row(row) for row in catalogue],
            "offers": [self._decode_offer_row(row) for row in offers],
        }

    def radar(
        self,
        *,
        now: datetime | None = None,
        horizon_hours: int = 72,
        sport: str | None = None,
        limit: int = 500,
        priced_only: bool = False,
    ) -> list[dict[str, Any]]:
        now = now or datetime.now(timezone.utc)
        start = now.astimezone(timezone.utc).isoformat()
        end = (now.astimezone(timezone.utc) + timedelta(hours=max(1, horizon_hours))).isoformat()
        where = ["e.starts_at IS NOT NULL", "e.starts_at>=?", "e.starts_at<=?"]
        params: list[Any] = [start, end]
        if sport:
            where.append("e.sport=?")
            params.append(str(sport).casefold())
        params.append(max(1, min(int(limit), 5000)))
        with self.database.connect() as conn:
            rows = conn.execute(
                f"""SELECT e.*,
                           (SELECT COUNT(*) FROM coverage_event_sources s WHERE s.event_id=e.id) AS source_count,
                           (SELECT COUNT(*) FROM coverage_market_catalogue c WHERE c.event_id=e.id) AS market_count,
                           (SELECT COUNT(DISTINCT c.family) FROM coverage_market_catalogue c WHERE c.event_id=e.id) AS market_family_count,
                           (SELECT COUNT(DISTINCT COALESCE(c.bookmaker,c.source_name)) FROM coverage_market_catalogue c WHERE c.event_id=e.id) AS bookmaker_count,
                           (SELECT COUNT(*) FROM coverage_market_offers o WHERE o.event_id=e.id) AS offer_observation_count,
                           (SELECT COUNT(DISTINCT o.family) FROM coverage_market_offers o WHERE o.event_id=e.id) AS priced_family_count
                    FROM coverage_events e
                    WHERE {' AND '.join(where)}
                    ORDER BY e.starts_at,e.sport,e.event_name LIMIT ?""",
                tuple(params),
            ).fetchall()
        result = [dict(row) for row in rows]
        if priced_only:
            result = [row for row in result if int(row.get("offer_observation_count") or 0) > 0]
        return result

    def research_candidates(
        self,
        scan_date: str,
        *,
        timezone_name: str = "Africa/Lagos",
        limit: int = 120,
    ) -> list[dict[str, Any]]:
        try:
            zone = ZoneInfo(timezone_name)
        except Exception:
            zone = timezone.utc
        day = date.fromisoformat(scan_date)
        start_local = datetime.combine(day, datetime.min.time(), zone)
        end_local = start_local + timedelta(days=1)
        rows = self.radar(
            now=start_local.astimezone(timezone.utc),
            horizon_hours=25,
            limit=5000,
        )
        eligible: list[dict[str, Any]] = []
        for row in rows:
            starts = _utc(row.get("starts_at"))
            if not starts or starts.astimezone(zone).date() != day:
                continue
            inventory = self.market_inventory(str(row["id"]), max_age_seconds=86400)
            offers = inventory["offers"]
            if not offers:
                continue
            event = dict(row)
            event["event"] = event.pop("event_name")
            event["event_id"] = row["id"]
            event["coverage_event_id"] = row["id"]
            event["odds"] = [
                {
                    "label": offer["selection_label"],
                    "decimal_odds": offer["decimal_odds"],
                    "market": offer["family"],
                    "line": offer.get("line"),
                    "period": offer.get("period"),
                    "participant": offer.get("participant"),
                    "bookmaker": offer.get("bookmaker") or offer.get("source_name"),
                    "observed_at": offer.get("observed_at"),
                }
                for offer in offers[:60]
            ]
            event["market_families"] = sorted({str(o.get("family")) for o in offers})
            event["source_count"] = len(inventory["sources"])
            event["market_count"] = len(inventory["catalogue"])
            event["_coverage_score"] = self._candidate_score(event, offers)
            eligible.append(event)
        eligible.sort(key=lambda item: (-float(item.get("_coverage_score") or 0), str(item.get("starts_at") or "")))
        buckets: dict[str, deque[dict[str, Any]]] = defaultdict(deque)
        for row in eligible:
            buckets[str(row.get("sport") or "unknown")].append(row)
        selected: list[dict[str, Any]] = []
        while buckets and len(selected) < max(1, int(limit)):
            progressed = False
            for sport in sorted(list(buckets)):
                bucket = buckets[sport]
                if bucket:
                    item = bucket.popleft()
                    item.pop("_coverage_score", None)
                    selected.append(item)
                    progressed = True
                if not bucket:
                    buckets.pop(sport, None)
                if len(selected) >= limit:
                    break
            if not progressed:
                break
        return selected

    @staticmethod
    def _candidate_score(event: dict[str, Any], offers: list[dict[str, Any]]) -> float:
        families = {str(item.get("family") or "") for item in offers}
        books = {str(item.get("bookmaker") or item.get("source_name") or "") for item in offers}
        sources = int(event.get("source_count") or 0)
        score = 30.0
        score += min(len(families) * 4.0, 28.0)
        score += min(len(books) * 2.5, 15.0)
        score += min(sources * 4.0, 16.0)
        if {"winner", "handicap", "total"}.issubset(families):
            score += 10.0
        return score

    def start_run(self, run_id: str, *, horizon_hours: int, sports_requested: int) -> None:
        with self.database.transaction() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO coverage_discovery_runs(id,started_at,horizon_hours,sports_requested,details_json)
                   VALUES(?,?,?,?,?)""",
                (run_id, datetime.now(timezone.utc).isoformat(), int(horizon_hours), int(sports_requested), "{}"),
            )

    def finish_run(self, run_id: str, **counts: Any) -> None:
        allowed = {
            "source_attempts",
            "source_successes",
            "source_failures",
            "events_seen",
            "canonical_events",
            "priced_events",
            "market_catalogue_count",
            "market_offer_count",
            "prefiltered_events",
            "researched_events",
            "selected_recommendations",
        }
        updates = {key: int(value or 0) for key, value in counts.items() if key in allowed}
        details = counts.get("details") or {}
        sets = ["completed_at=?", "details_json=?"] + [f"{key}=?" for key in updates]
        params: list[Any] = [datetime.now(timezone.utc).isoformat(), _json(details), *updates.values(), run_id]
        with self.database.transaction() as conn:
            conn.execute(f"UPDATE coverage_discovery_runs SET {','.join(sets)} WHERE id=?", tuple(params))

    def update_run(self, run_id: str, **counts: Any) -> None:
        allowed = {"prefiltered_events", "researched_events", "selected_recommendations"}
        updates = {key: int(value or 0) for key, value in counts.items() if key in allowed}
        if not updates:
            return
        with self.database.transaction() as conn:
            conn.execute(
                f"UPDATE coverage_discovery_runs SET {','.join(f'{key}=?' for key in updates)} WHERE id=?",
                (*updates.values(), run_id),
            )

    def latest_run_id(self) -> str | None:
        with self.database.connect() as conn:
            row = conn.execute("SELECT id FROM coverage_discovery_runs ORDER BY started_at DESC LIMIT 1").fetchone()
        return str(row[0]) if row else None

    def funnel(self, run_id: str | None = None) -> dict[str, Any]:
        with self.database.connect() as conn:
            if run_id:
                row = conn.execute("SELECT * FROM coverage_discovery_runs WHERE id=?", (run_id,)).fetchone()
            else:
                row = conn.execute("SELECT * FROM coverage_discovery_runs ORDER BY started_at DESC LIMIT 1").fetchone()
        if not row:
            return {
                "run_id": None,
                "discovered": 0,
                "priced": 0,
                "market_catalogue": 0,
                "market_offers": 0,
                "prefiltered": 0,
                "researched": 0,
                "selected": 0,
                "details": {},
            }
        data = dict(row)
        details = json.loads(data.pop("details_json") or "{}")
        discovered = int(data.get("canonical_events") or 0)
        priced = int(data.get("priced_events") or 0)
        return {
            **data,
            "run_id": data.pop("id"),
            "discovered": discovered,
            "priced": priced,
            "market_catalogue": int(data.get("market_catalogue_count") or 0),
            "market_offers": int(data.get("market_offer_count") or 0),
            "prefiltered": int(data.get("prefiltered_events") or 0),
            "researched": int(data.get("researched_events") or 0),
            "selected": int(data.get("selected_recommendations") or 0),
            "priced_pct": round((priced / discovered * 100.0), 1) if discovered else 0.0,
            "details": details,
        }

    def current_counts(self, *, now: datetime | None = None, horizon_hours: int = 72) -> dict[str, int]:
        rows = self.radar(now=now, horizon_hours=horizon_hours, limit=5000)
        ids = [str(row["id"]) for row in rows]
        if not ids:
            return {"events": 0, "priced_events": 0, "market_catalogue": 0, "market_offers": 0}
        placeholders = ",".join("?" for _ in ids)
        with self.database.connect() as conn:
            priced = conn.execute(
                f"SELECT COUNT(DISTINCT event_id) FROM coverage_market_offers WHERE event_id IN ({placeholders})",
                ids,
            ).fetchone()[0]
            catalogue = conn.execute(
                f"SELECT COUNT(*) FROM coverage_market_catalogue WHERE event_id IN ({placeholders})",
                ids,
            ).fetchone()[0]
            offers = conn.execute(
                f"SELECT COUNT(*) FROM coverage_market_offers WHERE event_id IN ({placeholders})",
                ids,
            ).fetchone()[0]
        return {
            "events": len(ids),
            "priced_events": int(priced or 0),
            "market_catalogue": int(catalogue or 0),
            "market_offers": int(offers or 0),
        }

    @staticmethod
    def _decode_market_row(row) -> dict[str, Any]:
        data = dict(row)
        data["metadata"] = json.loads(data.pop("metadata_json") or "{}")
        return data

    @staticmethod
    def _decode_offer_row(row) -> dict[str, Any]:
        data = dict(row)
        data.pop("rn", None)
        data["metadata"] = json.loads(data.pop("metadata_json") or "{}")
        return data
