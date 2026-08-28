from __future__ import annotations

from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path

from sabiai.storage import BankrollLedger, PickRecordService, SabiDatabase
from .chain import StrategyChainStore


class StrategyTicketService:
    """Materialize ready strategy plans as auditable Sabi Boy tickets.

    The service only writes the internal V2 record. It never contacts a bookmaker or
    submits a ticket. Candidate legs are retained as tips so the ticket's event and
    market identity remain inspectable without creating duplicate staked picks.
    """

    MATERIALIZED_CODES = {"daily_chain_1_30", "weekly_long_shot_1000"}

    def __init__(self, database: SabiDatabase | str | Path):
        self.db = database if isinstance(database, SabiDatabase) else SabiDatabase(database)

    def materialize(
        self,
        plans: list[dict],
        *,
        model: str | None = None,
        source_run_id: str | None = None,
        chain_date: str | None = None,
    ) -> list[dict]:
        results: list[dict] = []
        for plan in plans:
            if plan.get("strategy_code") not in self.MATERIALIZED_CODES:
                continue
            if plan.get("status") != "ready" or not plan.get("candidates"):
                continue
            try:
                results.append(
                    self._materialize_one(
                        plan,
                        model=model,
                        source_run_id=source_run_id,
                        chain_date=chain_date,
                    )
                )
            except (KeyError, TypeError, ValueError, InvalidOperation) as exc:
                results.append({"strategy_code": plan.get("strategy_code"), "skipped": True, "reason": str(exc)[:300]})
        return results

    def _materialize_one(
        self,
        plan: dict,
        *,
        model: str | None,
        source_run_id: str | None,
        chain_date: str | None,
    ) -> dict:
        code = str(plan["strategy_code"])
        run_key = str(source_run_id or plan.get("source_run_id") or plan.get("generated_at") or "").strip()
        if not run_key:
            raise ValueError("A strategy ticket needs a source run id.")
        ticket_id = "strategy_ticket_" + hashlib.sha256(f"{code}|{run_key}".encode()).hexdigest()[:24]
        with self.db.connect() as conn:
            existing = conn.execute("SELECT id,stake,status FROM tickets WHERE id=?", (ticket_id,)).fetchone()
        if existing is not None:
            if code == StrategyChainStore.CODE and existing["status"] == "pending":
                StrategyChainStore(self.db).attach_ticket(ticket_id)
            return {"id": ticket_id, "strategy_code": code, "existing": True, "status": existing["status"], "stake": existing["stake"]}

        if code == StrategyChainStore.CODE and chain_date:
            chain_state = StrategyChainStore(self.db).ensure()
            if chain_state.get("active_ticket_id") or chain_state.get("last_ticket_date") == chain_date:
                return {
                    "id": ticket_id,
                    "strategy_code": code,
                    "skipped": True,
                    "reason": "The daily chain already has a position for this calendar date.",
                }

        stake = _money(plan.get("suggested_stake"))
        candidate_pick_ids: list[str] = []
        for candidate in plan.get("candidates") or []:
            source = str(candidate.get("source") or "")
            candidate_pick_ids.append(
                PickRecordService(self.db).record(
                    {
                        "sport": candidate.get("sport") or "football",
                        "competition": candidate.get("competition"),
                        "event": candidate.get("event"),
                        "starts_at": candidate.get("starts_at"),
                        "market": candidate.get("market") or "Match winner",
                        "pick": candidate.get("pick"),
                        "decimal_odds": candidate.get("decimal_odds"),
                        "confidence_pct": candidate.get("confidence_pct"),
                        "rationale": candidate.get("reason"),
                        "strategy": plan.get("name"),
                        "strategy_code": code,
                        "source_name": source,
                        "source_event_id": candidate.get("source_event_id"),
                        "bookmaker": _bookmaker_for_source(source),
                        "source_run_id": run_key,
                        "model_generation": model,
                        "owner": "sabi_boy",
                        "record_kind": "tip",
                        "selected": False,
                        "stake": "0",
                    }
                )["id"]
            )

        with self.db.transaction() as conn:
            rows = [
                conn.execute(
                """SELECT p.id AS pick_id,p.event_id,p.market_id,p.selection_id,p.bookmaker_id,p.decimal_odds
                       FROM picks_v2 p WHERE p.id=?""",
                    (pick_id,),
                ).fetchone()
                for pick_id in candidate_pick_ids
            ]
            if any(row is None for row in rows):
                raise ValueError("A strategy ticket candidate could not be resolved to a canonical selection.")
            conn.execute(
                """INSERT INTO tickets(
                       id,source_type,source_reference,status,combined_odds,stake,notes_json,owner,strategy_code
                   ) VALUES(?,?,?,?,?,?,?,?,?)""",
                (
                    ticket_id,
                    "strategy",
                    run_key,
                    "pending",
                    str(plan.get("combined_odds")),
                    str(stake),
                    json.dumps([str(plan.get("rationale") or "")], ensure_ascii=False),
                    "sabi_boy",
                    code,
                ),
            )
            for index, row in enumerate(rows, start=1):
                leg_id = f"{ticket_id}_leg_{index}"
                conn.execute(
                    """INSERT INTO ticket_legs(
                           id,ticket_id,leg_no,event_id,market_id,selection_id,bookmaker_id,decimal_odds,locked,outcome,pick_id
                       ) VALUES(?,?,?,?,?,?,?,?,0,'pending',?)""",
                    (leg_id, ticket_id, index, row["event_id"], row["market_id"], row["selection_id"], row["bookmaker_id"], row["decimal_odds"], row["pick_id"]),
                )
        if stake > 0:
            BankrollLedger(self.db).record("stake", stake, ticket_id=ticket_id, note=f"Stake for {plan.get('name') or code}")
        if code == StrategyChainStore.CODE:
            StrategyChainStore(self.db).attach_ticket(ticket_id, local_date=chain_date)
        return {
            "id": ticket_id,
            "strategy_code": code,
            "existing": False,
            "status": "pending",
            "stake": str(stake),
            "legs": len(candidate_pick_ids),
        }


def _money(value) -> Decimal:
    try:
        return Decimal(str(value or "0")).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("Strategy stake must be a number.") from exc


def _bookmaker_for_source(source: object) -> str | None:
    text = str(source or "").casefold()
    if "sportybet" in text:
        return "sportybet"
    if "bet9ja" in text:
        return "bet9ja"
    return None
