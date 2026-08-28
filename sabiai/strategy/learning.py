from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from sabiai.storage.sqlite import SabiDatabase


class StrategyLearningService:
    """V2-native, bounded learning summaries for recorded strategy outcomes.

    Learning is deliberately advisory. It never rewrites historical picks, changes a
    stake, or silently pauses a strategy. The thresholds make the amount of evidence
    behind a recommendation explicit before a later policy layer can act on it.
    """

    MIN_SAMPLE = 8
    POLICY_SAMPLE = 15

    def __init__(self, database: SabiDatabase | str | Path):
        self.db = database if isinstance(database, SabiDatabase) else SabiDatabase(database)

    def summaries(
        self,
        *,
        owner: str = "sabi_boy",
        limit: int = 50,
    ) -> list[dict]:
        owner_key = owner.strip().casefold()
        with self.db.connect() as conn:
            rows = conn.execute(
                """SELECT COALESCE(NULLIF(strategy_code,''), NULLIF(strategy,''), 'Unspecified') AS strategy_code,
                          COALESCE(NULLIF(strategy,''), 'Unspecified') AS strategy,
                          COUNT(*) AS total,
                          SUM(CASE WHEN outcome IN ('won','lost','draw','void') THEN 1 ELSE 0 END) AS settled,
                          SUM(CASE WHEN outcome='won' THEN 1 ELSE 0 END) AS won,
                          SUM(CASE WHEN outcome='lost' THEN 1 ELSE 0 END) AS lost,
                          SUM(CASE WHEN outcome='draw' THEN 1 ELSE 0 END) AS drawn,
                          SUM(CASE WHEN outcome='void' THEN 1 ELSE 0 END) AS voided,
                          COALESCE(SUM(CAST(COALESCE(stake,'0') AS REAL)),0) AS stakes,
                          COALESCE(SUM(CAST(COALESCE(payout,'0') AS REAL)),0) AS payouts
                   FROM picks_v2
                   WHERE COALESCE(owner, 'sabi_boy')=?
                   GROUP BY strategy_code, strategy
                   ORDER BY settled DESC, total DESC, strategy COLLATE NOCASE
                   LIMIT ?""",
                (owner_key, max(1, min(int(limit), 250))),
            ).fetchall()

        result: list[dict] = []
        for row in rows:
            total = int(row["total"] or 0)
            settled = int(row["settled"] or 0)
            won = int(row["won"] or 0)
            lost = int(row["lost"] or 0)
            decided = won + lost
            win_pct = round((won / decided) * 100, 1) if decided else None
            net = (Decimal(str(row["payouts"] or 0)) - Decimal(str(row["stakes"] or 0))).quantize(Decimal("0.01"))
            policy, rationale = self._policy(settled=settled, decided=decided, win_pct=win_pct, net=net)
            result.append(
                {
                    "strategy_code": row["strategy_code"],
                    "strategy": row["strategy"],
                    "owner": owner_key,
                    "total_picks": total,
                    "settled_picks": settled,
                    "decided_picks": decided,
                    "won": won,
                    "lost": lost,
                    "draw": int(row["drawn"] or 0),
                    "void": int(row["voided"] or 0),
                    "win_percentage": win_pct,
                    "stakes": str(Decimal(str(row["stakes"] or 0)).quantize(Decimal("0.01"))),
                    "payouts": str(Decimal(str(row["payouts"] or 0)).quantize(Decimal("0.01"))),
                    "net": str(net),
                    "policy": policy,
                    "rationale": rationale,
                    "minimum_sample": self.MIN_SAMPLE,
                    "policy_sample": self.POLICY_SAMPLE,
                }
            )
        return result

    @classmethod
    def _policy(
        cls,
        *,
        settled: int,
        decided: int,
        win_pct: float | None,
        net: Decimal,
    ) -> tuple[str, str]:
        if settled < cls.MIN_SAMPLE:
            return "gathering_sample", f"Needs {cls.MIN_SAMPLE - settled} more settled result(s) before confidence changes."
        if decided < cls.POLICY_SAMPLE:
            return "hold", f"Settled sample is usable, but {cls.POLICY_SAMPLE - decided} more won/lost decisions are needed before policy changes."
        if win_pct is not None and win_pct < 45 and net < 0:
            return "review", "The recent decided record is weak and negative; keep stakes bounded and review the market mix."
        if win_pct is not None and win_pct >= 60 and net > 0:
            return "eligible_to_expand", "The recent decided record is positive; any increase should still be gradual and capped."
        return "hold", "Evidence is mixed; keep the current bounded allocation and continue observing."

