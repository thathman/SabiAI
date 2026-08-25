import pytest

from sabiai.settlement import SettlementService
from sabiai.storage import SabiDatabase


def _db(tmp_path):
    db = SabiDatabase(tmp_path / "settlement.db")
    db.initialize()
    with db.transaction() as conn:
        conn.execute("INSERT INTO sports(id,slug,name) VALUES('sport_football','football','Football')")
        conn.execute(
            "INSERT INTO events(id,sport_id,name,starts_at,status) VALUES('e1','sport_football','Arsenal vs Chelsea','2026-08-25T18:00:00+00:00','scheduled')"
        )
        for market_id, label in (("m1", "Arsenal to win"), ("m2", "Over 2.5 goals")):
            conn.execute(
                "INSERT INTO markets(id,event_id,kind,label) VALUES(?,?,?,?)",
                (market_id, "e1", "winner" if market_id == "m1" else "total", label),
            )
            conn.execute(
                "INSERT INTO selections(id,market_id,label) VALUES(?,?,?)",
                (f"s_{market_id}", market_id, label),
            )
        conn.execute(
            """INSERT INTO picks_v2(id,event_id,market_id,selection_id,decimal_odds,outcome,created_at)
               VALUES('p1','e1','m1','s_m1','1.80','pending','2026-08-25T10:00:00+00:00')"""
        )
        conn.execute(
            """INSERT INTO tickets(id,source_type,status,combined_odds,created_at)
               VALUES('t1','instruction','pending','3.24','2026-08-25T10:00:00+00:00')"""
        )
        conn.execute(
            """INSERT INTO ticket_legs(id,ticket_id,leg_no,event_id,market_id,selection_id,decimal_odds,outcome)
               VALUES('l1','t1',1,'e1','m1','s_m1','1.80','pending')"""
        )
        conn.execute(
            """INSERT INTO ticket_legs(id,ticket_id,leg_no,event_id,market_id,selection_id,decimal_odds,outcome)
               VALUES('l2','t1',2,'e1','m2','s_m2','1.80','pending')"""
        )
    return db


def test_pick_settlement_is_idempotent_and_corrections_are_audited(tmp_path):
    db = _db(tmp_path)
    service = SettlementService(db)

    first = service.settle_pick("p1", "win", source="test")
    assert first.changed is True
    assert first.new_outcome == "won"

    again = service.settle_pick("p1", "won", source="test")
    assert again.changed is False

    with pytest.raises(ValueError):
        service.settle_pick("p1", "lost", source="test")

    corrected = service.settle_pick(
        "p1", "lost", source="manual", correction=True, reason="Official result corrected"
    )
    assert corrected.changed is True

    with db.connect() as conn:
        audits = conn.execute(
            "SELECT previous_outcome,new_outcome FROM settlement_audit WHERE entity_type='pick' AND entity_id='p1' ORDER BY id"
        ).fetchall()
    assert [(row[0], row[1]) for row in audits] == [("pending", "won"), ("won", "lost")]


def test_ticket_status_is_derived_from_legs(tmp_path):
    db = _db(tmp_path)
    service = SettlementService(db)

    _, ticket = service.settle_ticket_leg("l1", "won", source="test")
    assert ticket.new_status == "pending"

    _, ticket = service.settle_ticket_leg("l2", "lost", source="test")
    assert ticket.new_status == "lost"

    _, ticket = service.settle_ticket_leg(
        "l2",
        "won",
        source="manual",
        correction=True,
        reason="Wrong leg result imported",
    )
    assert ticket.new_status == "won"


def test_void_event_voids_related_records_and_refreshes_ticket(tmp_path):
    db = _db(tmp_path)
    service = SettlementService(db)

    result = service.void_event("e1", source="official", reason="Event cancelled")
    assert result["picks_voided"] == 1
    assert result["legs_voided"] == 2
    assert result["tickets_refreshed"] == ["t1"]

    with db.connect() as conn:
        pick = conn.execute("SELECT outcome FROM picks_v2 WHERE id='p1'").fetchone()[0]
        ticket = conn.execute("SELECT status FROM tickets WHERE id='t1'").fetchone()[0]
    assert pick == "void"
    assert ticket == "void"


def test_ticket_payout_is_not_recorded_twice(tmp_path):
    db = _db(tmp_path)
    service = SettlementService(db)

    first = service.record_ticket_payout("t1", "25.00", source="test")
    second = service.record_ticket_payout("t1", "25.00", source="test")
    assert first["ledger_entry_id"] is not None
    assert second["ledger_entry_id"] is None

    with db.connect() as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM bankroll_ledger WHERE ticket_id='t1' AND kind='payout'"
        ).fetchone()[0]
    assert count == 1
