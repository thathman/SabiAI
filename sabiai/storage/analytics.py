from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from pathlib import Path

from sabiai.storage.sqlite import SabiDatabase


_DECIMAL_ZERO = Decimal("0.00")


def _money(value) -> Decimal:
    if value is None:
        return _DECIMAL_ZERO
    return Decimal(str(value)).quantize(Decimal("0.01"))


def _pct(won: int, lost: int) -> float | None:
    decided = won + lost
    return round((won / decided) * 100, 1) if decided else None


class PerformanceAnalytics:
    """Read-only analytics for our own Sabi Boy history.

    This service intentionally does not expose general sports statistics. It only summarizes
    records stored by Sabi Boy: our picks, tickets, bankroll and outcomes.
    """

    def __init__(self, database: SabiDatabase | str | Path):
        self.db = database if isinstance(database, SabiDatabase) else SabiDatabase(database)

    def streaks(self) -> dict:
        with self.db.connect() as conn:
            rows = conn.execute(
                """SELECT outcome, COALESCE(settled_at, created_at) AS stamp
                   FROM picks_v2
                   WHERE outcome IN ('won','lost')
                   ORDER BY COALESCE(settled_at, created_at), created_at, id"""
            ).fetchall()

        outcomes = [row["outcome"] for row in rows]
        if not outcomes:
            return {
                "current": {"type": None, "count": 0},
                "best_win_streak": 0,
                "worst_losing_streak": 0,
                "decided_picks": 0,
            }

        best_win = best_loss = 0
        run_type = outcomes[0]
        run_count = 0
        for outcome in outcomes:
            if outcome == run_type:
                run_count += 1
            else:
                if run_type == "won":
                    best_win = max(best_win, run_count)
                else:
                    best_loss = max(best_loss, run_count)
                run_type = outcome
                run_count = 1
        if run_type == "won":
            best_win = max(best_win, run_count)
        else:
            best_loss = max(best_loss, run_count)

        return {
            "current": {"type": run_type, "count": run_count},
            "best_win_streak": best_win,
            "worst_losing_streak": best_loss,
            "decided_picks": len(outcomes),
        }

    def profit_loss(self) -> dict:
        """Separate betting cashflow from deposits/withdrawals and other adjustments."""
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT kind, COALESCE(SUM(CAST(amount AS REAL)),0) AS total, COUNT(*) AS n "
                "FROM bankroll_ledger GROUP BY kind"
            ).fetchall()
            balance = conn.execute(
                "SELECT balance_after FROM bankroll_ledger WHERE balance_after IS NOT NULL ORDER BY id DESC LIMIT 1"
            ).fetchone()

        totals = {row["kind"]: _money(row["total"]) for row in rows}
        stakes = totals.get("stake", _DECIMAL_ZERO)
        payouts = totals.get("payout", _DECIMAL_ZERO)
        refunds = totals.get("refund", _DECIMAL_ZERO)
        betting_result = (stakes + payouts + refunds).quantize(Decimal("0.01"))
        deposits = totals.get("deposit", _DECIMAL_ZERO) + totals.get("opening_balance", _DECIMAL_ZERO)
        withdrawals = totals.get("withdrawal", _DECIMAL_ZERO)
        adjustments = totals.get("adjustment", _DECIMAL_ZERO)

        return {
            "betting": {
                "stakes": str(stakes),
                "payouts": str(payouts),
                "refunds": str(refunds),
                "profit_loss": str(betting_result),
            },
            "funding": {
                "deposits_and_opening": str(deposits),
                "withdrawals": str(withdrawals),
                "adjustments": str(adjustments),
            },
            "bankroll": str(_money(balance[0]) if balance and balance[0] is not None else _DECIMAL_ZERO),
        }

    def by_strategy(self) -> list[dict]:
        return self._pick_breakdown("COALESCE(NULLIF(strategy,''), 'Unspecified')", "strategy")

    def by_competition(self) -> list[dict]:
        with self.db.connect() as conn:
            rows = conn.execute(
                """SELECT COALESCE(c.name, 'Unknown') AS competition, p.outcome, COUNT(*) AS n
                   FROM picks_v2 p
                   JOIN events e ON e.id=p.event_id
                   LEFT JOIN competitions c ON c.id=e.competition_id
                   GROUP BY COALESCE(c.name, 'Unknown'), p.outcome
                   ORDER BY competition COLLATE NOCASE"""
            ).fetchall()
        return self._group_outcomes(rows, "competition")

    def by_odds_band(self) -> list[dict]:
        with self.db.connect() as conn:
            rows = conn.execute(
                """SELECT
                     CASE
                       WHEN CAST(decimal_odds AS REAL) < 1.50 THEN '1.01–1.49'
                       WHEN CAST(decimal_odds AS REAL) < 2.00 THEN '1.50–1.99'
                       WHEN CAST(decimal_odds AS REAL) < 3.00 THEN '2.00–2.99'
                       WHEN CAST(decimal_odds AS REAL) < 5.00 THEN '3.00–4.99'
                       ELSE '5.00+'
                     END AS odds_band,
                     outcome,
                     COUNT(*) AS n
                   FROM picks_v2
                   GROUP BY odds_band, outcome
                   ORDER BY MIN(CAST(decimal_odds AS REAL))"""
            ).fetchall()
        return self._group_outcomes(rows, "odds_band")

    def by_ticket_size(self) -> list[dict]:
        with self.db.connect() as conn:
            rows = conn.execute(
                """SELECT leg_count, status, COUNT(*) AS n
                   FROM (
                     SELECT t.id, t.status, COUNT(l.id) AS leg_count
                     FROM tickets t
                     LEFT JOIN ticket_legs l ON l.ticket_id=t.id
                     WHERE t.status IN ('won','lost','void','partial','pending')
                     GROUP BY t.id, t.status
                   ) q
                   GROUP BY leg_count, status
                   ORDER BY leg_count"""
            ).fetchall()
        return self._group_ticket_status(rows, "leg_count")

    def by_combined_odds_band(self) -> list[dict]:
        with self.db.connect() as conn:
            rows = conn.execute(
                """SELECT
                     CASE
                       WHEN CAST(combined_odds AS REAL) < 3 THEN 'Under 3.00'
                       WHEN CAST(combined_odds AS REAL) < 5 THEN '3.00–4.99'
                       WHEN CAST(combined_odds AS REAL) < 10 THEN '5.00–9.99'
                       WHEN CAST(combined_odds AS REAL) < 20 THEN '10.00–19.99'
                       WHEN CAST(combined_odds AS REAL) < 50 THEN '20.00–49.99'
                       ELSE '50.00+'
                     END AS combined_odds_band,
                     status,
                     COUNT(*) AS n
                   FROM tickets
                   WHERE combined_odds IS NOT NULL
                     AND status IN ('won','lost','void','partial','pending')
                   GROUP BY combined_odds_band, status
                   ORDER BY MIN(CAST(combined_odds AS REAL))"""
            ).fetchall()
        return self._group_ticket_status(rows, "combined_odds_band")

    def ticket_sources(self) -> list[dict]:
        with self.db.connect() as conn:
            rows = conn.execute(
                """SELECT
                     CASE WHEN parent_ticket_id IS NULL THEN 'original' ELSE 'edited' END AS version_type,
                     COALESCE(NULLIF(source_type,''), 'unknown') AS source_type,
                     status,
                     COUNT(*) AS n
                   FROM tickets
                   WHERE status IN ('won','lost','void','partial','pending')
                   GROUP BY version_type, source_type, status
                   ORDER BY version_type, source_type"""
            ).fetchall()

        grouped: dict[tuple[str, str], dict[str, int]] = defaultdict(dict)
        for row in rows:
            grouped[(row["version_type"], row["source_type"])][row["status"]] = int(row["n"])
        result = []
        for (version_type, source_type), statuses in grouped.items():
            won, lost = statuses.get("won", 0), statuses.get("lost", 0)
            result.append({
                "version_type": version_type,
                "source_type": source_type,
                "tickets": sum(statuses.values()),
                "won": won,
                "lost": lost,
                "void": statuses.get("void", 0),
                "partial": statuses.get("partial", 0),
                "pending": statuses.get("pending", 0),
                "win_percentage": _pct(won, lost),
            })
        return result

    def ticket_killers(self, limit: int = 25) -> list[dict]:
        """Return lost tickets where exactly one leg lost and no other leg lost.

        This is the useful 'one game killed the ticket' pattern from our own history.
        """
        with self.db.connect() as conn:
            rows = conn.execute(
                """WITH one_loss AS (
                     SELECT ticket_id,
                            SUM(CASE WHEN outcome='lost' THEN 1 ELSE 0 END) AS lost_legs,
                            SUM(CASE WHEN outcome='pending' THEN 1 ELSE 0 END) AS pending_legs
                     FROM ticket_legs
                     GROUP BY ticket_id
                   )
                   SELECT t.id AS ticket_id,
                          t.created_at,
                          t.combined_odds,
                          t.source_type,
                          e.name AS event,
                          m.label AS market,
                          s.label AS selection,
                          l.decimal_odds
                   FROM tickets t
                   JOIN one_loss x ON x.ticket_id=t.id AND x.lost_legs=1 AND x.pending_legs=0
                   JOIN ticket_legs l ON l.ticket_id=t.id AND l.outcome='lost'
                   JOIN events e ON e.id=l.event_id
                   JOIN markets m ON m.id=l.market_id
                   JOIN selections s ON s.id=l.selection_id
                   WHERE t.status='lost'
                   ORDER BY COALESCE(t.settled_at, t.created_at) DESC
                   LIMIT ?""",
                (max(int(limit), 1),),
            ).fetchall()
        return [dict(row) for row in rows]

    def daily_outcomes(self, limit_days: int = 90) -> list[dict]:
        with self.db.connect() as conn:
            rows = conn.execute(
                """SELECT date(COALESCE(settled_at, created_at)) AS day,
                          outcome,
                          COUNT(*) AS n
                   FROM picks_v2
                   WHERE outcome IN ('won','lost','draw','void')
                   GROUP BY day, outcome
                   ORDER BY day DESC
                   LIMIT ?""",
                (max(int(limit_days), 1) * 4,),
            ).fetchall()
        grouped: dict[str, dict[str, int]] = defaultdict(dict)
        for row in rows:
            grouped[row["day"]][row["outcome"]] = int(row["n"])
        days = sorted(grouped.keys())[-max(int(limit_days), 1):]
        return [
            {
                "day": day,
                "won": grouped[day].get("won", 0),
                "lost": grouped[day].get("lost", 0),
                "draw": grouped[day].get("draw", 0),
                "void": grouped[day].get("void", 0),
            }
            for day in days
        ]

    def bankroll_series(self, limit: int = 365) -> list[dict]:
        with self.db.connect() as conn:
            rows = conn.execute(
                """SELECT occurred_at, kind, amount, balance_after
                   FROM bankroll_ledger
                   WHERE balance_after IS NOT NULL
                   ORDER BY id DESC LIMIT ?""",
                (max(int(limit), 1),),
            ).fetchall()
        return [
            {
                "occurred_at": row["occurred_at"],
                "kind": row["kind"],
                "amount": str(_money(row["amount"])),
                "balance": str(_money(row["balance_after"])),
            }
            for row in reversed(rows)
        ]

    def _pick_breakdown(self, label_sql: str, label_key: str) -> list[dict]:
        with self.db.connect() as conn:
            rows = conn.execute(
                f"""SELECT {label_sql} AS {label_key}, outcome, COUNT(*) AS n
                    FROM picks_v2
                    GROUP BY {label_sql}, outcome
                    ORDER BY {label_key} COLLATE NOCASE"""
            ).fetchall()
        return self._group_outcomes(rows, label_key)

    @staticmethod
    def _group_outcomes(rows, label_key: str) -> list[dict]:
        grouped: dict[object, dict[str, int]] = defaultdict(dict)
        for row in rows:
            grouped[row[label_key]][row["outcome"]] = int(row["n"])
        result = []
        for label, outcomes in grouped.items():
            won, lost = outcomes.get("won", 0), outcomes.get("lost", 0)
            result.append({
                label_key: label,
                "played": sum(outcomes.values()),
                "won": won,
                "lost": lost,
                "draw": outcomes.get("draw", 0),
                "void": outcomes.get("void", 0),
                "pending": outcomes.get("pending", 0),
                "win_percentage": _pct(won, lost),
            })
        return result

    @staticmethod
    def _group_ticket_status(rows, label_key: str) -> list[dict]:
        grouped: dict[object, dict[str, int]] = defaultdict(dict)
        for row in rows:
            grouped[row[label_key]][row["status"]] = int(row["n"])
        result = []
        for label, statuses in grouped.items():
            won, lost = statuses.get("won", 0), statuses.get("lost", 0)
            result.append({
                label_key: label,
                "tickets": sum(statuses.values()),
                "won": won,
                "lost": lost,
                "void": statuses.get("void", 0),
                "partial": statuses.get("partial", 0),
                "pending": statuses.get("pending", 0),
                "win_percentage": _pct(won, lost),
            })
        return result
