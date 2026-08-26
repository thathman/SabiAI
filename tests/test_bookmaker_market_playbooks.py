from pathlib import Path

from sabiai.bookmakers import BookmakerBrowserProfiles
from sabiai.config import Settings
from sabiai.openclaw.gateway import SabiToolGateway


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        repo_root=tmp_path,
        data_dir=tmp_path / "data",
        legacy_bets_db=tmp_path / "data" / "bets.db",
        v2_db=tmp_path / "data" / "v2.db",
        timezone="Africa/Lagos",
        paid_sources_enabled=False,
    )


def test_verified_market_search_profiles_are_separate_from_code_restore_profiles():
    profiles = BookmakerBrowserProfiles()

    sporty = profiles.market_search("sportybet")
    bet9ja = profiles.market_search("bet9ja")
    assert sporty and sporty.ready and sporty.entry_url.endswith("/ng/lite")
    assert bet9ja and bet9ja.ready and bet9ja.entry_url == "https://sports.bet9ja.com/"
    assert profiles.market_search("stake") is None
    assert profiles.market_search("1xbet") is None


def test_openclaw_search_plan_includes_target_browser_playbook(tmp_path: Path):
    gateway = SabiToolGateway(_settings(tmp_path))
    result = gateway.dispatch(
        "bookmaker.search.plan",
        {
            "target_bookmaker": "SportyBet",
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
    assert result["data"]["ready"] is True
    assert result["data"]["browser_ready"] is True
    assert result["data"]["browser_playbook"]["odds_format"] == "decimal"
    assert result["data"]["browser_playbook"]["extraction_fields"]


def test_removed_1xbet_market_search_is_rejected(tmp_path: Path):
    gateway = SabiToolGateway(_settings(tmp_path))
    result = gateway.dispatch(
        "bookmaker.search.plan",
        {
            "target_bookmaker": "1xBet",
            "legs": [
                {
                    "sport": "Football",
                    "event": "Arsenal vs Chelsea",
                    "home": "Arsenal",
                    "away": "Chelsea",
                    "market": "Arsenal to win",
                    "odds": "1.70",
                }
            ],
        },
    )

    assert result["ok"] is False
    assert "Unknown target bookmaker" in result["error"]
