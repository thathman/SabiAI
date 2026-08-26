from sabiai.bookmakers import BookmakerBrowserProfiles, BookmakerExecutionPlanner


def test_verified_browser_profiles_exist_only_for_supported_bookmakers():
    profiles = BookmakerBrowserProfiles()
    for slug in ("sportybet", "bet9ja"):
        profile = profiles.get(slug)
        assert profile is not None
        assert profile.public_restore is True
        assert profile.entry_url
        assert profile.verified_on == "2026-08-25"
        assert "decimal_odds" in profile.extraction_fields

    assert profiles.get("stake") is None
    assert profiles.get("1xbet") is None


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


def test_removed_bookmakers_cannot_create_import_plans():
    for name in ("Stake", "1xBet"):
        plan = BookmakerExecutionPlanner().import_booking_code(
            bookmaker=name,
            booking_code="ABC123",
        )
        assert plan.ready is False
        assert plan.bookmaker_slug == "unknown"
        assert "Unknown bookmaker" in plan.reason
