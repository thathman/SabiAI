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


def _source_leg():
    return {
        "sport": "Football",
        "event": "Arsenal vs Chelsea",
        "home": "Arsenal",
        "away": "Chelsea",
        "market": "Over 2.5 goals",
        "odds": "1.70",
    }


def test_market_search_ingest_rejects_wrong_book_and_invalid_odds(tmp_path: Path):
    gateway = _gateway(tmp_path)
    result = gateway.dispatch(
        "bookmaker.market_search.ingest",
        {
            "target_bookmaker": "SportyBet",
            "offers": [
                {
                    "event": "Arsenal vs Chelsea",
                    "market": "Over 2.5 goals",
                    "decimal_odds": "1.82",
                    "bookmaker": "SportyBet",
                    "sport": "Football",
                },
                {
                    "event": "Arsenal vs Chelsea",
                    "market": "Over 2.5 goals",
                    "decimal_odds": "0.82",
                    "bookmaker": "SportyBet",
                },
                {
                    "event": "Arsenal vs Chelsea",
                    "market": "Over 2.5 goals",
                    "decimal_odds": "1.90",
                    "bookmaker": "Bet9ja",
                },
            ],
        },
    )

    assert result["ok"] is True
    data = result["data"]
    assert len(data["offers"]) == 1
    assert data["offers"][0]["odds"] == "1.82"
    assert data["usable"] is False
    assert len([issue for issue in data["issues"] if issue["level"] == "error"]) == 2


def test_duplicate_browser_offer_is_ignored_with_warning(tmp_path: Path):
    gateway = _gateway(tmp_path)
    row = {
        "event": "Arsenal vs Chelsea",
        "market": "Over 2.5 goals",
        "decimal_odds": "1.82",
        "bookmaker": "SportyBet",
        "sport": "Football",
        "event_ref": "evt-1",
        "market_ref": "mkt-1",
        "observed_at": "2026-08-25T12:00:00Z",
    }
    result = gateway.dispatch(
        "bookmaker.market_search.ingest",
        {"target_bookmaker": "SportyBet", "offers": [row, dict(row)]},
    )

    assert result["ok"] is True
    assert len(result["data"]["offers"]) == 1
    assert any(issue["level"] == "warning" for issue in result["data"]["issues"])


def test_convert_from_search_accepts_exact_market_and_rejects_near_line(tmp_path: Path):
    gateway = _gateway(tmp_path)

    exact = gateway.dispatch(
        "bookmaker.convert.from_search",
        {
            "bookmaker": "Bet9ja",
            "target_bookmaker": "SportyBet",
            "legs": [_source_leg()],
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
                }
            ],
        },
    )
    assert exact["ok"] is True
    assert exact["data"]["ready"] is True
    assert exact["data"]["conversion"]["target_ticket"] is not None
    assert exact["data"]["conversion"]["legs"][0]["target_odds"] == "1.82"

    near = gateway.dispatch(
        "bookmaker.convert.from_search",
        {
            "bookmaker": "Bet9ja",
            "target_bookmaker": "SportyBet",
            "legs": [_source_leg()],
            "offers": [
                {
                    "event": "Arsenal vs Chelsea",
                    "home": "Arsenal",
                    "away": "Chelsea",
                    "sport": "Football",
                    "market": "Over 3.5 goals",
                    "decimal_odds": "2.30",
                    "bookmaker": "SportyBet",
                }
            ],
        },
    )
    assert near["ok"] is True
    assert near["data"]["ready"] is False
    assert near["data"]["conversion"]["legs"][0]["status"] == "missing_market"
