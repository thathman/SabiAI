from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from pathlib import Path

from .sqlite import SabiDatabase


class AdvancedAnalytics:
    """Read-only analytics for ticket evolution and observed bookmaker prices."""

    def __init__(self, database: SabiDatabase | str | Path):
        self.db = database if isinstance(database, SabiDatabase) else SabiDatabase(database)

    def ticket_version_outcomes(self, limit: int = 250) -> dict:
        """Compare each edited/converted child ticket with its direct parent."""
        with self.db.connect() as conn:
            rows = conn.execute(
                """SELECT
                     child.id AS child_id,
                     child.parent_ticket_id AS parent_id,
                     child.source_type AS child_source_type,
                     child.status AS child_status,
                     child.combined_odds AS child_combined_odds,
                     child.created_at AS child_created_at,
                     parent.source_type AS parent_source_type,
                     parent.status AS parent_status,
                     parent.combined_odds AS parent_combined_odds,
                     parent.created_at AS parent_created_at
                   FROM tickets child
                   JOIN tickets parent ON parent.id=child.parent_ticket_id
                   ORDER BY child.created_at DESC
                   LIMIT ?""",
                (max(1, int(limit)),),
            ).fetchall()

        pairs = []
        summary = defaultdict(int)
        for row in rows:
            parent = str(row["parent_status"] or "pending")
            child = str(row["child_status"] or "pending")
            comparison = self._outcome_comparison(parent, child)
            summary[comparison] += 1
            parent_odds = self._decimal(row["parent_combined_odds"])
            child_odds = self._decimal(row["child_combined_odds"])
            pairs.append(
                {
                    "parent_id": row["parent_id"],
                    "child_id": row["child_id"],
                    "parent_source_type": row["parent_source_type"],
                    "child_source_type": row["child_source_type"],
                    "parent_status": parent,
                    "child_status": child,
                    "comparison": comparison,
                    "parent_combined_odds": str(parent_odds) if parent_odds is not None else None,
                    "child_combined_odds": str(child_odds) if child_odds is not None else None,
                    "combined_odds_change": (
                        str((child_odds - parent_odds).quantize(Decimal("0.01")))
                        if parent_odds is not None and child_odds is not None
                        else None
                    ),
                    "parent_created_at": row["parent_created_at"],
                    "child_created_at": row["child_created_at"],
                }
            )
        return {
            "pairs": pairs,
            "summary": {
                "total_pairs": len(pairs),
                "improved_result": summary["improved_result"],
                "worsened_result": summary["worsened_result"],
                "both_won": summary["both_won"],
                "both_lost": summary["both_lost"],
                "other_or_unsettled": summary["other_or_unsettled"],
            },
        }

    def bookmaker_price_history(self, limit: int = 100) -> list[dict]:
        """Summarize observed price movement per bookmaker/event/market text."""
        with self.db.connect() as conn:
            rows = conn.execute(
                """SELECT target_bookmaker_slug, event, market,
                          COUNT(*) AS observations,
                          MIN(observed_at) AS first_observed_at,
                          MAX(observed_at) AS last_observed_at,
                          MIN(CAST(decimal_odds AS REAL)) AS min_odds,
                          MAX(CAST(decimal_odds AS REAL)) AS max_odds
                   FROM bookmaker_offer_observations
                   GROUP BY target_bookmaker_slug, lower(event), lower(market)
                   ORDER BY last_observed_at DESC
                   LIMIT ?""",
                (max(1, int(limit)),),
            ).fetchall()

            result = []
            for row in rows:
                first = conn.execute(
                    """SELECT decimal_odds FROM bookmaker_offer_observations
                       WHERE target_bookmaker_slug=? AND lower(event)=lower(?) AND lower(market)=lower(?)
                       ORDER BY observed_at ASC, ingested_at ASC LIMIT 1""",
                    (row["target_bookmaker_slug"], row["event"], row["market"]),
                ).fetchone()
                latest = conn.execute(
                    """SELECT decimal_odds FROM bookmaker_offer_observations
                       WHERE target_bookmaker_slug=? AND lower(event)=lower(?) AND lower(market)=lower(?)
                       ORDER BY observed_at DESC, ingested_at DESC LIMIT 1""",
                    (row["target_bookmaker_slug"], row["event"], row["market"]),
                ).fetchone()
                first_odds = self._decimal(first[0]) if first else None
                latest_odds = self._decimal(latest[0]) if latest else None
                result.append(
                    {
                        "bookmaker": row["target_bookmaker_slug"],
                        "event": row["event"],
                        "market": row["market"],
                        "observations": int(row["observations"]),
                        "first_observed_at": row["first_observed_at"],
                        "last_observed_at": row["last_observed_at"],
                        "first_odds": str(first_odds) if first_odds is not None else None,
                        "latest_odds": str(latest_odds) if latest_odds is not None else None,
                        "change": (
                            str((latest_odds - first_odds).quantize(Decimal("0.001")))
                            if first_odds is not None and latest_odds is not None
                            else None
                        ),
                        "min_odds": str(Decimal(str(row["min_odds"])).quantize(Decimal("0.001"))),
                        "max_odds": str(Decimal(str(row["max_odds"])).quantize(Decimal("0.001"))),
                    }
                )
        return result

    def latest_price_disagreements(self, limit: int = 50) -> list[dict]:
        """Show latest observed cross-book price gaps for identical event/market text.

        This is historical monitoring only. It does not override the strict live comparison
        engine, which still performs freshness and settlement-equivalence checks before use.
        """
        with self.db.connect() as conn:
            rows = conn.execute(
                """WITH ranked AS (
                     SELECT *,
                            ROW_NUMBER() OVER (
                              PARTITION BY target_bookmaker_slug, lower(event), lower(market)
                              ORDER BY observed_at DESC, ingested_at DESC
                            ) AS rn
                     FROM bookmaker_offer_observations
                   )
                   SELECT event, market,
                          COUNT(DISTINCT target_bookmaker_slug) AS bookmakers,
                          MIN(CAST(decimal_odds AS REAL)) AS min_odds,
                          MAX(CAST(decimal_odds AS REAL)) AS max_odds,
                          MAX(observed_at) AS latest_observed_at
                   FROM ranked
                   WHERE rn=1
                   GROUP BY lower(event), lower(market)
                   HAVING COUNT(DISTINCT target_bookmaker_slug) >= 2
                   ORDER BY (MAX(CAST(decimal_odds AS REAL))-MIN(CAST(decimal_odds AS REAL))) DESC,
                            latest_observed_at DESC
                   LIMIT ?""",
                (max(1, int(limit)),),
            ).fetchall()
        return [
            {
                "event": row["event"],
                "market": row["market"],
                "bookmakers": int(row["bookmakers"]),
                "lowest_latest_odds": str(Decimal(str(row["min_odds"])).quantize(Decimal("0.001"))),
                "highest_latest_odds": str(Decimal(str(row["max_odds"])).quantize(Decimal("0.001"))),
                "latest_gap": str(
                    (Decimal(str(row["max_odds"])) - Decimal(str(row["min_odds"]))).quantize(Decimal("0.001"))
                ),
                "latest_observed_at": row["latest_observed_at"],
            }
            for row in rows
        ]

    @staticmethod
    def _outcome_comparison(parent: str, child: str) -> str:
        if parent == "lost" and child == "won":
            return "improved_result"
        if parent == "won" and child == "lost":
            return "worsened_result"
        if parent == "won" and child == "won":
            return "both_won"
        if parent == "lost" and child == "lost":
            return "both_lost"
        return "other_or_unsettled"

    @staticmethod
    def _decimal(value) -> Decimal | None:
        if value is None or str(value).strip() == "":
            return None
        return Decimal(str(value))
