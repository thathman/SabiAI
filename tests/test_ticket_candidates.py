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


def _base_legs():
    return [
        {
            "sport": "Football",
            "event": "Arsenal vs Chelsea",
            "market": "Arsenal to win",
            "odds": "1.70",
        },
        {
            "sport": "Football",
            "event": "Liverpool vs Everton",
            "market": "Over 2.5 goals",
            "odds": "1.75",
        },
    ]


def test_common_ticket_tools_can_load_persistent_draft_directly(tmp_path: Path):
    gateway = _gateway(tmp_path)
    saved = gateway.dispatch(
        "ticket.draft.save",
        {"legs": _base_legs(), "bookmaker": "SportyBet", "source_type": "instruction"},
    )
    assert saved["ok"] is True
    draft_id = saved["data"]["id"]

    split = gateway.dispatch("ticket.split", {"draft_id": draft_id, "slips": 2})
    assert split["ok"] is True
    assert len(split["data"]["slips"]) == 2


def test_higher_odds_variant_requires_fresh_verified_prices(tmp_path: Path):
    gateway = _gateway(tmp_path)
    normalized = gateway.dispatch("ticket.normalize", {"legs": _base_legs(), "bookmaker": "SportyBet"})
    assert normalized["ok"] is True
    legs = normalized["data"]["ticket"]["legs"]
    first_id = legs[0]["id"]
    now = datetime.now(timezone.utc).isoformat()

    result = gateway.dispatch(
        "ticket.higher_odds.from_verified_offers",
        {
            "legs": legs,
            "bookmaker": "SportyBet",
            "target_bookmaker": "SportyBet",
            "save_draft": False,
            "replacements": [
                {
                    "leg_id": first_id,
                    "bookmaker": "SportyBet",
                    "sport": "Football",
                    "event": "Arsenal vs Chelsea",
                    "home": "Arsenal",
                    "away": "Chelsea",
                    "market": "Arsenal -1 handicap",
                    "odds": "2.25",
                    "observed_at": now,
                }
            ],
        },
    )
    assert result["ok"] is True
    assert result["data"]["ready"] is True
    assert result["data"]["changes"][0]["after"] == "Arsenal -1 handicap"
    assert float(result["data"]["new_combined_odds"]) > float(result["data"]["original_combined_odds"])


def test_higher_odds_variant_rejects_stale_price(tmp_path: Path):
    gateway = _gateway(tmp_path)
    normalized = gateway.dispatch("ticket.normalize", {"legs": _base_legs(), "bookmaker": "SportyBet"})
    legs = normalized["data"]["ticket"]["legs"]
    result = gateway.dispatch(
        "ticket.higher_odds.from_verified_offers",
        {
            "legs": legs,
            "bookmaker": "SportyBet",
            "target_bookmaker": "SportyBet",
            "save_draft": False,
            "max_age_seconds": 180,
            "replacements": [
                {
                    "leg_id": legs[0]["id"],
                    "bookmaker": "SportyBet",
                    "event": "Arsenal vs Chelsea",
                    "market": "Arsenal -1 handicap",
                    "odds": "2.25",
                    "observed_at": "2026-01-01T00:00:00+00:00",
                }
            ],
        },
    )
    assert result["ok"] is True
    assert result["data"]["ready"] is False


def test_candidate_comparison_is_descriptive_not_recommendation(tmp_path: Path):
    gateway = _gateway(tmp_path)
    result = gateway.dispatch(
        "ticket.candidates.compare",
        {
            "base": {"legs": _base_legs()},
            "candidates": [
                {"label": "Shorter", "legs": [_base_legs()[0]]},
                {"label": "Original shape", "legs": _base_legs()},
            ],
        },
    )
    assert result["ok"] is True
    assert len(result["data"]["candidates"]) == 2
    assert "not by a claim" in result["data"]["note"]
