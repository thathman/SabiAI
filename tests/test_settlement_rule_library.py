from sabiai.domain.types import MarketKind
from sabiai.odds import SettlementRuleLibrary, SettlementRules


def test_tennis_profile_requires_retirement_rule_verification():
    profile = SettlementRuleLibrary().profile("Tennis", MarketKind.WINNER)
    assert profile.verification_required is True
    assert profile.rules.retirement_rule == "bookmaker_specific"
    assert "retirement" in profile.verification_topics


def test_golf_profile_keeps_dead_heat_in_fingerprint():
    profile = SettlementRuleLibrary().profile("Golf", MarketKind.WINNER)
    assert profile.rules.dead_heat_rule == "bookmaker_specific"
    assert "dead heat" in profile.verification_topics


def test_deeper_settlement_fields_prevent_false_equivalence():
    first = SettlementRules(
        period="full_event",
        includes_overtime=None,
        retirement_rule="one_set_completed",
    )
    second = SettlementRules(
        period="full_event",
        includes_overtime=None,
        retirement_rule="one_point_played",
    )
    assert first.key != second.key


def test_unknown_sport_fails_conservatively_to_bookmaker_specific_rules():
    profile = SettlementRuleLibrary().profile("Kabaddi Variant X", "winner")
    assert profile.verification_required is True
    assert profile.rules.void_rule == "bookmaker_specific"
    assert profile.rules.format_rule == "bookmaker_specific"
