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


def _recommendation(event):
    prepared = prepare_events_for_model([event])[0]
    arsenal = next(row for row in prepared["odds"] if row["label"] == "Arsenal")
    return {
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
    }


def test_prepared_offers_have_stable_refs_and_no_vig_baseline():
    prepared = prepare_events_for_model([_event()])[0]
    assert len(prepared["odds"]) == 2
    assert prepared["odds"][0]["offer_ref"].startswith("offer:")
    assert prepared["odds"][0]["action_book_fair_probability_pct"] == 50.0
    assert prepared["engine_profile"]["needs_discovery"] is False


def test_validator_binds_model_output_to_exact_offer_not_just_numeric_price():
    event = _event()
    result = {"recommendations": [_recommendation(event)]}
    rows = validate_engine_recommendations(result, [event])
    assert len(rows) == 1
    assert rows[0]["pick"] == "Arsenal"
    assert rows[0]["bookmaker"] == "SportyBet"
    assert rows[0]["expected_value_pct"] > 0

    result["recommendations"][0]["pick"] = "Chelsea"
    assert validate_engine_recommendations(result, [event]) == []


def test_validator_rejects_missing_or_wrong_offer_reference():
    event = _event()
    base = _recommendation(event)
    base.pop("offer_ref")
    assert validate_engine_recommendations({"recommendations": [base]}, [event]) == []
    assert validate_engine_recommendations({"recommendations": [{**base, "offer_ref": "offer:not-real"}]}, [event]) == []


def test_explicit_evidence_gap_blocks_an_otherwise_valid_offer():
    event = _event()
    event["evidence_packet"] = {
        "quality": "weak",
        "ready_for_decision": False,
        "sources": ["TheSportsDB"],
        "missing_topics": ["current lineup/roster availability"],
    }
    result = {"recommendations": [_recommendation(event)]}
    assert validate_engine_recommendations(result, [event]) == []


def test_evidence_metadata_is_preserved_on_validated_recommendation():
    event = _event()
    event["evidence_packet"] = {
        "quality": "strong",
        "ready_for_decision": True,
        "sources": ["TheSportsDB", "ESPN Public Data"],
        "missing_topics": [],
    }
    rows = validate_engine_recommendations({"recommendations": [_recommendation(event)]}, [event])
    assert rows[0]["evidence_quality"] == "strong"
    assert rows[0]["evidence_ready_for_decision"] is True
    assert rows[0]["evidence_sources"] == ["TheSportsDB", "ESPN Public Data"]
