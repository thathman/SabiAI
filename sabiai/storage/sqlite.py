from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
from typing import Iterator

from sabiai.domain.aliases import normalize_name
from sabiai.domain.models import Bookmaker, Event, Sport, Ticket


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
        with self.connect() as conn:
            conn.executescript(schema_path.read_text(encoding="utf-8"))
            conn.execute("INSERT OR REPLACE INTO v2_meta(key, value, updated_at) VALUES ('schema_version', '1', CURRENT_TIMESTAMP)")

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

    def save_sport(self, sport: Sport) -> None:
        with self.transaction() as conn:
            conn.execute("INSERT INTO sports(id, slug, name) VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET slug=excluded.slug, name=excluded.name", (sport.id, sport.slug, sport.name))
            for alias in {sport.name, sport.slug, *sport.aliases}:
                conn.execute("INSERT OR REPLACE INTO sport_aliases(sport_id, alias, normalized_alias, source) VALUES(?,?,?,?)", (sport.id, alias, normalize_name(alias), "canonical"))

    def save_bookmaker(self, bookmaker: Bookmaker) -> None:
        with self.transaction() as conn:
            conn.execute("INSERT INTO bookmakers(id, slug, name) VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET slug=excluded.slug, name=excluded.name", (bookmaker.id, bookmaker.slug, bookmaker.name))
            for alias in {bookmaker.name, bookmaker.slug, *bookmaker.aliases}:
                conn.execute("INSERT OR REPLACE INTO bookmaker_aliases(bookmaker_id, alias, normalized_alias) VALUES(?,?,?)", (bookmaker.id, alias, normalize_name(alias)))

    def save_event(self, event: Event) -> None:
        with self.transaction() as conn:
            if event.home:
                conn.execute("INSERT OR IGNORE INTO participants(id, sport_id, participant_type, name) VALUES(?,?,?,?)", (event.home.id, event.home.sport_id or event.sport_id, event.home.participant_type.value, event.home.name))
            if event.away:
                conn.execute("INSERT OR IGNORE INTO participants(id, sport_id, participant_type, name) VALUES(?,?,?,?)", (event.away.id, event.away.sport_id or event.sport_id, event.away.participant_type.value, event.away.name))
            conn.execute("INSERT INTO events(id,sport_id,competition_id,name,starts_at,home_participant_id,away_participant_id,venue,status) VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET competition_id=excluded.competition_id,name=excluded.name,starts_at=excluded.starts_at,home_participant_id=excluded.home_participant_id,away_participant_id=excluded.away_participant_id,venue=excluded.venue,status=excluded.status,updated_at=CURRENT_TIMESTAMP", (event.id,event.sport_id,event.competition_id,event.explicit_name,event.starts_at.isoformat(),event.home.id if event.home else None,event.away.id if event.away else None,event.venue,event.status.value))
            for source_name, source_event_id in event.source_ids.items():
                conn.execute("INSERT OR REPLACE INTO event_source_ids(event_id, source_name, source_event_id) VALUES(?,?,?)", (event.id, source_name, source_event_id))

    def save_ticket(self, ticket: Ticket) -> None:
        with self.transaction() as conn:
            conn.execute("INSERT INTO tickets(id,bookmaker_id,source_type,source_reference,parent_ticket_id,status,combined_odds,notes_json,created_at) VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET bookmaker_id=excluded.bookmaker_id,source_type=excluded.source_type,source_reference=excluded.source_reference,parent_ticket_id=excluded.parent_ticket_id,status=excluded.status,combined_odds=excluded.combined_odds,notes_json=excluded.notes_json", (ticket.id,ticket.bookmaker_id,ticket.source_type,ticket.source_reference,ticket.parent_ticket_id,ticket.status.value,str(ticket.combined_odds),json.dumps(ticket.notes),ticket.created_at.isoformat()))
            conn.execute("DELETE FROM ticket_legs WHERE ticket_id=?", (ticket.id,))
            for index, leg in enumerate(ticket.legs, start=1):
                conn.execute("INSERT OR IGNORE INTO markets(id,event_id,kind,label,metric,line,period,participant_id) VALUES(?,?,?,?,?,?,?,?)", (leg.market.id,leg.event_id,leg.market.kind.value,leg.market.label,leg.market.metric,str(leg.market.line) if leg.market.line is not None else None,leg.market.period,leg.market.participant_id))
                conn.execute("INSERT OR IGNORE INTO selections(id,market_id,label,side,participant_id) VALUES(?,?,?,?,?)", (leg.selection.id,leg.market.id,leg.selection.label,leg.selection.side,leg.selection.participant_id))
                conn.execute("INSERT INTO ticket_legs(id,ticket_id,leg_no,event_id,market_id,selection_id,bookmaker_id,decimal_odds,locked,outcome,note) VALUES(?,?,?,?,?,?,?,?,?,?,?)", (leg.id,ticket.id,index,leg.event_id,leg.market.id,leg.selection.id,leg.bookmaker_id,str(leg.odds),1 if leg.locked else 0,leg.outcome.value,leg.note))

    def table_counts(self) -> dict[str, int]:
        tables = ("sports","competitions","participants","events","bookmakers","markets","selections","odds_snapshots","picks_v2","tickets","ticket_legs","bankroll_ledger","blog_posts")
        with self.connect() as conn:
            return {table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in tables}
