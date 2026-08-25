from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from sabiai.domain.types import Outcome, TicketStatus
from sabiai.storage import BankrollLedger, SabiDatabase


@dataclass(frozen=True, slots=True)
class SettlementResult:
    entity_type: str
    entity_id: str
    previous_outcome: str
    new_outcome: str
    changed: bool
    ticket_id: str | None = None
    note: str | None = None


@dataclass(frozen=True, slots=True)
class TicketSettlementResult:
    ticket_id: str
    previous_status: str
    new_status: str
    changed: bool
    pending_legs: int
    won_legs: int
    lost_legs: int
    draw_legs: int
    void_legs: int


class SettlementService:
    """Canonical V2 settlement path for picks and ticket legs.

    Repeating the same settlement is a no-op. Reversing or changing a settled result requires
    an explicit correction flag and reason, and every material change is written to the audit
    table. Ticket status is derived from its legs rather than independently guessed.
    """

    FINAL_OUTCOMES = {Outcome.WON.value, Outcome.LOST.value, Outcome.DRAW.value, Outcome.VOID.value}

    def __init__(self, database: SabiDatabase | str | Path):
        self.db = database if isinstance(database, SabiDatabase) else SabiDatabase(database)

    @staticmethod
    def normalize_outcome(value: Outcome | str) -> str:
        if isinstance(value, Outcome):
            return value.value
        text = str(value or "").strip().casefold()
        aliases = {
            "win": "won",
            "winner": "won",
            "won": "won",
            "loss": "lost",
            "lose": "lost",
            "lost": "lost",
            "draw": "draw",
            "push": "void",
            "refund": "void",
            "void": "void",
            "cancelled": "void",
            "canceled": "void",
            "pending": "pending",
        }
        outcome = aliases.get(text)
        if outcome is None:
            raise ValueError(f"Unknown settlement outcome: {value}")
        return outcome

    def settle_pick(
        self,
        pick_id: str,
        outcome: Outcome | str,
        *,
        source: str,
        reason: str | None = None,
        correction: bool = False,
        payout: Decimal | int | float | str | None = None,
        record_payout: bool = False,
    ) -> SettlementResult:
        target = self.normalize_outcome(outcome)
        with self.db.transaction() as conn:
            row = conn.execute(
                "SELECT outcome, payout FROM picks_v2 WHERE id=?", (pick_id,)
            ).fetchone()
            if row is None:
                raise KeyError(f"Unknown pick: {pick_id}")
            previous = row["outcome"]
            if previous == target:
                return SettlementResult("pick", pick_id, previous, target, False, note="Already settled to this outcome.")
            self._validate_change(previous, target, correction=correction, reason=reason)
            stamp = datetime.now(timezone.utc).isoformat() if target in self.FINAL_OUTCOMES else None
            payout_text = str(Decimal(str(payout)).quantize(Decimal("0.01"))) if payout is not None else row["payout"]
            conn.execute(
                "UPDATE picks_v2 SET outcome=?, settled_at=?, payout=? WHERE id=?",
                (target, stamp, payout_text, pick_id),
            )
            self._audit(conn, "pick", pick_id, previous, target, source, reason)

        if record_payout and payout is not None and Decimal(str(payout)) > 0:
            self._record_unique_payout(pick_id=pick_id, amount=payout, note=f"Settlement payout for {pick_id}")
        return SettlementResult("pick", pick_id, previous, target, True)

    def settle_ticket_leg(
        self,
        leg_id: str,
        outcome: Outcome | str,
        *,
        source: str,
        reason: str | None = None,
        correction: bool = False,
    ) -> tuple[SettlementResult, TicketSettlementResult]:
        target = self.normalize_outcome(outcome)
        with self.db.transaction() as conn:
            row = conn.execute(
                "SELECT ticket_id, outcome FROM ticket_legs WHERE id=?", (leg_id,)
            ).fetchone()
            if row is None:
                raise KeyError(f"Unknown ticket leg: {leg_id}")
            ticket_id = row["ticket_id"]
            previous = row["outcome"]
            changed = previous != target
            if changed:
                self._validate_change(previous, target, correction=correction, reason=reason)
                conn.execute("UPDATE ticket_legs SET outcome=? WHERE id=?", (target, leg_id))
                self._audit(conn, "ticket_leg", leg_id, previous, target, source, reason)

        ticket_result = self.refresh_ticket(ticket_id, source=source, reason=reason)
        return (
            SettlementResult(
                "ticket_leg",
                leg_id,
                previous,
                target,
                changed,
                ticket_id=ticket_id,
                note=None if changed else "Already settled to this outcome.",
            ),
            ticket_result,
        )

    def refresh_ticket(
        self,
        ticket_id: str,
        *,
        source: str = "settlement-service",
        reason: str | None = None,
    ) -> TicketSettlementResult:
        with self.db.transaction() as conn:
            ticket = conn.execute("SELECT status FROM tickets WHERE id=?", (ticket_id,)).fetchone()
            if ticket is None:
                raise KeyError(f"Unknown ticket: {ticket_id}")
            rows = conn.execute(
                "SELECT outcome, COUNT(*) AS n FROM ticket_legs WHERE ticket_id=? GROUP BY outcome",
                (ticket_id,),
            ).fetchall()
            counts = {row["outcome"]: int(row["n"]) for row in rows}
            if not counts:
                new_status = TicketStatus.DRAFT.value
            else:
                new_status = self._derive_ticket_status(counts)
            previous = ticket["status"]
            changed = previous != new_status
            if changed:
                settled_at = (
                    datetime.now(timezone.utc).isoformat()
                    if new_status in {"won", "lost", "void", "partial"}
                    else None
                )
                conn.execute(
                    "UPDATE tickets SET status=?, settled_at=? WHERE id=?",
                    (new_status, settled_at, ticket_id),
                )
                self._audit(conn, "ticket", ticket_id, previous, new_status, source, reason)

        return TicketSettlementResult(
            ticket_id=ticket_id,
            previous_status=previous,
            new_status=new_status,
            changed=changed,
            pending_legs=counts.get("pending", 0),
            won_legs=counts.get("won", 0),
            lost_legs=counts.get("lost", 0),
            draw_legs=counts.get("draw", 0),
            void_legs=counts.get("void", 0),
        )

    def record_ticket_payout(
        self,
        ticket_id: str,
        amount: Decimal | int | float | str,
        *,
        source: str = "settlement-service",
        reason: str | None = None,
    ) -> dict:
        money = Decimal(str(amount)).quantize(Decimal("0.01"))
        if money <= 0:
            raise ValueError("Ticket payout must be greater than zero.")
        with self.db.transaction() as conn:
            row = conn.execute("SELECT status, payout FROM tickets WHERE id=?", (ticket_id,)).fetchone()
            if row is None:
                raise KeyError(f"Unknown ticket: {ticket_id}")
            existing = row["payout"]
            if existing is not None and Decimal(str(existing)).quantize(Decimal("0.01")) != money:
                raise ValueError("Ticket already has a different payout. Correct the bankroll with an explicit adjustment instead of silently replacing it.")
            conn.execute("UPDATE tickets SET payout=? WHERE id=?", (str(money), ticket_id))
        entry = self._record_unique_payout(ticket_id=ticket_id, amount=money, note=reason or f"Ticket payout from {source}")
        return {"ticket_id": ticket_id, "payout": str(money), "ledger_entry_id": entry.id if entry else None}

    def void_event(self, event_id: str, *, source: str, reason: str) -> dict:
        if not reason.strip():
            raise ValueError("Voiding an event requires a reason.")
        affected_tickets: set[str] = set()
        changed_picks = changed_legs = 0
        with self.db.transaction() as conn:
            picks = conn.execute(
                "SELECT id, outcome FROM picks_v2 WHERE event_id=?", (event_id,)
            ).fetchall()
            for row in picks:
                if row["outcome"] == "void":
                    continue
                self._validate_change(row["outcome"], "void", correction=True, reason=reason)
                conn.execute(
                    "UPDATE picks_v2 SET outcome='void', settled_at=? WHERE id=?",
                    (datetime.now(timezone.utc).isoformat(), row["id"]),
                )
                self._audit(conn, "pick", row["id"], row["outcome"], "void", source, reason)
                changed_picks += 1

            legs = conn.execute(
                "SELECT id, ticket_id, outcome FROM ticket_legs WHERE event_id=?", (event_id,)
            ).fetchall()
            for row in legs:
                affected_tickets.add(row["ticket_id"])
                if row["outcome"] == "void":
                    continue
                self._validate_change(row["outcome"], "void", correction=True, reason=reason)
                conn.execute("UPDATE ticket_legs SET outcome='void' WHERE id=?", (row["id"],))
                self._audit(conn, "ticket_leg", row["id"], row["outcome"], "void", source, reason)
                changed_legs += 1

        ticket_results = [self.refresh_ticket(ticket_id, source=source, reason=reason) for ticket_id in sorted(affected_tickets)]
        return {
            "event_id": event_id,
            "picks_voided": changed_picks,
            "legs_voided": changed_legs,
            "tickets_refreshed": [result.ticket_id for result in ticket_results],
        }

    def backlog(self, *, older_than_hours: int = 24) -> dict:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=max(int(older_than_hours), 0))).isoformat()
        with self.db.connect() as conn:
            pending_picks = conn.execute(
                "SELECT COUNT(*) FROM picks_v2 WHERE outcome='pending' AND created_at<=?", (cutoff,)
            ).fetchone()[0]
            pending_tickets = conn.execute(
                "SELECT COUNT(*) FROM tickets WHERE status='pending' AND created_at<=?", (cutoff,)
            ).fetchone()[0]
            pending_legs = conn.execute(
                """SELECT COUNT(*) FROM ticket_legs l
                   JOIN tickets t ON t.id=l.ticket_id
                   WHERE l.outcome='pending' AND t.created_at<=?""",
                (cutoff,),
            ).fetchone()[0]
        return {
            "older_than_hours": int(older_than_hours),
            "pending_picks": int(pending_picks),
            "pending_tickets": int(pending_tickets),
            "pending_ticket_legs": int(pending_legs),
        }

    @staticmethod
    def _derive_ticket_status(counts: dict[str, int]) -> str:
        if counts.get("pending", 0):
            return TicketStatus.PENDING.value
        if counts.get("lost", 0):
            return TicketStatus.LOST.value
        if counts.get("draw", 0):
            return TicketStatus.PARTIAL.value
        if counts.get("won", 0):
            return TicketStatus.WON.value
        if counts.get("void", 0):
            return TicketStatus.VOID.value
        return TicketStatus.PARTIAL.value

    @staticmethod
    def _validate_change(previous: str, target: str, *, correction: bool, reason: str | None) -> None:
        if previous == target:
            return
        if previous != Outcome.PENDING.value:
            if not correction:
                raise ValueError(
                    f"{previous} is already settled. Changing it to {target} requires correction=True."
                )
            if not reason or not reason.strip():
                raise ValueError("A settlement correction requires a reason.")

    @staticmethod
    def _audit(conn, entity_type: str, entity_id: str, previous: str, target: str, source: str, reason: str | None) -> None:
        if not source or not source.strip():
            raise ValueError("Settlement source is required.")
        conn.execute(
            """INSERT INTO settlement_audit(entity_type,entity_id,previous_outcome,new_outcome,source,reason)
               VALUES(?,?,?,?,?,?)""",
            (entity_type, entity_id, previous, target, source.strip(), reason),
        )

    def _record_unique_payout(
        self,
        *,
        amount,
        pick_id: str | None = None,
        ticket_id: str | None = None,
        note: str | None = None,
    ):
        with self.db.connect() as conn:
            if pick_id:
                row = conn.execute(
                    "SELECT id FROM bankroll_ledger WHERE kind='payout' AND pick_id=? LIMIT 1",
                    (pick_id,),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT id FROM bankroll_ledger WHERE kind='payout' AND ticket_id=? LIMIT 1",
                    (ticket_id,),
                ).fetchone()
        if row:
            return None
        return BankrollLedger(self.db).record(
            "payout",
            amount,
            pick_id=pick_id,
            ticket_id=ticket_id,
            note=note,
        )
