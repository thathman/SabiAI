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


def test_ticket_research_plan_is_market_specific_and_explicit(tmp_path: Path):
    gateway = _gateway(tmp_path)
    result = gateway.dispatch(
        "ticket.research.plan",
        {
            "legs": [
                {
                    "sport": "Football",
                    "event": "Arsenal vs Chelsea",
                    "home": "Arsenal",
                    "away": "Chelsea",
                    "market": "Over 8.5 corners",
                    "odds": "1.75",
                },
                {
                    "sport": "Volleyball",
                    "event": "VakifBank vs Fenerbahce",
                    "home": "VakifBank",
                    "away": "Fenerbahce",
                    "market": "VakifBank +1.5 sets handicap",
                    "odds": "1.50",
                },
            ]
        },
    )

    assert result["ok"] is True
    data = result["data"]
    assert data["leg_count"] == 2
    assert data["legs"][0]["home"] == "Arsenal"
    assert data["legs"][0]["away"] == "Chelsea"
    assert data["legs"][0]["selection"] == "Over 8.5 corners"
    assert data["legs"][0]["market_focus"]
    assert data["legs"][1]["sport"] == "Volleyball"
    assert data["legs"][1]["market_focus"]


def test_large_ticket_automatically_requests_skeptic_review(tmp_path: Path):
    gateway = _gateway(tmp_path)
    legs = [
        {
            "sport": "Football",
            "event": f"Home {index} vs Away {index}",
            "home": f"Home {index}",
            "away": f"Away {index}",
            "market": f"Home {index} or Draw",
            "odds": "1.25",
        }
        for index in range(1, 7)
    ]
    result = gateway.dispatch("ticket.research.plan", {"legs": legs})

    assert result["ok"] is True
    assert result["data"]["skeptic_required"] is True
    assert any("Large ticket" in reason for reason in result["data"]["reasons"])
