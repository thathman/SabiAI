from sabiai.research.model_contract import prepare_events_for_model, validate_engine_recommendations


def _event():
    return {
        "sport": "football",
        "event": "Arsenal vs Chelsea",
        "event_id": "evt-1",
        "source": "SportyBet",
        "action_book": "SportyBet",
        "competition": "Premier League",
        "odds": [
            {"label": "Arsenal", "market": "winner", "decimal_odds": 1.91, "bookmaker": "SportyBet", "observed_at": "2026-08-29T10:00:00+00:00"},
            {"label": "Chelsea", "market": "winner", "decimal_odds": 1.91, "bookmaker": "SportyBet", "observed_at": "2026-08-29T10:00:00+00:00"},
        ],
    }


def test_prepared_offers_have_stable_refs_and_no_vig_baseline():
    prepared = prepare_events_for_model([_event()])[0]
    assert len(prepared["odds"]) == 2
    assert prepared["odds"][0]["offer_ref"].startswith("offer:")
    assert prepared["odds"][0]["action_book_fair_probability_pct"] == 50.0
    assert prepared["engine_profile"]["needs_discovery"] is False


def test_validator_binds_model_output_to_exact_offer_not_just_numeric_price():
    prepared = prepare_events_for_model([_event()])[0]
    arsenal = next(row for row in prepared["odds"] if row["label"] == "Arsenal")
    result = {
        "recommendations": [{
            "sport": "football",
            "event": "Arsenal vs Chelsea",
            "offer_ref": arsenal["offer_ref"],
            "bookmaker": "SportyBet",
            "market": "winner",
            "pick": "Arsenal",
            "decimal_odds": 1.91,
            "confidence_pct": 60,
            "estimated_probability_pct": 58,
            "reason": "supplied evidence supports the home side",
        }]
    }
    rows = validate_engine_recommendations(result, [_event()])
    assert len(rows) == 1
    assert rows[0]["pick"] == "Arsenal"
    assert rows[0]["bookmaker"] == "SportyBet"
    assert rows[0]["expected_value_pct"] > 0

    # The same price on another outcome cannot be used with Arsenal's offer reference.
    result["recommendations"][0]["pick"] = "Chelsea"
    assert validate_engine_recommendations(result, [_event()]) == []


def test_validator_rejects_missing_or_wrong_offer_reference():
    base = {
        "sport": "football",
        "event": "Arsenal vs Chelsea",
        "bookmaker": "SportyBet",
        "market": "winner",
        "pick": "Arsenal",
        "decimal_odds": 1.91,
        "confidence_pct": 60,
        "estimated_probability_pct": 58,
    }
    assert validate_engine_recommendations({"recommendations": [base]}, [_event()]) == []
    assert validate_engine_recommendations({"recommendations": [{**base, "offer_ref": "offer:not-real"}]}, [_event()]) == []
