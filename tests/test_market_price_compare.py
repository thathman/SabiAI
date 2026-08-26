from datetime import datetime, timedelta, timezone
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


def _quote(bookmaker, odds, captured_at, *, overtime=False):
    return {
        "event_key": "arsenal-chelsea",
        "market_key": "over-2.5-goals",
        "selection_key": "over-2.5",
        "selection_label": "Over 2.5 goals",
        "bookmaker": bookmaker,
        "odds": odds,
        "captured_at": captured_at,
        "rules": {
            "period": "full_event",
            "includes_overtime": overtime,
            "void_rule": "standard",
            "line_key": "2.5",
        },
    }


def test_market_compare_returns_best_decimal_price(tmp_path: Path):
    gateway = _gateway(tmp_path)
    now = datetime.now(timezone.utc).isoformat()
    result = gateway.dispatch(
        "market.compare",
        {
            "quotes": [
                _quote("SportyBet", "1.82", now),
                _quote("Bet9ja", "1.86", now),
            ],
            "max_age_seconds": 180,
        },
    )

    assert result["ok"] is True
    row = result["data"]["selections"][0]
    assert row["selection"] == "Over 2.5 goals"
    assert row["best_bookmaker"] == "Bet9ja"
    assert row["best_odds"] == "1.86"
    assert [price["bookmaker"] for price in row["prices"]] == ["Bet9ja", "SportyBet"]


def test_market_compare_rejects_stale_and_incompatible_rules(tmp_path: Path):
    gateway = _gateway(tmp_path)
    now = datetime.now(timezone.utc)
    fresh = now.isoformat()
    stale = (now - timedelta(minutes=10)).isoformat()
    result = gateway.dispatch(
        "market.compare",
        {
            "quotes": [
                _quote("SportyBet", "1.82", fresh),
                _quote("Bet9ja", "1.90", stale),
                _quote("Bet9ja", "1.95", fresh, overtime=True),
            ],
            "max_age_seconds": 180,
        },
    )

    assert result["ok"] is True
    assert result["data"]["rejected_stale"] == 1
    assert result["data"]["rejected_rule_mismatch"] == 1
    assert result["data"]["selections"][0]["best_bookmaker"] == "SportyBet"


def test_bookmaker_compare_plan_covers_multiple_books_without_claiming_unverified_one(tmp_path: Path):
    gateway = _gateway(tmp_path)
    result = gateway.dispatch(
        "bookmaker.compare.plan",
        {
            "bookmakers": ["SportyBet", "Bet9ja", "Stake", "1xBet"],
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
    )

    assert result["ok"] is True
    plans = {row["slug"]: row for row in result["data"]["plans"]}
    assert plans["sportybet"]["browser_ready"] is True
    assert plans["bet9ja"]["browser_ready"] is True
    assert result["data"]["unknown_bookmakers"] == ["Stake", "1xBet"]


def test_market_compare_rejects_removed_bookmakers(tmp_path: Path):
    gateway = _gateway(tmp_path)
    result = gateway.dispatch(
        "market.compare",
        {"quotes": [_quote("Stake", "1.82", datetime.now(timezone.utc).isoformat())]},
    )
    assert result["ok"] is False
    assert "Unknown bookmaker: Stake" in result["error"]
