from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import hashlib
from pathlib import Path
import re

from sabiai.storage.bankroll import BankrollLedger
from sabiai.storage.sqlite import SabiDatabase


class PickRecordService:
    """Create canonical Sabi Boy or Hendrix pick records from structured input."""

    OWNERS = {"sabi_boy", "hendrix"}
    RECORD_KINDS = {"pick", "tip"}
    BOOKMAKERS = {"sportybet": ("sportybet", "SportyBet"), "bet9ja": ("bet9ja", "Bet9ja")}

    def __init__(self, database: SabiDatabase | str | Path):
        self.db = database if isinstance(database, SabiDatabase) else SabiDatabase(database)

    def record(self, args: dict) -> dict:
        event = str(args.get("event") or "").strip()
        sport = str(args.get("sport") or "").strip()
        market = str(args.get("market") or "").strip()
        selection = str(args.get("pick") or args.get("selection") or "").strip()
        if not event or not sport or not market or not selection:
            raise ValueError("A pick needs event, sport, market and selection.")
        odds = _odds(args.get("decimal_odds", args.get("odds")))
        confidence = _confidence(args.get("confidence_pct"))
        owner = str(args.get("owner") or "sabi_boy").strip().casefold()
        if owner not in self.OWNERS:
            raise ValueError("Pick owner must be Sabi Boy or Hendrix.")
        record_kind = str(args.get("record_kind") or "pick").strip().casefold()
        if record_kind not in self.RECORD_KINDS:
            raise ValueError("Pick record_kind must be pick or tip.")
        starts_at = _timestamp(args.get("starts_at"))
        strategy = str(args.get("strategy") or "").strip() or None
        strategy_code = str(args.get("strategy_code") or "").strip() or None
        source_run_id = str(args.get("source_run_id") or "").strip() or None
        model_generation = str(args.get("model_generation") or "").strip() or None
        stake = _money(args.get("stake")) if args.get("stake") is not None else Decimal("0.00")
        selected = bool(args.get("selected", record_kind == "pick"))
        if record_kind == "tip":
            selected = False
            stake = Decimal("0.00")
        if stake < 0:
            raise ValueError("Stake cannot be negative.")
        if selected and stake > 0 and stake > BankrollLedger(self.db).current_balance():
            raise ValueError("Stake exceeds the current bankroll.")

        event_key = _stable_key("event", sport, event, starts_at)
        sport_slug = _slug(sport)
        sport_id = _stable_key("sport", sport_slug)
        competition = str(args.get("competition") or "").strip() or None
        competition_id = _stable_key("competition", sport_id, competition) if competition else None
        home, away = _participants(event)
        home_id = _stable_key("participant", sport_id, home) if home else None
        away_id = _stable_key("participant", sport_id, away) if away else None
        market_kind = _market_kind(market, args.get("market_kind"))
        market_id = _stable_key("market", event_key, market_kind, market, args.get("line"), args.get("period"))
        selection_id = _stable_key("selection", market_id, selection)
        bookmaker_id, bookmaker_name = self._bookmaker(args.get("bookmaker"))
        pick_id = _stable_key("pick", event_key, market_id, selection_id, odds, owner, record_kind, strategy_code)
        existing = False

        with self.db.transaction() as conn:
            existing = conn.execute("SELECT id FROM picks_v2 WHERE id=?", (pick_id,)).fetchone() is not None
            conn.execute(
                "INSERT INTO sports(id,slug,name) VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name",
                (sport_id, sport_slug, sport),
            )
            if competition_id:
                conn.execute(
                    "INSERT INTO competitions(id,sport_id,name) VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name",
                    (competition_id, sport_id, competition),
                )
            if home_id:
                conn.execute(
                    "INSERT OR IGNORE INTO participants(id,sport_id,participant_type,name) VALUES(?,?,?,?)",
                    (home_id, sport_id, "team", home),
                )
            if away_id:
                conn.execute(
                    "INSERT OR IGNORE INTO participants(id,sport_id,participant_type,name) VALUES(?,?,?,?)",
                    (away_id, sport_id, "team", away),
                )
            conn.execute(
                """INSERT INTO events(id,sport_id,competition_id,name,starts_at,home_participant_id,away_participant_id,status)
                   VALUES(?,?,?,?,?,?,?, 'scheduled')
                   ON CONFLICT(id) DO UPDATE SET competition_id=excluded.competition_id,name=excluded.name,
                     starts_at=excluded.starts_at,home_participant_id=excluded.home_participant_id,
                     away_participant_id=excluded.away_participant_id""",
                (event_key, sport_id, competition_id, event, starts_at, home_id, away_id),
            )
            source_name = str(args.get("source_name") or "").strip()
            source_event_id = str(args.get("source_event_id") or "").strip()
            if source_name and source_event_id:
                conn.execute(
                    "INSERT OR REPLACE INTO event_source_ids(event_id,source_name,source_event_id) VALUES(?,?,?)",
                    (event_key, source_name, source_event_id),
                )
            if bookmaker_id:
                conn.execute(
                    "INSERT INTO bookmakers(id,slug,name) VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name",
                    (bookmaker_id, self.BOOKMAKERS[str(args.get("bookmaker")).strip().casefold()][0], bookmaker_name),
                )
            conn.execute(
                """INSERT INTO markets(id,event_id,kind,label,metric,line,period,participant_id)
                   VALUES(?,?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET label=excluded.label,line=excluded.line,period=excluded.period""",
                (
                    market_id,
                    event_key,
                    market_kind,
                    market,
                    str(args.get("metric") or "") or None,
                    str(args.get("line")) if args.get("line") is not None else None,
                    str(args.get("period") or "full_event"),
                    None,
                ),
            )
            side = str(args.get("side") or "").strip().casefold() or _infer_side(selection, home, away)
            conn.execute(
                "INSERT INTO selections(id,market_id,label,side,participant_id) VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET label=excluded.label,side=excluded.side",
                (selection_id, market_id, selection, side or None, None),
            )
            conn.execute(
                """INSERT INTO picks_v2(
                       id,event_id,market_id,selection_id,bookmaker_id,decimal_odds,
                       confidence_pct,rationale,strategy,selected,outcome,stake,
                       owner,record_kind,strategy_code,source_run_id,model_generation
                   ) VALUES(?,?,?,?,?,?,?,?,?,?, 'pending',?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET
                       confidence_pct=excluded.confidence_pct,rationale=excluded.rationale,
                       strategy=excluded.strategy,selected=excluded.selected,stake=excluded.stake,
                       owner=excluded.owner,record_kind=excluded.record_kind,
                       strategy_code=excluded.strategy_code,source_run_id=excluded.source_run_id,
                       model_generation=excluded.model_generation""",
                (
                    pick_id,
                    event_key,
                    market_id,
                    selection_id,
                    bookmaker_id,
                    str(odds),
                    confidence,
                    str(args.get("rationale") or args.get("reason") or "").strip()[:1000] or None,
                    strategy,
                    1 if selected else 0,
                    str(stake) if stake else None,
                    owner,
                    record_kind,
                    strategy_code,
                    source_run_id,
                    model_generation,
                ),
            )

        if selected and stake > 0:
            with self.db.connect() as conn:
                already_debited = conn.execute(
                    "SELECT 1 FROM bankroll_ledger WHERE kind='stake' AND pick_id=? LIMIT 1",
                    (pick_id,),
                ).fetchone() is not None
            if not already_debited:
                BankrollLedger(self.db).record("stake", stake, pick_id=pick_id, note=f"Stake for {strategy or 'pick'}")
        return {
            "id": pick_id,
            "event": event,
            "sport": sport,
            "market": market,
            "selection": selection,
            "decimal_odds": str(odds),
            "confidence_pct": confidence,
            "owner": owner,
            "record_kind": record_kind,
            "selected": selected,
            "stake": str(stake),
            "strategy": strategy,
            "strategy_code": strategy_code,
            "status": "pending",
            "existing": existing,
        }

    def _bookmaker(self, value):
        if not value:
            return None, None
        key = str(value).strip().casefold()
        item = self.BOOKMAKERS.get(key)
        if item is None:
            raise ValueError("Only SportyBet and Bet9ja are supported bookmakers.")
        return _stable_key("bookmaker", item[0]), item[1]


def _money(value) -> Decimal:
    try:
        amount = Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("Stake must be a number.") from exc
    return amount


def _odds(value) -> Decimal:
    try:
        odds = Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("Decimal odds must be a number.") from exc
    if odds <= 1:
        raise ValueError("Decimal odds must be greater than 1.00.")
    return odds


def _confidence(value) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Confidence must be a number between 0 and 100.") from exc
    if not 0 <= number <= 100:
        raise ValueError("Confidence must be a number between 0 and 100.")
    return round(number, 1)


def _timestamp(value) -> str:
    if value is None or str(value).strip() == "":
        return (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
    if isinstance(value, (int, float)) or str(value).strip().isdigit():
        return datetime.fromtimestamp(float(value) / 1000 if float(value) > 10_000_000_000 else float(value), tz=timezone.utc).isoformat()
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("starts_at must be an ISO timestamp or epoch value.") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_")
    return slug or "unknown"


def _stable_key(prefix: str, *values) -> str:
    raw = "|".join(str(value or "").strip().casefold() for value in values)
    return f"{prefix}_{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:24]}"


def _participants(event: str) -> tuple[str | None, str | None]:
    parts = re.split(r"\s+(?:vs?|v|@)\s+", event, maxsplit=1, flags=re.IGNORECASE)
    return (parts[0].strip(), parts[1].strip()) if len(parts) == 2 else (None, None)


def _market_kind(label: str, explicit: object) -> str:
    if explicit:
        return str(explicit).strip().casefold().replace(" ", "_")
    text = label.casefold()
    if "double chance" in text:
        return "double_chance"
    if "handicap" in text or "spread" in text or "+" in text or "-" in text:
        return "handicap"
    if "over" in text or "under" in text or "total" in text:
        return "total"
    return "winner"


def _infer_side(selection: str, home: str | None, away: str | None) -> str | None:
    text = selection.casefold()
    if text in {"draw", "x", "tie"}:
        return "draw"
    if home and text.startswith(home.casefold()):
        return "home"
    if away and text.startswith(away.casefold()):
        return "away"
    if text in {"home", "away"}:
        return text
    if text.startswith("over"):
        return "over"
    if text.startswith("under"):
        return "under"
    return None
