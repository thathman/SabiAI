from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
from typing import Callable

from sabiai.config import Settings
from sabiai.sources import SourceRequest, TheSportsDBAdapter
from sabiai.storage import SabiDatabase

from .service import SettlementService


@dataclass(frozen=True, slots=True)
class ResultSnapshot:
    source_name: str
    source_event_id: str
    status: str
    home_score: Decimal | None
    away_score: Decimal | None
    observed_at: str
    payload: dict

    @property
    def final(self) -> bool:
        return self.status == "finished"


@dataclass(frozen=True, slots=True)
class AutomaticSettlementReport:
    checked_events: int
    live_events: int
    finished_events: int
    postponed_events: int
    cancelled_events: int
    picks_settled: int
    ticket_legs_settled: int
    records_skipped: int
    source_errors: tuple[str, ...]

    @property
    def changed(self) -> int:
        return self.picks_settled + self.ticket_legs_settled

    def as_dict(self) -> dict:
        data = asdict(self)
        data["changed"] = self.changed
        return data


ResultFetcher = Callable[[str], ResultSnapshot]


class TheSportsDbResultFetcher:
    def __init__(self, api_key: str = "123"):
        self.adapter = TheSportsDBAdapter(api_key=api_key)

    def __call__(self, source_event_id: str) -> ResultSnapshot:
        response = self.adapter.fetch(
            SourceRequest(
                request_key=f"auto-settlement:thesportsdb:{source_event_id}",
                capability="event_lookup",
                ttl_seconds=0,
                metadata={"event_id": source_event_id},
                source_names=("TheSportsDB",),
            )
        )
        event = ((response or {}).get("raw") or {}).get("event")
        if not isinstance(event, dict):
            raise RuntimeError("TheSportsDB event lookup did not return an event object.")
        status = self._status(event)
        return ResultSnapshot(
            source_name="TheSportsDB",
            source_event_id=str(source_event_id),
            status=status,
            home_score=self._score(event.get("intHomeScore")),
            away_score=self._score(event.get("intAwayScore")),
            observed_at=datetime.now(timezone.utc).isoformat(),
            payload=event,
        )

    @staticmethod
    def _score(value) -> Decimal | None:
        if value is None or str(value).strip() == "":
            return None
        try:
            return Decimal(str(value).strip())
        except (InvalidOperation, TypeError, ValueError):
            return None

    @staticmethod
    def _status(event: dict) -> str:
        text = " ".join(
            str(event.get(key) or "")
            for key in ("strStatus", "strProgress", "strPostponed")
        ).strip().casefold()
        if any(token in text for token in ("cancelled", "canceled", "abandoned")):
            return "cancelled"
        if "postpon" in text:
            return "postponed"
        if text in {"ft", "aet"} or any(
            token in text for token in ("match finished", "finished", "final", "full time")
        ):
            return "finished"
        if any(token in text for token in ("live", "in progress", "half time", "1h", "2h")):
            return "live"
        return "scheduled"


class AutomaticSettlementService:
    """Poll result heartbeats and settle only deterministic score-derived selections."""

    SCOREBOARD_SPORTS = {
        "football",
        "soccer",
        "futsal",
        "basketball",
        "baseball",
        "american football",
        "ice hockey",
        "hockey",
        "handball",
        "rugby",
        "cricket",
        "volleyball",
    }
    FULL_PERIODS = {"full_event", "full_game", "full_match", "regulation"}

    def __init__(
        self,
        database: SabiDatabase | str | Path,
        *,
        settings: Settings | None = None,
        fetchers: dict[str, ResultFetcher] | None = None,
    ):
        self.db = database if isinstance(database, SabiDatabase) else SabiDatabase(database)
        self.settings = settings or Settings.from_env()
        self.fetchers = fetchers or {
            "thesportsdb": TheSportsDbResultFetcher(self.settings.thesportsdb_key)
        }
        self.settlements = SettlementService(self.db)

    def run(self, *, max_events: int = 100) -> AutomaticSettlementReport:
        checked = live = finished = postponed = cancelled = 0
        picks_settled = legs_settled = skipped = 0
        errors: list[str] = []

        for event in self._pending_events(max_events=max_events):
            fetcher = self.fetchers.get(event["source_key"])
            if fetcher is None:
                skipped += event["pending_records"]
                continue
            checked += 1
            try:
                snapshot = fetcher(event["source_event_id"])
            except Exception as exc:
                errors.append(f"{event['id']}: {type(exc).__name__}: {str(exc)[:180]}")
                continue

            self._record_observation(event["id"], snapshot)
            self._update_event_status(event["id"], snapshot.status)
            if snapshot.status == "live":
                live += 1
            elif snapshot.status == "finished":
                finished += 1
            elif snapshot.status == "postponed":
                postponed += 1
            elif snapshot.status == "cancelled":
                cancelled += 1

            if not snapshot.final or snapshot.home_score is None or snapshot.away_score is None:
                continue

            for record in self._pending_records(event["id"]):
                outcome = self.evaluate(record, snapshot)
                if outcome is None:
                    skipped += 1
                    continue
                source = f"auto:{snapshot.source_name}"
                reason = (
                    f"Official result heartbeat {snapshot.source_event_id}: "
                    f"{self._fmt(snapshot.home_score)}-{self._fmt(snapshot.away_score)}."
                )
                if record["entity_type"] == "pick":
                    result = self.settlements.settle_pick(
                        record["entity_id"], outcome, source=source, reason=reason
                    )
                    picks_settled += int(result.changed)
                else:
                    result, _ = self.settlements.settle_ticket_leg(
                        record["entity_id"], outcome, source=source, reason=reason
                    )
                    legs_settled += int(result.changed)

        return AutomaticSettlementReport(
            checked_events=checked,
            live_events=live,
            finished_events=finished,
            postponed_events=postponed,
            cancelled_events=cancelled,
            picks_settled=picks_settled,
            ticket_legs_settled=legs_settled,
            records_skipped=skipped,
            source_errors=tuple(errors),
        )

    @classmethod
    def evaluate(cls, record, snapshot: ResultSnapshot) -> str | None:
        sport = str(record["sport_slug"] or "").casefold().replace("_", " ")
        period = str(record["period"] or "full_event").casefold()
        if sport not in cls.SCOREBOARD_SPORTS or period not in cls.FULL_PERIODS:
            return None

        home = snapshot.home_score
        away = snapshot.away_score
        if home is None or away is None:
            return None
        side = str(record["side"] or "").casefold().replace(" ", "_")
        kind = str(record["kind"] or "").casefold()
        metric = str(record["metric"] or "").casefold().replace(" ", "_")

        if kind in {"winner", "win_draw_lose"}:
            actual = "home" if home > away else "away" if away > home else "draw"
            if side not in {"home", "away", "draw"}:
                return None
            return "won" if side == actual else "lost"

        if kind == "double_chance":
            actual = "home" if home > away else "away" if away > home else "draw"
            allowed = {
                "home_or_draw": {"home", "draw"},
                "away_or_draw": {"away", "draw"},
                "home_or_away": {"home", "away"},
            }.get(side)
            return None if allowed is None else "won" if actual in allowed else "lost"

        line = cls._decimal(record["line"])
        if kind == "total" and metric in {"", "total", "goals", "points", "runs", "score"}:
            return cls._over_under(side, home + away, line)

        if kind == "team_total" and metric in {"", "total", "goals", "points", "runs", "score"}:
            team_side = cls._participant_side(record)
            value = home if team_side == "home" else away if team_side == "away" else None
            return cls._over_under(side, value, line)

        if kind == "count" and metric == "teams_scoring" and side in {"yes", "no"}:
            actual = home > 0 and away > 0
            return "won" if actual == (side == "yes") else "lost"

        if kind == "handicap" and metric in {"", "score", "goals", "points", "runs", "draw_no_bet"}:
            team_side = cls._participant_side(record) or (side if side in {"home", "away"} else None)
            if team_side not in {"home", "away"} or line is None:
                return None
            selected = home if team_side == "home" else away
            other = away if team_side == "home" else home
            adjusted = selected + line
            return "won" if adjusted > other else "lost" if adjusted < other else "void"

        return None

    def _pending_events(self, *, max_events: int) -> list[dict]:
        now = datetime.now(timezone.utc).isoformat()
        with self.db.connect() as conn:
            rows = conn.execute(
                """SELECT e.id, esi.source_name, esi.source_event_id,
                          (SELECT COUNT(*) FROM picks_v2 p WHERE p.event_id=e.id AND p.outcome='pending') +
                          (SELECT COUNT(*) FROM ticket_legs l WHERE l.event_id=e.id AND l.outcome='pending') AS pending_records
                   FROM events e
                   JOIN event_source_ids esi ON esi.event_id=e.id
                   WHERE e.starts_at<=?
                     AND LOWER(REPLACE(esi.source_name,' ',''))='thesportsdb'
                     AND (
                       EXISTS(SELECT 1 FROM picks_v2 p WHERE p.event_id=e.id AND p.outcome='pending')
                       OR EXISTS(SELECT 1 FROM ticket_legs l WHERE l.event_id=e.id AND l.outcome='pending')
                     )
                   ORDER BY e.starts_at
                   LIMIT ?""",
                (now, max(1, min(int(max_events), 500))),
            ).fetchall()
        return [
            {
                "id": row["id"],
                "source_key": "".join(ch for ch in row["source_name"].casefold() if ch.isalnum()),
                "source_event_id": row["source_event_id"],
                "pending_records": int(row["pending_records"] or 0),
            }
            for row in rows
        ]

    def _pending_records(self, event_id: str):
        sql = """SELECT 'pick' AS entity_type, p.id AS entity_id,
                        sp.slug AS sport_slug, m.kind, m.metric, m.line, m.period,
                        s.side, m.participant_id AS market_participant_id,
                        s.participant_id AS selection_participant_id,
                        e.home_participant_id, e.away_participant_id
                 FROM picks_v2 p
                 JOIN events e ON e.id=p.event_id
                 JOIN sports sp ON sp.id=e.sport_id
                 JOIN markets m ON m.id=p.market_id
                 JOIN selections s ON s.id=p.selection_id
                 WHERE p.event_id=? AND p.outcome='pending'
                 UNION ALL
                 SELECT 'ticket_leg' AS entity_type, l.id AS entity_id,
                        sp.slug AS sport_slug, m.kind, m.metric, m.line, m.period,
                        s.side, m.participant_id AS market_participant_id,
                        s.participant_id AS selection_participant_id,
                        e.home_participant_id, e.away_participant_id
                 FROM ticket_legs l
                 JOIN events e ON e.id=l.event_id
                 JOIN sports sp ON sp.id=e.sport_id
                 JOIN markets m ON m.id=l.market_id
                 JOIN selections s ON s.id=l.selection_id
                 WHERE l.event_id=? AND l.outcome='pending'"""
        with self.db.connect() as conn:
            return conn.execute(sql, (event_id, event_id)).fetchall()

    def _record_observation(self, event_id: str, snapshot: ResultSnapshot) -> None:
        core = {
            "status": snapshot.status,
            "home_score": self._fmt(snapshot.home_score),
            "away_score": self._fmt(snapshot.away_score),
        }
        digest = hashlib.sha256(
            json.dumps(core, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        with self.db.transaction() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO event_result_observations(
                     event_id,source_name,source_event_id,status,home_score,away_score,
                     observed_at,content_hash,payload_json
                   ) VALUES(?,?,?,?,?,?,?,?,?)""",
                (
                    event_id,
                    snapshot.source_name,
                    snapshot.source_event_id,
                    snapshot.status,
                    core["home_score"],
                    core["away_score"],
                    snapshot.observed_at,
                    digest,
                    json.dumps(snapshot.payload, ensure_ascii=False, separators=(",", ":")),
                ),
            )

    def _update_event_status(self, event_id: str, status: str) -> None:
        if status not in {"scheduled", "live", "finished", "postponed", "cancelled"}:
            return
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE events SET status=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (status, event_id),
            )

    @staticmethod
    def _participant_side(record) -> str | None:
        participant = record["selection_participant_id"] or record["market_participant_id"]
        if participant and participant == record["home_participant_id"]:
            return "home"
        if participant and participant == record["away_participant_id"]:
            return "away"
        return None

    @staticmethod
    def _decimal(value) -> Decimal | None:
        if value is None:
            return None
        try:
            return Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            return None

    @classmethod
    def _over_under(cls, side: str, value: Decimal | None, line: Decimal | None) -> str | None:
        if value is None or line is None or side not in {"over", "under"}:
            return None
        if value == line:
            return "void"
        won = value > line if side == "over" else value < line
        return "won" if won else "lost"

    @staticmethod
    def _fmt(value: Decimal | None) -> str | None:
        if value is None:
            return None
        return format(value, "f")
