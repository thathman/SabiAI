from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from sabiai.storage.sqlite import SabiDatabase


class HistoryService:
    """Read-only summaries of our own SabiAI records."""

    def __init__(self, database: SabiDatabase | str | Path):
        self.db = database if isinstance(database, SabiDatabase) else SabiDatabase(database)

    def summary(self) -> dict:
        with self.db.connect() as conn:
            pick_rows = conn.execute(
                "SELECT outcome, COUNT(*) AS n FROM picks_v2 GROUP BY outcome"
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

    def by_sport(self) -> list[dict]:
        with self.db.connect() as conn:
            rows = conn.execute(
                """SELECT s.name AS sport, p.outcome, COUNT(*) AS n
                   FROM picks_v2 p
                   JOIN events e ON e.id=p.event_id
                   JOIN sports s ON s.id=e.sport_id
                   GROUP BY s.name, p.outcome
                   ORDER BY s.name COLLATE NOCASE"""
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

    def by_market(self) -> list[dict]:
        with self.db.connect() as conn:
            rows = conn.execute(
                """SELECT m.label AS market, p.outcome, COUNT(*) AS n
                   FROM picks_v2 p
                   JOIN markets m ON m.id=p.market_id
                   GROUP BY m.label, p.outcome
                   ORDER BY m.label COLLATE NOCASE"""
            ).fetchall()
        return self._group_outcomes(rows, "market")

    def by_bookmaker(self) -> list[dict]:
        with self.db.connect() as conn:
            rows = conn.execute(
                """SELECT COALESCE(b.name, 'Unknown') AS bookmaker, p.outcome, COUNT(*) AS n
                   FROM picks_v2 p
                   LEFT JOIN bookmakers b ON b.id=p.bookmaker_id
                   GROUP BY COALESCE(b.name, 'Unknown'), p.outcome
                   ORDER BY bookmaker COLLATE NOCASE"""
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
