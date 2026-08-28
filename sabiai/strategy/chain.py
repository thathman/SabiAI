from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

from sabiai.storage import SabiDatabase


class StrategyChainStore:
    """Own the state of Sabi Boy's 30-day, win-to-compound daily chain."""

    CHAIN_ID = "sabi_boy_daily_chain_1_30"
    CODE = "daily_chain_1_30"
    NAME = "Daily 1.30 Chain"
    TARGET_DAYS = 30
    TARGET_ODDS = Decimal("1.30")
    STARTING_STAKE = Decimal("1000.00")

    def __init__(self, database: SabiDatabase | str | Path):
        self.db = database if isinstance(database, SabiDatabase) else SabiDatabase(database)

    def ensure(self) -> dict:
        with self.db.transaction() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO strategy_chain_state(
                       id,owner,strategy_code,name,target_days,target_odds,
                       starting_stake,current_stake,status
                   ) VALUES(?,?,?,?,?,?,?,?,?)""",
                (
                    self.CHAIN_ID,
                    "sabi_boy",
                    self.CODE,
                    self.NAME,
                    self.TARGET_DAYS,
                    str(self.TARGET_ODDS),
                    str(self.STARTING_STAKE),
                    str(self.STARTING_STAKE),
                    "ready",
                ),
            )
            completed = conn.execute(
                "SELECT status,starting_stake FROM strategy_chain_state WHERE id=?",
                (self.CHAIN_ID,),
            ).fetchone()
            if completed is not None and completed["status"] == "completed":
                # A finished 30-day run is visible until the next daily wake. At
                # that wake a new cycle starts from the configured base stake.
                conn.execute(
                    """UPDATE strategy_chain_state
                       SET status='ready', completed_days=0, current_stake=starting_stake,
                           active_ticket_id=NULL, updated_at=CURRENT_TIMESTAMP
                       WHERE id=?""",
                    (self.CHAIN_ID,),
                )
            # Pending tickets from before the explicit chain state existed are
            # deliberately not adopted. They may contain a provider-selected
            # future fixture; leaving them as history prevents an old run from
            # blocking today's chain or creating a second active Day 1 state.
        return self.get()

    def get(self) -> dict:
        with self.db.connect() as conn:
            row = conn.execute("SELECT * FROM strategy_chain_state WHERE id=?", (self.CHAIN_ID,)).fetchone()
        if row is None:
            return self.ensure()
        return self._row(row)

    def attach_ticket(self, ticket_id: str) -> dict:
        self.ensure()
        with self.db.transaction() as conn:
            state = conn.execute(
                "SELECT status,completed_days,last_outcome,starting_stake FROM strategy_chain_state WHERE id=?",
                (self.CHAIN_ID,),
            ).fetchone()
            ticket = conn.execute("SELECT stake FROM tickets WHERE id=?", (str(ticket_id),)).fetchone()
            # Direct callers that materialize an older plan may not have passed a
            # chain context to the planner. Adopt that first ticket's stake so the
            # durable chain and the ledger cannot disagree about Day 1.
            adopt_stake = None
            if (
                state is not None
                and state["status"] == "ready"
                and int(state["completed_days"] or 0) == 0
                and state["last_outcome"] is None
                and ticket is not None
                and ticket["stake"] is not None
            ):
                adopt_stake = str(_money(ticket["stake"]))
            conn.execute(
                """UPDATE strategy_chain_state
                   SET starting_stake=COALESCE(?, starting_stake),
                       current_stake=COALESCE(?, current_stake),
                       status='pending', active_ticket_id=?, updated_at=CURRENT_TIMESTAMP
                   WHERE id=? AND status IN ('ready','voided')""",
                (adopt_stake, adopt_stake, str(ticket_id), self.CHAIN_ID),
            )
        return self.get()

    def settle_ticket(self, ticket_id: str, status: str, combined_odds: object) -> dict:
        """Advance only after a fully won ticket; losses reset to Day 1."""

        outcome = str(status or "").strip().casefold()
        if outcome not in {"won", "lost", "void", "partial"}:
            return self.get()
        with self.db.transaction() as conn:
            row = conn.execute("SELECT * FROM strategy_chain_state WHERE id=?", (self.CHAIN_ID,)).fetchone()
            if row is None or row["active_ticket_id"] != ticket_id:
                return self._row(row) if row is not None else self.ensure()
            now = datetime.now(timezone.utc).isoformat()
            completed = int(row["completed_days"] or 0)
            starting = _money(row["starting_stake"])
            current = _money(row["current_stake"])
            if outcome == "won":
                odds = _money(combined_odds)
                next_stake = (current * odds).quantize(Decimal("0.01"))
                day = completed + 1
                if day >= int(row["target_days"] or self.TARGET_DAYS):
                    new_status = "completed"
                    new_completed = int(row["target_days"] or self.TARGET_DAYS)
                    new_stake = next_stake
                    cycles = int(row["cycle_count"] or 0) + 1
                else:
                    new_status = "ready"
                    new_completed = day
                    new_stake = next_stake
                    cycles = int(row["cycle_count"] or 0)
            elif outcome == "lost":
                new_status = "ready"
                new_completed = 0
                new_stake = starting
                cycles = int(row["cycle_count"] or 0)
            else:
                # A void/partial result does not count as a win and leaves the
                # current day and stake available for a fresh eligible fixture.
                new_status = "ready"
                new_completed = completed
                new_stake = current
                cycles = int(row["cycle_count"] or 0)
            conn.execute(
                """UPDATE strategy_chain_state
                   SET status=?,active_ticket_id=NULL,last_outcome=?,last_settled_at=?,
                       completed_days=?,current_stake=?,cycle_count=?,updated_at=?
                   WHERE id=?""",
                (
                    new_status,
                    outcome,
                    now,
                    new_completed,
                    str(new_stake),
                    cycles,
                    now,
                    self.CHAIN_ID,
                ),
            )
            result = conn.execute("SELECT * FROM strategy_chain_state WHERE id=?", (self.CHAIN_ID,)).fetchone()
        return self._row(result)

    @classmethod
    def _row(cls, row) -> dict:
        return {
            "id": row["id"],
            "owner": row["owner"],
            "strategy_code": row["strategy_code"],
            "name": row["name"],
            "target_days": int(row["target_days"] or cls.TARGET_DAYS),
            "target_odds": str(_money(row["target_odds"])),
            "starting_stake": str(_money(row["starting_stake"])),
            "current_stake": str(_money(row["current_stake"])),
            "completed_days": int(row["completed_days"] or 0),
            "current_day": min(int(row["completed_days"] or 0) + 1, int(row["target_days"] or cls.TARGET_DAYS)),
            "status": row["status"],
            "active_ticket_id": row["active_ticket_id"],
            "last_outcome": row["last_outcome"],
            "last_settled_at": row["last_settled_at"],
            "cycle_count": int(row["cycle_count"] or 0),
            "updated_at": row["updated_at"],
        }


def _money(value: object) -> Decimal:
    try:
        return Decimal(str(value or "0")).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("Chain money value must be numeric.") from exc
