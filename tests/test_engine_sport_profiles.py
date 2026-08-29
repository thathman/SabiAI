from sabiai.sports import complete_sports, engine_sport_profiles, sport_engine_profile


def test_every_proactive_engine_sport_has_a_complete_profile():
    profiles = engine_sport_profiles()
    assert len(profiles) == 31
    assert len({profile.slug for profile in profiles}) == 31
    for profile in profiles:
        assert profile.minimum_market_families
        assert profile.evidence_topics
        assert profile.settlement_concerns
        assert profile.discovery_horizon_hours >= 72
        assert profile.needs_discovery is False


def test_extended_registry_knows_v24_discovery_sports():
    registry = complete_sports()
    for value in (
        "american football",
        "horse racing",
        "greyhound racing",
        "rugby league",
        "athletics",
        "winter sports",
    ):
        assert registry.resolve(value).needs_discovery is False


def test_unknown_sport_stays_discoverable_instead_of_fake_complete():
    profile = sport_engine_profile("underwater basket weaving")
    assert profile.needs_discovery is True
    assert profile.minimum_market_families == ("winner",)
    assert "bookmaker-specific rules must be verified" in profile.settlement_concerns


def test_special_sports_have_non_team_market_contracts():
    assert sport_engine_profile("golf").minimum_market_families == ("outright", "placement", "matchup")
    assert sport_engine_profile("mma").minimum_market_families == ("winner", "method", "total_rounds")
    assert sport_engine_profile("horse_racing").event_shape == "race"
    assert sport_engine_profile("boxing").discovery_horizon_hours == 336
