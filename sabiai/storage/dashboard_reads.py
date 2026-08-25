from __future__ import annotations

from pathlib import Path

from sabiai.storage.sqlite import SabiDatabase


class DashboardReadService:
    """Read-only detailed records used by the Sabi Boy dashboard."""

    def __init__(self, database: SabiDatabase | str | Path):
        self.db = database if isinstance(database, SabiDatabase) else SabiDatabase(database)

    def picks(
        self,
        *,
        limit: int = 100,
        outcome: str | None = None,
        sport: str | None = None,
        strategy: str | None = None,
    ) -> list[dict]:
        where: list[str] = []
        params: list[object] = []
        if outcome:
            where.append("p.outcome=?")
            params.append(outcome.strip().casefold())
        if sport:
            where.append("LOWER(s.name)=LOWER(?)")
            params.append(sport.strip())
        if strategy:
            where.append("LOWER(COALESCE(p.strategy,''))=LOWER(?)")
            params.append(strategy.strip())
        sql = """SELECT p.id,
                        e.name AS event,
                        e.starts_at,
                        s.name AS sport,
                        c.name AS competition,
                        m.label AS market,
                        sel.label AS selection,
                        p.decimal_odds,
                        p.confidence_pct,
                        p.strategy,
                        p.selected,
                        p.outcome,
                        p.stake,
                        p.payout,
                        b.name AS bookmaker,
                        p.rationale,
                        p.created_at,
                        p.settled_at
                 FROM picks_v2 p
                 JOIN events e ON e.id=p.event_id
                 JOIN sports s ON s.id=e.sport_id
                 LEFT JOIN competitions c ON c.id=e.competition_id
                 JOIN markets m ON m.id=p.market_id
                 JOIN selections sel ON sel.id=p.selection_id
                 LEFT JOIN bookmakers b ON b.id=p.bookmaker_id"""
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY p.created_at DESC LIMIT ?"
        params.append(max(1, min(int(limit), 1000)))
        with self.db.connect() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        return [dict(row) for row in rows]

    def tickets(
        self,
        *,
        limit: int = 100,
        status: str | None = None,
        source_type: str | None = None,
    ) -> list[dict]:
        where: list[str] = []
        params: list[object] = []
        if status:
            where.append("t.status=?")
            params.append(status.strip().casefold())
        if source_type:
            where.append("LOWER(t.source_type)=LOWER(?)")
            params.append(source_type.strip())
        sql = """SELECT t.id,
                        t.parent_ticket_id,
                        t.source_type,
                        t.source_reference,
                        t.version_no,
                        t.booking_code,
                        t.status,
                        t.combined_odds,
                        t.stake,
                        t.payout,
                        t.created_at,
                        t.settled_at,
                        b.name AS bookmaker,
                        COUNT(l.id) AS leg_count,
                        SUM(CASE WHEN l.outcome='won' THEN 1 ELSE 0 END) AS won_legs,
                        SUM(CASE WHEN l.outcome='lost' THEN 1 ELSE 0 END) AS lost_legs,
                        SUM(CASE WHEN l.outcome='draw' THEN 1 ELSE 0 END) AS draw_legs,
                        SUM(CASE WHEN l.outcome='void' THEN 1 ELSE 0 END) AS void_legs,
                        SUM(CASE WHEN l.outcome='pending' THEN 1 ELSE 0 END) AS pending_legs
                 FROM tickets t
                 LEFT JOIN bookmakers b ON b.id=t.bookmaker_id
                 LEFT JOIN ticket_legs l ON l.ticket_id=t.id"""
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " GROUP BY t.id ORDER BY t.created_at DESC LIMIT ?"
        params.append(max(1, min(int(limit), 1000)))
        with self.db.connect() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        return [dict(row) for row in rows]

    def ticket(self, ticket_id: str) -> dict | None:
        with self.db.connect() as conn:
            ticket = conn.execute(
                """SELECT t.*, b.name AS bookmaker
                   FROM tickets t
                   LEFT JOIN bookmakers b ON b.id=t.bookmaker_id
                   WHERE t.id=?""",
                (ticket_id,),
            ).fetchone()
            if ticket is None:
                return None
            legs = conn.execute(
                """SELECT l.id,
                          l.leg_no,
                          e.name AS event,
                          sp.name AS sport,
                          c.name AS competition,
                          m.label AS market,
                          s.label AS selection,
                          l.decimal_odds,
                          l.locked,
                          l.outcome,
                          l.note,
                          b.name AS bookmaker
                   FROM ticket_legs l
                   JOIN events e ON e.id=l.event_id
                   JOIN sports sp ON sp.id=e.sport_id
                   LEFT JOIN competitions c ON c.id=e.competition_id
                   JOIN markets m ON m.id=l.market_id
                   JOIN selections s ON s.id=l.selection_id
                   LEFT JOIN bookmakers b ON b.id=l.bookmaker_id
                   WHERE l.ticket_id=?
                   ORDER BY l.leg_no""",
                (ticket_id,),
            ).fetchall()
        return {**dict(ticket), "legs": [dict(row) for row in legs]}

    def strategies(self) -> list[str]:
        with self.db.connect() as conn:
            rows = conn.execute(
                """SELECT DISTINCT strategy
                   FROM picks_v2
                   WHERE strategy IS NOT NULL AND TRIM(strategy) != ''
                   ORDER BY strategy COLLATE NOCASE"""
            ).fetchall()
        return [str(row[0]) for row in rows]

    def sports(self) -> list[str]:
        with self.db.connect() as conn:
            rows = conn.execute(
                """SELECT DISTINCT s.name
                   FROM picks_v2 p
                   JOIN events e ON e.id=p.event_id
                   JOIN sports s ON s.id=e.sport_id
                   ORDER BY s.name COLLATE NOCASE"""
            ).fetchall()
        return [str(row[0]) for row in rows]
