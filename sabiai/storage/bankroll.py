from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

from sabiai.storage.sqlite import SabiDatabase


def _money(value: Decimal | int | float | str) -> Decimal:
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError("Amount must be a number.") from exc


@dataclass(frozen=True, slots=True)
class LedgerEntry:
    id: int
    occurred_at: str
    kind: str
    amount: Decimal
    balance_after: Decimal | None
    pick_id: str | None = None
    ticket_id: str | None = None
    legacy_bet_id: str | None = None
    note: str | None = None


class BankrollLedger:
    """Single V2 money ledger. Amounts are signed internally."""

    VALID_KINDS = {
        "opening_balance",
        "deposit",
        "withdrawal",
        "stake",
        "payout",
        "refund",
        "adjustment",
    }

    def __init__(self, database: SabiDatabase | str | Path):
        self.db = database if isinstance(database, SabiDatabase) else SabiDatabase(database)

    def current_balance(self) -> Decimal:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT balance_after FROM bankroll_ledger WHERE balance_after IS NOT NULL ORDER BY id DESC LIMIT 1"
            ).fetchone()
        return _money(row[0]) if row and row[0] is not None else Decimal("0.00")

    def record(
        self,
        kind: str,
        amount: Decimal | int | float | str,
        *,
        pick_id: str | None = None,
        ticket_id: str | None = None,
        legacy_bet_id: str | None = None,
        note: str | None = None,
        occurred_at: datetime | str | None = None,
    ) -> LedgerEntry:
        kind_key = kind.strip().casefold().replace(" ", "_")
        if kind_key not in self.VALID_KINDS:
            raise ValueError(f"Unknown bankroll entry kind: {kind}")
        money = _money(amount)
        if money == 0:
            raise ValueError("Bankroll entry amount cannot be zero.")
        if kind_key in {"stake", "withdrawal"} and money > 0:
            money = -money
        if kind_key in {"deposit", "payout", "refund", "opening_balance"} and money < 0:
            raise ValueError(f"{kind_key} must use a positive amount.")

        stamp = occurred_at or datetime.now(timezone.utc)
        stamp_text = stamp if isinstance(stamp, str) else stamp.isoformat()
        with self.db.transaction() as conn:
            row = conn.execute(
                "SELECT balance_after FROM bankroll_ledger WHERE balance_after IS NOT NULL ORDER BY id DESC LIMIT 1"
            ).fetchone()
            previous = _money(row[0]) if row and row[0] is not None else Decimal("0.00")
            balance_after = (previous + money).quantize(Decimal("0.01"))
            cursor = conn.execute(
                """INSERT INTO bankroll_ledger(
                    occurred_at, kind, amount, balance_after, pick_id, ticket_id, legacy_bet_id, note
                ) VALUES(?,?,?,?,?,?,?,?)""",
                (stamp_text, kind_key, str(money), str(balance_after), pick_id, ticket_id, legacy_bet_id, note),
            )
            entry_id = int(cursor.lastrowid)

        return LedgerEntry(
            id=entry_id,
            occurred_at=stamp_text,
            kind=kind_key,
            amount=money,
            balance_after=balance_after,
            pick_id=pick_id,
            ticket_id=ticket_id,
            legacy_bet_id=legacy_bet_id,
            note=note,
        )

    def history(self, limit: int = 100) -> list[LedgerEntry]:
        if limit < 1:
            return []
        with self.db.connect() as conn:
            rows = conn.execute(
                """SELECT id, occurred_at, kind, amount, balance_after, pick_id, ticket_id, legacy_bet_id, note
                   FROM bankroll_ledger ORDER BY id DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        return [
            LedgerEntry(
                id=int(row["id"]),
                occurred_at=row["occurred_at"],
                kind=row["kind"],
                amount=_money(row["amount"]),
                balance_after=_money(row["balance_after"]) if row["balance_after"] is not None else None,
                pick_id=row["pick_id"],
                ticket_id=row["ticket_id"],
                legacy_bet_id=row["legacy_bet_id"],
                note=row["note"],
            )
            for row in rows
        ]

    def reconcile(self, expected_balance: Decimal | int | float | str) -> dict:
        expected = _money(expected_balance)
        actual = self.current_balance()
        difference = (actual - expected).quantize(Decimal("0.01"))
        return {"expected": expected, "actual": actual, "difference": difference, "matches": difference == 0}
