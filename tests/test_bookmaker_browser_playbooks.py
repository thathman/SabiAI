from sabiai.bookmakers import BookmakerBrowserProfiles, BookmakerExecutionPlanner


def test_verified_browser_profiles_exist_for_sportybet_bet9ja_and_stake():
    profiles = BookmakerBrowserProfiles()
    for slug in ("sportybet", "bet9ja", "stake"):
        profile = profiles.get(slug)
        assert profile is not None
        assert profile.public_restore is True
        assert profile.entry_url
        assert profile.verified_on == "2026-08-25"
        assert "decimal_odds" in profile.extraction_fields


def test_1xbet_remains_discovery_only_until_current_flow_is_verified():
    profile = BookmakerBrowserProfiles().get("1xbet")
    assert profile is not None
    assert profile.public_restore is False
    assert profile.entry_url is None

    plan = BookmakerExecutionPlanner().import_booking_code(
        bookmaker="1xBet",
        booking_code="ABC123",
    )
    assert plan.ready is False
    assert plan.method == "discover_current_flow"


def test_sportybet_import_plan_includes_current_public_restore_route():
    plan = BookmakerExecutionPlanner().import_booking_code(
        bookmaker="SportyBet",
        booking_code="ABC123",
    )
    assert plan.ready is True
    assert plan.method == "openclaw_browser"
    assert plan.entry_url == "https://www.sportybet.com/ng/lite/betslip"
    assert plan.code_prompt == "Please insert booking code"
    assert plan.next_tool == "bookmaker.booking_code.restore"


def test_bet9ja_import_plan_uses_guest_book_a_bet_page():
    plan = BookmakerExecutionPlanner().import_booking_code(
        bookmaker="Bet9ja",
        booking_code="ZXCV12",
    )
    assert plan.ready is True
    assert "Tutorial_book/Guest" in (plan.entry_url or "")
    assert plan.load_action == "LOAD"


def test_stake_import_plan_is_explicit_about_region_account_variation():
    plan = BookmakerExecutionPlanner().import_booking_code(
        bookmaker="Stake",
        booking_code="STAKE77",
    )
    assert plan.ready is True
    assert plan.method == "openclaw_browser"
    assert "region/account" in (plan.verification_note or "")
