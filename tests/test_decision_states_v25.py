from sabiai.research.decision import CrossSportDecisionPass


def _row(event, *, confidence, estimated, odds, sport="football"):
    return {
        "sport": sport,
        "country": "Test",
        "competition": "Test League",
        "division": "1",
        "event": event,
        "market": "winner",
        "pick": f"{event} pick",
        "bookmaker": "SportyBet",
        "decimal_odds": odds,
        "confidence_pct": confidence,
        "estimated_probability_pct": estimated,
    }


def test_decision_states_separate_quality_from_price():
    engine = CrossSportDecisionPass(minimum_confidence=55, minimum_edge=1, minimum_expected_value_pct=1)
    result = engine.select([
        _row("positive", confidence=65, estimated=60, odds=1.90),
        _row("price-too-short", confidence=65, estimated=60, odds=1.65),
        _row("watch", confidence=52, estimated=53, odds=1.90),
        _row("pass", confidence=45, estimated=45, odds=1.70),
    ])
    states = {row["event"]: row["decision_state"] for row in result["all_recommendations"]}
    assert states["positive"] == "BET"
    assert states["price-too-short"] == "BET IF PRICE"
    assert states["watch"] == "WATCH"
    assert states["pass"] == "PASS"
    assert [row["event"] for row in result["recommendations"]] == ["positive"]


def test_rank_prefers_expected_value_before_raw_odds():
    engine = CrossSportDecisionPass(max_recommendations=2, max_per_sport=2, max_per_scope=2)
    result = engine.select([
        _row("higher-ev", confidence=65, estimated=60, odds=2.00),
        _row("lower-ev", confidence=70, estimated=58, odds=1.90),
    ])
    assert result["recommendations"][0]["event"] == "higher-ev"
