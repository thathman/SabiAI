from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from sabiai.storage.sqlite import SabiDatabase


class HistoryService:
    """Read-only summaries of our own SabiAI records."""

    def __init__(self, database: SabiDatabase | str | Path):
        self.db = database if isinstance(database, SabiDatabase) else SabiDatabase(database)

    def summary(self, *, owner: str | None = None, record_kind: str | None = None) -> dict:
        clauses: list[str] = []
        owner_params: list[str] = []
        if owner:
            clauses.append("COALESCE(owner, 'sabi_boy')=?")
            owner_params.append(owner.strip().casefold())
        if record_kind:
            clauses.append("COALESCE(record_kind, 'pick')=?")
            owner_params.append(record_kind.strip().casefold())
        owner_clause = " WHERE " + " AND ".join(clauses) if clauses else ""
        with self.db.connect() as conn:
            pick_rows = conn.execute(
                f"SELECT outcome, COUNT(*) AS n FROM picks_v2{owner_clause} GROUP BY outcome",
                tuple(owner_params),
            ).fetchall()
            ticket_rows = conn.execute(
                "SELECT status, COUNT(*) AS n FROM tickets GROUP BY status"
            ).fetchall()
            bankroll = conn.execute(
                "SELECT balance_after FROM bankroll_ledger WHERE balance_after IS NOT NULL ORDER BY id DESC LIMIT 1"
            ).fetchone()
        picks = {row["outcome"]: int(row["n"]) for row in pick_rows}
        tickets = {row["status"]: int(row["n"]) for row in ticket_rows}
        settled = sum(picks.get(key, 0) for key in ("won", "lost", "draw", "void"))
        decisions = picks.get("won", 0) + picks.get("lost", 0)
        win_pct = round((picks.get("won", 0) / decisions) * 100, 1) if decisions else None
        return {
            "picks": {
                "total": sum(picks.values()),
                "won": picks.get("won", 0),
                "lost": picks.get("lost", 0),
                "draw": picks.get("draw", 0),
                "void": picks.get("void", 0),
                "pending": picks.get("pending", 0),
                "settled": settled,
                "win_percentage": win_pct,
            },
            "tickets": {"total": sum(tickets.values()), **tickets},
            "bankroll": str(Decimal(str(bankroll[0])).quantize(Decimal("0.01"))) if bankroll and bankroll[0] is not None else "0.00",
        }

    def by_sport(self, *, owner: str | None = None, record_kind: str | None = None) -> list[dict]:
        where, params = _pick_where(owner=owner, record_kind=record_kind)
        with self.db.connect() as conn:
            rows = conn.execute(
                f"""SELECT s.name AS sport, p.outcome, COUNT(*) AS n
                   FROM picks_v2 p
                   JOIN events e ON e.id=p.event_id
                   JOIN sports s ON s.id=e.sport_id
                   {where}
                   GROUP BY s.name, p.outcome
                   ORDER BY s.name COLLATE NOCASE""",
                params,
            ).fetchall()
        grouped: dict[str, dict[str, int]] = {}
        for row in rows:
            grouped.setdefault(row["sport"], {})[row["outcome"]] = int(row["n"])
        result = []
        for sport, outcomes in grouped.items():
            decided = outcomes.get("won", 0) + outcomes.get("lost", 0)
            result.append(
                {
                    "sport": sport,
                    "played": sum(outcomes.values()),
                    "won": outcomes.get("won", 0),
                    "lost": outcomes.get("lost", 0),
                    "draw": outcomes.get("draw", 0),
                    "void": outcomes.get("void", 0),
                    "pending": outcomes.get("pending", 0),
                    "win_percentage": round((outcomes.get("won", 0) / decided) * 100, 1) if decided else None,
                }
            )
        return result

    def by_market(self, *, owner: str | None = None, record_kind: str | None = None) -> list[dict]:
        where, params = _pick_where(owner=owner, record_kind=record_kind)
        with self.db.connect() as conn:
            rows = conn.execute(
                f"""SELECT m.label AS market, p.outcome, COUNT(*) AS n
                   FROM picks_v2 p
                   JOIN markets m ON m.id=p.market_id
                   {where}
                   GROUP BY m.label, p.outcome
                   ORDER BY m.label COLLATE NOCASE""",
                params,
            ).fetchall()
        return self._group_outcomes(rows, "market")

    def by_bookmaker(self, *, owner: str | None = None, record_kind: str | None = None) -> list[dict]:
        where, params = _pick_where(owner=owner, record_kind=record_kind)
        with self.db.connect() as conn:
            rows = conn.execute(
                f"""SELECT COALESCE(b.name, 'Unknown') AS bookmaker, p.outcome, COUNT(*) AS n
                   FROM picks_v2 p
                   LEFT JOIN bookmakers b ON b.id=p.bookmaker_id
                   {where}
                   GROUP BY COALESCE(b.name, 'Unknown'), p.outcome
                   ORDER BY bookmaker COLLATE NOCASE""",
                params,
            ).fetchall()
        return self._group_outcomes(rows, "bookmaker")

    @staticmethod
    def _group_outcomes(rows, label_key: str) -> list[dict]:
        grouped: dict[str, dict[str, int]] = {}
        for row in rows:
            grouped.setdefault(row[label_key], {})[row["outcome"]] = int(row["n"])
        result = []
        for label, outcomes in grouped.items():
            decided = outcomes.get("won", 0) + outcomes.get("lost", 0)
            result.append(
                {
                    label_key: label,
                    "played": sum(outcomes.values()),
                    "won": outcomes.get("won", 0),
                    "lost": outcomes.get("lost", 0),
                    "draw": outcomes.get("draw", 0),
                    "void": outcomes.get("void", 0),
                    "pending": outcomes.get("pending", 0),
                    "win_percentage": round((outcomes.get("won", 0) / decided) * 100, 1) if decided else None,
                }
            )
        return result


def _pick_where(*, owner: str | None = None, record_kind: str | None = None) -> tuple[str, tuple[str, ...]]:
    clauses: list[str] = []
    params: list[str] = []
    if owner:
        clauses.append("COALESCE(p.owner, 'sabi_boy')=?")
        params.append(owner.strip().casefold())
    if record_kind:
        clauses.append("COALESCE(p.record_kind, 'pick')=?")
        params.append(record_kind.strip().casefold())
    return ("WHERE " + " AND ".join(clauses) if clauses else "", tuple(params))
