from pathlib import Path

import pytest

from sabiai.storage import BankrollLedger, PickRecordService, SabiDatabase


def test_record_pick_creates_canonical_sabi_boy_record_and_stake(tmp_path: Path):
    db = SabiDatabase(tmp_path / "v2.db")
    db.initialize()
    BankrollLedger(db).record("opening_balance", "1000")
    result = PickRecordService(db).record(
        {
            "sport": "Football",
            "event": "Arsenal vs Chelsea",
            "starts_at": "2099-08-28T18:00:00+00:00",
            "market": "Arsenal to win",
            "pick": "Arsenal",
            "decimal_odds": "1.80",
            "confidence_pct": 67,
            "stake": "20",
            "strategy": "Precision Picks",
            "strategy_code": "precision_picks",
        }
    )
    assert result["owner"] == "sabi_boy"
    assert result["selected"] is True
    with db.connect() as conn:
        row = conn.execute("SELECT owner,record_kind,stake,selected FROM picks_v2 WHERE id=?", (result["id"],)).fetchone()
    assert tuple(row) == ("sabi_boy", "pick", "20.00", 1)
    assert BankrollLedger(db).current_balance() == 980


def test_record_tip_is_unselected_and_does_not_debit_bankroll(tmp_path: Path):
    db = SabiDatabase(tmp_path / "v2.db")
    db.initialize()
    BankrollLedger(db).record("opening_balance", "1000")
    result = PickRecordService(db).record(
        {
            "sport": "Basketball",
            "event": "Home vs Away",
            "starts_at": "2099-08-28T18:00:00+00:00",
            "market": "Over 2.5 goals",
            "pick": "Over 2.5 goals",
            "decimal_odds": "1.40",
            "record_kind": "tip",
            "stake": "20",
        }
    )
    assert result["record_kind"] == "tip"
    assert result["selected"] is False
    assert BankrollLedger(db).current_balance() == 1000


def test_record_pick_rejects_removed_bookmaker(tmp_path: Path):
    db = SabiDatabase(tmp_path / "v2.db")
    db.initialize()
    with pytest.raises(ValueError, match="Only SportyBet and Bet9ja"):
        PickRecordService(db).record(
            {
                "sport": "Football",
                "event": "Home vs Away",
                "starts_at": "2099-08-28T18:00:00+00:00",
                "market": "Home to win",
                "pick": "Home",
                "decimal_odds": "1.50",
                "bookmaker": "Stake",
            }
        )
