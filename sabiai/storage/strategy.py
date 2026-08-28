from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from .sqlite import SabiDatabase


class StrategyPlanStore:
    """Durable read model for the strategies Sabi Boy considered on each scan."""

    def __init__(self, database: SabiDatabase | str | Path):
        self.db = database if isinstance(database, SabiDatabase) else SabiDatabase(database)

    def save_many(self, plans: Iterable[dict]) -> list[dict]:
        saved: list[dict] = []
        with self.db.transaction() as conn:
            for plan in plans:
                plan_id = str(plan.get("id") or "").strip()
                code = str(plan.get("strategy_code") or "").strip()
                name = str(plan.get("name") or "").strip()
                generated_at = str(plan.get("generated_at") or "").strip()
                if not plan_id or not code or not name or not generated_at:
                    raise ValueError("A strategy plan needs id, strategy_code, name and generated_at.")
                candidates = plan.get("candidates")
                if not isinstance(candidates, list):
                    candidates = []
                chain = plan.get("chain")
                if not isinstance(chain, dict):
                    chain = {}
                conn.execute(
                    """INSERT INTO strategy_plans(
                           id,strategy_code,name,status,target_odds,combined_odds,
                           suggested_stake,confidence_pct,rationale,candidate_count,
                           candidates_json,chain_json,source_run_id,generated_at,expires_at
                       ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                       ON CONFLICT(id) DO UPDATE SET
                           status=excluded.status,
                           target_odds=excluded.target_odds,
                           combined_odds=excluded.combined_odds,
                           suggested_stake=excluded.suggested_stake,
                           confidence_pct=excluded.confidence_pct,
                           rationale=excluded.rationale,
                           candidate_count=excluded.candidate_count,
                           candidates_json=excluded.candidates_json,
                           chain_json=excluded.chain_json,
                           source_run_id=excluded.source_run_id,
                           generated_at=excluded.generated_at,
                           expires_at=excluded.expires_at""",
                    (
                        plan_id,
                        code,
                        name,
                        str(plan.get("status") or "watch"),
                        _optional_text(plan.get("target_odds")),
                        _optional_text(plan.get("combined_odds")),
                        _optional_text(plan.get("suggested_stake")),
                        _optional_number(plan.get("confidence_pct")),
                        str(plan.get("rationale") or "")[:1000],
                        int(plan.get("candidate_count") or len(candidates)),
                        json.dumps(candidates, ensure_ascii=False, separators=(",", ":")),
                        json.dumps(chain, ensure_ascii=False, separators=(",", ":")),
                        _optional_text(plan.get("source_run_id")),
                        generated_at,
                        _optional_text(plan.get("expires_at")),
                    ),
                )
                saved.append(dict(plan, candidates=candidates, chain=chain))
        return saved

    def latest(self, *, limit: int = 20, strategy_code: str | None = None) -> list[dict]:
        limit = max(1, min(int(limit), 200))
        where = ""
        params: list[object] = []
        if strategy_code:
            where = "WHERE strategy_code=?"
            params.append(strategy_code.strip())
        params.append(limit)
        with self.db.connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM strategy_plans {where} ORDER BY generated_at DESC, created_at DESC LIMIT ?",
                tuple(params),
            ).fetchall()
        return [self._row(row) for row in rows]

    def latest_by_strategy(self) -> list[dict]:
        with self.db.connect() as conn:
            rows = conn.execute(
                """SELECT p.*
                   FROM strategy_plans p
                   JOIN (
                     SELECT strategy_code, MAX(generated_at) AS latest_at
                     FROM strategy_plans GROUP BY strategy_code
                   ) latest ON latest.strategy_code=p.strategy_code AND latest.latest_at=p.generated_at
                   ORDER BY p.strategy_code"""
            ).fetchall()
        return [self._row(row) for row in rows]

    @staticmethod
    def _row(row) -> dict:
        try:
            candidates = json.loads(row["candidates_json"] or "[]")
        except (TypeError, ValueError, json.JSONDecodeError):
            candidates = []
        try:
            chain = json.loads(row["chain_json"] or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            chain = {}
        return {
            "id": row["id"],
            "strategy_code": row["strategy_code"],
            "name": row["name"],
            "status": row["status"],
            "target_odds": row["target_odds"],
            "combined_odds": row["combined_odds"],
            "suggested_stake": row["suggested_stake"],
            "confidence_pct": row["confidence_pct"],
            "rationale": row["rationale"],
            "candidate_count": int(row["candidate_count"] or 0),
            "candidates": candidates if isinstance(candidates, list) else [],
            "chain": chain if isinstance(chain, dict) else {},
            "source_run_id": row["source_run_id"],
            "generated_at": row["generated_at"],
            "expires_at": row["expires_at"],
        }


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_number(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
