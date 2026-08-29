import pytest

from sabiai.odds import (
    ConsensusPricingEngine,
    assess_value,
    expected_value_pct,
    market_margin,
    no_vig_probabilities,
)


def test_no_vig_probabilities_remove_overround():
    prices = {"over": 1.91, "under": 1.91}
    fair = no_vig_probabilities(prices)
    assert fair["over"] == pytest.approx(0.5)
    assert fair["under"] == pytest.approx(0.5)
    assert market_margin(prices.values()) * 100 == pytest.approx(4.712, abs=0.01)


def test_consensus_pricing_requires_complete_equivalent_markets():
    offers = [
        {"family": "total", "metric": "goals", "line": 2.5, "side": "over", "selection_label": "Over 2.5", "decimal_odds": 1.91, "bookmaker": "Book A"},
        {"family": "total", "metric": "goals", "line": 2.5, "side": "under", "selection_label": "Under 2.5", "decimal_odds": 1.91, "bookmaker": "Book A"},
        {"family": "total", "metric": "goals", "line": 2.5, "side": "over", "selection_label": "Over 2.5", "decimal_odds": 2.00, "bookmaker": "Book B"},
        {"family": "total", "metric": "goals", "line": 2.5, "side": "under", "selection_label": "Under 2.5", "decimal_odds": 1.82, "bookmaker": "Book B"},
        # Different line must never be mixed into the same fair market.
        {"family": "total", "metric": "goals", "line": 3.5, "side": "over", "selection_label": "Over 3.5", "decimal_odds": 2.50, "bookmaker": "Book C"},
    ]
    rows = ConsensusPricingEngine().fair_prices(offers)
    two_five = [row for row in rows if row.market_identity[-1] == "2.5"]
    three_five = [row for row in rows if row.market_identity[-1] == "3.5"]
    assert {row.selection for row in two_five} == {"over", "under"}
    assert all(row.contributing_books == 2 for row in two_five)
    assert three_five == []


def test_value_assessment_reports_ev_and_consensus_gap():
    result = assess_value(60.0, 1.90, consensus_probability_pct=55.0)
    assert result.expected_value_pct == pytest.approx(expected_value_pct(0.60, 1.90))
    assert result.raw_implied_probability_pct == pytest.approx(52.6315, abs=0.01)
    assert result.probability_vs_consensus_pct == pytest.approx(5.0)
    assert result.consensus_fair_odds == pytest.approx(1 / 0.55)
