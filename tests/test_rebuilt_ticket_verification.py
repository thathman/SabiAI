from datetime import datetime, timezone
from pathlib import Path

from sabiai.config import Settings
from sabiai.openclaw.gateway import SabiToolGateway


def _gateway(tmp_path: Path) -> SabiToolGateway:
    return SabiToolGateway(
        Settings(
            repo_root=tmp_path,
            data_dir=tmp_path / "data",
            legacy_bets_db=tmp_path / "data" / "bets.db",
            v2_db=tmp_path / "data" / "v2.db",
            timezone="Africa/Lagos",
            paid_sources_enabled=False,
        )
    )


def _converted_draft(gateway: SabiToolGateway) -> dict:
    source_leg = {
        "sport": "Football",
        "event": "Arsenal vs Chelsea",
        "home": "Arsenal",
        "away": "Chelsea",
        "market": "Over 2.5 goals",
        "odds": "1.70",
    }
    source = gateway.dispatch(
        "ticket.draft.save",
        {
            "bookmaker": "Bet9ja",
            "source_type": "booking_code",
            "source_reference": "Bet9ja:SOURCE1",
            "legs": [source_leg],
        },
    )
    assert source["ok"] is True
    converted = gateway.dispatch(
        "bookmaker.convert.from_search",
        {
            "source_draft_id": source["data"]["id"],
            "bookmaker": "Bet9ja",
            "target_bookmaker": "SportyBet",
            "legs": [source_leg],
            "offers": [
                {
                    "event": "Arsenal vs Chelsea",
                    "home": "Arsenal",
                    "away": "Chelsea",
                    "sport": "Football",
                    "market": "Over 2.5 goals",
                    "decimal_odds": "1.82",
                    "bookmaker": "SportyBet",
                    "event_ref": "evt-1",
                    "market_ref": "mkt-25",
                    "observed_at": datetime.now(timezone.utc).isoformat(),
                }
            ],
        },
    )
    assert converted["ok"] is True
    assert converted["data"]["ready"] is True
    return converted["data"]["draft"]


def test_rebuilt_code_verifies_structure_and_surfaces_price_change(tmp_path: Path):
    gateway = _gateway(tmp_path)
    expected = _converted_draft(gateway)

    result = gateway.dispatch(
        "bookmaker.build.verify",
        {
            "expected_draft_id": expected["id"],
            "bookmaker": "SportyBet",
            "booking_code": "NEW123",
            "payload": {
                "leg_count": 1,
                "combined_odds": "1.80",
                "legs": [
                    {
                        "sport": "Football",
                        "event": "Arsenal vs Chelsea",
                        "home": "Arsenal",
                        "away": "Chelsea",
                        "market": "Over 2.5 goals",
                        "odds": "1.80",
                    }
                ],
            },
        },
    )

    assert result["ok"] is True
    data = result["data"]
    assert data["verified"] is True
    assert data["ready_to_return_code"] is True
    assert data["prices_changed"] is True
    assert data["verification"]["legs"][0]["restored_odds"] == "1.80"
    assert data["draft"] is not None
    assert data["draft"]["parent_draft_id"] == expected["id"]
    assert data["draft"]["status"] == "verified_built"
    assert data["draft"]["payload"]["booking_code"] == "NEW123"


def test_rebuilt_code_with_wrong_market_is_not_verified(tmp_path: Path):
    gateway = _gateway(tmp_path)
    expected = _converted_draft(gateway)

    result = gateway.dispatch(
        "bookmaker.build.verify",
        {
            "expected_draft_id": expected["id"],
            "bookmaker": "SportyBet",
            "booking_code": "WRONG123",
            "payload": {
                "leg_count": 1,
                "combined_odds": "2.30",
                "legs": [
                    {
                        "sport": "Football",
                        "event": "Arsenal vs Chelsea",
                        "home": "Arsenal",
                        "away": "Chelsea",
                        "market": "Over 3.5 goals",
                        "odds": "2.30",
                    }
                ],
            },
        },
    )

    assert result["ok"] is True
    data = result["data"]
    assert data["verified"] is False
    assert data["ready_to_return_code"] is False
    assert data["verification"]["legs"][0]["status"] == "missing"
    assert data["draft"] is None
