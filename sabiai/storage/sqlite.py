from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import TYPE_CHECKING, Iterator

from sabiai.domain.aliases import normalize_name
from sabiai.domain.models import Bookmaker, Event, Sport, Ticket

if TYPE_CHECKING:
    from sabiai.sources.registry import Source


class SabiDatabase:
    """V2 repository layer that leaves V1 databases untouched during migration."""

    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser()

    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def initialize(self) -> None:
        schema_path = Path(__file__).with_name("schema.sql")
        migration_dir = Path(__file__).with_name("migrations")
        with self.connect() as conn:
            conn.executescript(schema_path.read_text(encoding="utf-8"))
            conn.execute(
                """CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )"""
            )
            conn.execute(
                "INSERT OR IGNORE INTO schema_migrations(version, name) VALUES (1, 'base-schema')"
            )
            migrations = sorted(migration_dir.glob("*.sql")) if migration_dir.exists() else []
            for path in migrations:
                prefix = path.name.split("_", 1)[0]
                if not prefix.isdigit():
                    continue
                version = int(prefix)
                exists = conn.execute(
                    "SELECT 1 FROM schema_migrations WHERE version=?", (version,)
                ).fetchone()
                if exists:
                    continue
                conn.executescript(path.read_text(encoding="utf-8"))
                conn.execute(
                    "INSERT INTO schema_migrations(version, name) VALUES (?, ?)",
                    (version, path.name),
                )
            version_row = conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()
            version = int(version_row[0] or 1)
            conn.execute(
                "INSERT OR REPLACE INTO v2_meta(key, value, updated_at) VALUES ('schema_version', ?, CURRENT_TIMESTAMP)",
                (str(version),),
            )

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        conn = self.connect()
        try:
            conn.execute("BEGIN")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def schema_version(self) -> int | None:
        with self.connect() as conn:
            row = conn.execute("SELECT value FROM v2_meta WHERE key='schema_version'").fetchone()
            return int(row[0]) if row else None

    def save_sport(self, sport: Sport) -> None:
        with self.transaction() as conn:
            conn.execute(
                "INSERT INTO sports(id, slug, name) VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET slug=excluded.slug, name=excluded.name",
                (sport.id, sport.slug, sport.name),
            )
            for alias in {sport.name, sport.slug, *sport.aliases}:
                conn.execute(
                    "INSERT OR REPLACE INTO sport_aliases(sport_id, alias, normalized_alias, source) VALUES(?,?,?,?)",
                    (sport.id, alias, normalize_name(alias), "canonical"),
                )

    def save_bookmaker(self, bookmaker: Bookmaker) -> None:
        with self.transaction() as conn:
            conn.execute(
                "INSERT INTO bookmakers(id, slug, name) VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET slug=excluded.slug, name=excluded.name",
                (bookmaker.id, bookmaker.slug, bookmaker.name),
            )
            for alias in {bookmaker.name, bookmaker.slug, *bookmaker.aliases}:
                conn.execute(
                    "INSERT OR REPLACE INTO bookmaker_aliases(bookmaker_id, alias, normalized_alias) VALUES(?,?,?)",
                    (bookmaker.id, alias, normalize_name(alias)),
                )

    def save_event(self, event: Event) -> None:
        with self.transaction() as conn:
            if event.home:
                conn.execute(
                    "INSERT OR IGNORE INTO participants(id, sport_id, participant_type, name) VALUES(?,?,?,?)",
                    (event.home.id, event.home.sport_id or event.sport_id, event.home.participant_type.value, event.home.name),
                )
            if event.away:
                conn.execute(
                    "INSERT OR IGNORE INTO participants(id, sport_id, participant_type, name) VALUES(?,?,?,?)",
                    (event.away.id, event.away.sport_id or event.sport_id, event.away.participant_type.value, event.away.name),
                )
            conn.execute(
                "INSERT INTO events(id,sport_id,competition_id,name,starts_at,home_participant_id,away_participant_id,venue,status) VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET competition_id=excluded.competition_id,name=excluded.name,starts_at=excluded.starts_at,home_participant_id=excluded.home_participant_id,away_participant_id=excluded.away_participant_id,venue=excluded.venue,status=excluded.status,updated_at=CURRENT_TIMESTAMP",
                (
                    event.id,
                    event.sport_id,
                    event.competition_id,
                    event.explicit_name,
                    event.starts_at.isoformat(),
                    event.home.id if event.home else None,
                    event.away.id if event.away else None,
                    event.venue,
                    event.status.value,
                ),
            )
            for source_name, source_event_id in event.source_ids.items():
                conn.execute(
                    "INSERT OR REPLACE INTO event_source_ids(event_id, source_name, source_event_id) VALUES(?,?,?)",
                    (event.id, source_name, source_event_id),
                )

    def save_ticket(self, ticket: Ticket) -> None:
        with self.transaction() as conn:
            conn.execute(
                "INSERT INTO tickets(id,bookmaker_id,source_type,source_reference,parent_ticket_id,status,combined_odds,notes_json,created_at) VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET bookmaker_id=excluded.bookmaker_id,source_type=excluded.source_type,source_reference=excluded.source_reference,parent_ticket_id=excluded.parent_ticket_id,status=excluded.status,combined_odds=excluded.combined_odds,notes_json=excluded.notes_json",
                (
                    ticket.id,
                    ticket.bookmaker_id,
                    ticket.source_type,
                    ticket.source_reference,
                    ticket.parent_ticket_id,
                    ticket.status.value,
                    str(ticket.combined_odds),
                    json.dumps(ticket.notes),
                    ticket.created_at.isoformat(),
                ),
            )
            conn.execute("DELETE FROM ticket_legs WHERE ticket_id=?", (ticket.id,))
            for index, leg in enumerate(ticket.legs, start=1):
                conn.execute(
                    "INSERT OR IGNORE INTO markets(id,event_id,kind,label,metric,line,period,participant_id) VALUES(?,?,?,?,?,?,?,?)",
                    (
                        leg.market.id,
                        leg.event_id,
                        leg.market.kind.value,
                        leg.market.label,
                        leg.market.metric,
                        str(leg.market.line) if leg.market.line is not None else None,
                        leg.market.period,
                        leg.market.participant_id,
                    ),
                )
                conn.execute(
                    "INSERT OR IGNORE INTO selections(id,market_id,label,side,participant_id) VALUES(?,?,?,?,?)",
                    (
                        leg.selection.id,
                        leg.market.id,
                        leg.selection.label,
                        leg.selection.side,
                        leg.selection.participant_id,
                    ),
                )
                conn.execute(
                    "INSERT INTO ticket_legs(id,ticket_id,leg_no,event_id,market_id,selection_id,bookmaker_id,decimal_odds,locked,outcome,note) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        leg.id,
                        ticket.id,
                        index,
                        leg.event_id,
                        leg.market.id,
                        leg.selection.id,
                        leg.bookmaker_id,
                        str(leg.odds),
                        1 if leg.locked else 0,
                        leg.outcome.value,
                        leg.note,
                    ),
                )

    def upsert_source(self, source: "Source") -> None:
        with self.transaction() as conn:
            conn.execute(
                """INSERT INTO sources(name,kind,cost,enabled,health,sports_json,capabilities_json,notes)
                   VALUES(?,?,?,?,?,?,?,?)
                   ON CONFLICT(name) DO UPDATE SET
                     kind=excluded.kind,cost=excluded.cost,enabled=excluded.enabled,
                     health=excluded.health,sports_json=excluded.sports_json,
                     capabilities_json=excluded.capabilities_json,notes=excluded.notes""",
                (
                    source.name,
                    source.kind.value,
                    source.cost.value,
                    1 if source.enabled else 0,
                    source.health,
                    json.dumps(sorted(source.sports)),
                    json.dumps(sorted(source.capabilities)),
                    source.notes,
                ),
            )

    def get_cache(self, cache_key: str, *, now: datetime | None = None) -> dict | None:
        now = now or datetime.now(timezone.utc)
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM source_cache WHERE cache_key=?", (cache_key,)
            ).fetchone()
        if not row:
            return None
        expires_at = datetime.fromisoformat(row["expires_at"])
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= now:
            return None
        return {
            "cache_key": row["cache_key"],
            "source_name": row["source_name"],
            "sport": row["sport"],
            "capability": row["capability"],
            "payload": json.loads(row["payload_json"]),
            "fetched_at": row["fetched_at"],
            "expires_at": row["expires_at"],
            "source_observed_at": row["source_observed_at"],
            "metadata": json.loads(row["metadata_json"] or "{}"),
        }

    def put_cache(
        self,
        *,
        cache_key: str,
        source_name: str,
        sport: str | None,
        capability: str | None,
        payload: object,
        fetched_at: datetime,
        expires_at: datetime,
        source_observed_at: datetime | None = None,
        metadata: dict | None = None,
    ) -> None:
        with self.transaction() as conn:
            conn.execute(
                """INSERT INTO source_cache(cache_key,source_name,sport,capability,payload_json,fetched_at,expires_at,source_observed_at,metadata_json)
                   VALUES(?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(cache_key) DO UPDATE SET
                     source_name=excluded.source_name,sport=excluded.sport,capability=excluded.capability,
                     payload_json=excluded.payload_json,fetched_at=excluded.fetched_at,expires_at=excluded.expires_at,
                     source_observed_at=excluded.source_observed_at,metadata_json=excluded.metadata_json""",
                (
                    cache_key,
                    source_name,
                    sport,
                    capability,
                    json.dumps(payload, ensure_ascii=False),
                    fetched_at.isoformat(),
                    expires_at.isoformat(),
                    source_observed_at.isoformat() if source_observed_at else None,
                    json.dumps(metadata or {}, ensure_ascii=False),
                ),
            )

    def log_source_fetch(
        self,
        *,
        source_name: str,
        sport: str | None,
        capability: str | None,
        request_key: str,
        cache_hit: bool,
        success: bool,
        paid: bool,
        reason: str | None = None,
        error: str | None = None,
    ) -> None:
        with self.transaction() as conn:
            conn.execute(
                "INSERT INTO source_fetch_log(source_name,sport,capability,request_key,cache_hit,success,paid,reason,error) VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    source_name,
                    sport,
                    capability,
                    request_key,
                    1 if cache_hit else 0,
                    1 if success else 0,
                    1 if paid else 0,
                    reason,
                    error,
                ),
            )

    def table_counts(self) -> dict[str, int]:
        tables = (
            "sports",
            "competitions",
            "participants",
            "events",
            "bookmakers",
            "markets",
            "selections",
            "odds_snapshots",
            "picks_v2",
            "tickets",
            "ticket_legs",
            "bankroll_ledger",
            "blog_posts",
        )
        with self.connect() as conn:
            return {
                table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in tables
            }
