from pathlib import Path

from sabiai.bookmakers import BookmakerBrowserProfiles
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


def test_rich_build_profiles_are_explicit_about_verified_code_creation():
    profiles = BookmakerBrowserProfiles()
    assert profiles.browser_build("sportybet").ready is True
    assert profiles.browser_build("bet9ja").ready is True
    assert profiles.browser_build("stake").ready is False
    assert profiles.browser_build("1xbet").ready is False
    assert profiles.browser_build("sportybet").verification_tool == "bookmaker.build.verify"


def test_sportybet_browser_build_plan_accepts_total_market(tmp_path: Path):
    gateway = _gateway(tmp_path)
    result = gateway.dispatch(
        "bookmaker.browser_build.plan",
        {
            "target_bookmaker": "SportyBet",
            "legs": [
                {
                    "sport": "Football",
                    "event": "Arsenal vs Chelsea",
                    "market": "Over 2.5 goals",
                    "odds": "1.82",
                }
            ],
        },
    )

    assert result["ok"] is True
    data = result["data"]
    assert data["playbook"]["ready"] is True
    assert data["scope"] == "create_booking_code_only"
    assert data["verification_tool"] == "bookmaker.build.verify"
    assert data["tasks"][0]["selection"] == "Over 2.5 goals"


def test_bet9ja_browser_build_plan_can_prepare_handicap_without_legacy_1x2_constraint(tmp_path: Path):
    gateway = _gateway(tmp_path)
    result = gateway.dispatch(
        "bookmaker.browser_build.plan",
        {
            "target_bookmaker": "Bet9ja",
            "legs": [
                {
                    "sport": "Basketball",
                    "event": "Lagos Kings vs Abuja Lions",
                    "market": "Lagos Kings +4.5 handicap",
                    "odds": "1.88",
                }
            ],
        },
    )

    assert result["ok"] is True
    data = result["data"]
    assert data["playbook"]["ready"] is True
    assert data["tasks"][0]["selection"] == "Lagos Kings +4.5 handicap"
    assert any("booking" in step.casefold() for step in data["steps"])


def test_unverified_stake_code_creation_does_not_claim_ready(tmp_path: Path):
    gateway = _gateway(tmp_path)
    result = gateway.dispatch(
        "bookmaker.browser_build.plan",
        {
            "target_bookmaker": "Stake",
            "legs": [
                {
                    "sport": "Football",
                    "event": "Arsenal vs Chelsea",
                    "market": "Arsenal to win",
                    "odds": "1.72",
                }
            ],
        },
    )

    assert result["ok"] is True
    assert result["data"]["ready"] is False
    assert any("verified rich browser build profile" in reason for reason in result["data"]["reasons_not_ready"])


def test_browser_build_infers_target_from_converted_draft_and_blocks_mismatch(tmp_path: Path):
    gateway = _gateway(tmp_path)
    saved = gateway.dispatch(
        "ticket.draft.save",
        {
            "source_type": "conversion",
            "target_bookmaker": "SportyBet",
            "status": "converted",
            "legs": [
                {
                    "sport": "Football",
                    "event": "Arsenal vs Chelsea",
                    "market": "Over 2.5 goals",
                    "odds": "1.82",
                }
            ],
        },
    )
    assert saved["ok"] is True
    draft_id = saved["data"]["id"]

    inferred = gateway.dispatch(
        "bookmaker.browser_build.plan",
        {"draft_id": draft_id},
    )
    assert inferred["ok"] is True
    assert inferred["data"]["slug"] == "sportybet"
    assert inferred["data"]["expected_draft_id"] == draft_id

    mismatch = gateway.dispatch(
        "bookmaker.browser_build.plan",
        {"draft_id": draft_id, "target_bookmaker": "Bet9ja"},
    )
    assert mismatch["ok"] is False
    assert "refusing to build it on Bet9ja" in mismatch["error"]


def test_legacy_build_plan_and_execute_infer_target_from_converted_draft(tmp_path: Path):
    gateway = _gateway(tmp_path)
    saved = gateway.dispatch(
        "ticket.draft.save",
        {
            "source_type": "conversion",
            "target_bookmaker": "Bet9ja",
            "status": "converted",
            "legs": [
                {
                    "sport": "Football",
                    "event": "Vietnam vs Thailand",
                    "home": "Vietnam",
                    "away": "Thailand",
                    "market": "Vietnam to win",
                    "odds": "1.77",
                }
            ],
        },
    )
    draft_id = saved["data"]["id"]

    planned = gateway.dispatch("bookmaker.build.plan", {"draft_id": draft_id})
    executed = gateway.dispatch(
        "bookmaker.build.execute",
        {"draft_id": draft_id, "dry_run": True},
    )

    assert planned["ok"] is True
    assert planned["data"]["bookmaker_slug"] == "bet9ja"
    assert planned["data"]["ready"] is True
    assert executed["ok"] is True
    assert executed["data"]["plan"]["bookmaker_slug"] == "bet9ja"
    assert "Unknown bookmaker" not in executed["data"]["result"]["message"]
