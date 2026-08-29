from sabiai.odds import SettlementRuleLibrary
from sabiai.research import expected_market_families
from sabiai.sports import complete_sports, engine_sport_profiles


def test_market_minimums_come_from_engine_sport_contract():
    assert expected_market_families("football") == ("winner", "handicap", "total")
    assert expected_market_families("athletics") == ("outright", "placement", "matchup")
    assert expected_market_families("winter_sports") == ("outright", "placement", "matchup")
    assert expected_market_families("horse_racing") == ("outright", "placement")
    assert expected_market_families("mma") == ("winner", "method", "total_rounds")


def test_every_proactive_sport_has_a_nonempty_settlement_verification_contract():
    library = SettlementRuleLibrary()
    for profile in engine_sport_profiles():
        settlement = library.profile(profile.slug, "winner")
        assert settlement.verification_required is True
        assert settlement.verification_topics
        assert settlement.rules.format_rule
        assert settlement.rules.void_rule


def test_openclaw_knowledge_registry_contains_every_engine_sport():
    registry = complete_sports()
    resolved = {registry.resolve(profile.slug).name for profile in engine_sport_profiles()}
    assert len(resolved) == 31
