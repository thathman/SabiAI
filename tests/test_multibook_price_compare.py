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


def _now():
    return datetime.now(timezone.utc).isoformat()


def _ticket_leg():
    return {
        "sport": "Football",
        "event": "Arsenal vs Chelsea",
        "market": "Over 2.5 goals",
        "odds": "1.70",
    }


def test_multibook_compare_uses_best_exact_market_not_highest_wrong_line(tmp_path: Path):
    gateway = _gateway(tmp_path)
    result = gateway.dispatch(
        "bookmaker.compare.from_search",
        {
            "bookmaker": "Bet9ja",
            "legs": [_ticket_leg()],
            "results": [
                {
                    "bookmaker": "SportyBet",
                    "offers": [
                        {
                            "event": "Arsenal vs Chelsea",
                            "home": "Arsenal",
                            "away": "Chelsea",
                            "sport": "Football",
                            "market": "Over 2.5 goals",
                            "decimal_odds": "1.82",
                            "observed_at": _now(),
                        }
                    ],
                },
                {
                    "bookmaker": "Stake",
                    "offers": [
                        {
                            "event": "Arsenal vs Chelsea",
                            "home": "Arsenal",
                            "away": "Chelsea",
                            "sport": "Football",
                            "market": "Over 3.5 goals",
                            "decimal_odds": "2.50",
                            "observed_at": _now(),
                        },
                        {
                            "event": "Arsenal vs Chelsea",
                            "home": "Arsenal",
                            "away": "Chelsea",
                            "sport": "Football",
                            "market": "Over 2.5 goals",
                            "decimal_odds": "1.90",
                            "observed_at": _now(),
                        },
                    ],
                },
            ],
        },
    )

    assert result["ok"] is True
    data = result["data"]
    assert data["complete"] is True
    assert data["priced_legs"] == 1
    leg = data["legs"][0]
    assert leg["best"] == {
        "bookmaker": "stake",
        "odds": "1.90",
        "event": "Arsenal vs Chelsea",
        "selection": "Over 2.5 goals",
    }
    assert [row["odds"] for row in leg["prices"]] == ["1.90", "1.82"]
    assert all(row["selection"] == "Over 2.5 goals" for row in leg["prices"])


def test_multibook_compare_does_not_treat_source_ticket_odds_as_current(tmp_path: Path):
    gateway = _gateway(tmp_path)
    result = gateway.dispatch(
        "bookmaker.compare.from_search",
        {
            "bookmaker": "Bet9ja",
            "legs": [_ticket_leg()],
            "results": [
                {
                    "bookmaker": "SportyBet",
                    "offers": [
                        {
                            "event": "Arsenal vs Chelsea",
                            "home": "Arsenal",
                            "away": "Chelsea",
                            "sport": "Football",
                            "market": "Over 2.5 goals",
                            "decimal_odds": "1.60",
                            "observed_at": _now(),
                        }
                    ],
                }
            ],
        },
    )

    assert result["ok"] is True
    leg = result["data"]["legs"][0]
    assert leg["source_ticket_odds"] == "1.70"
    assert leg["best"]["bookmaker"] == "sportybet"
    assert leg["best"]["odds"] == "1.60"
    assert "not assumed current" in result["data"]["note"]
