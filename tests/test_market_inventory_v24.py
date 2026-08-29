from __future__ import annotations

from sabiai.research import (
    MarketInventoryNormalizer,
    classify_market,
    expected_market_families,
    market_family_gap,
)


def test_minimum_market_families_are_sport_aware():
    assert expected_market_families("football") == ("winner", "handicap", "total")
    assert expected_market_families("basketball") == ("winner", "handicap", "total")
    assert expected_market_families("golf") == ("outright", "placement", "matchup")
    assert expected_market_families("mma") == ("winner", "method", "total_rounds")
    assert market_family_gap("football", ["winner", "total"]) == ["handicap"]


def test_market_classifier_handles_core_and_niche_markets():
    assert classify_market("h2h", sport="football")["family"] == "winner"
    assert classify_market("spreads", sport="basketball")["family"] == "handicap"
    assert classify_market("totals", sport="basketball")["family"] == "total"
    assert classify_market("btts", sport="football")["family"] == "btts"
    assert classify_market("team_totals", sport="football")["family"] == "team_total"
    assert classify_market("player_points", sport="basketball")["family"] == "player_prop"
    assert classify_market("method_of_victory", sport="mma")["family"] == "method"
    assert classify_market("top_10", sport="golf")["family"] == "placement"
    assert classify_market("h2h", sport="golf")["family"] == "outright"


def test_the_odds_normalizer_preserves_market_line_bookmaker_and_price():
    event = {
        "id": "evt-1",
        "sport_key": "soccer_epl",
        "bookmakers": [
            {
                "key": "book-a",
                "title": "Book A",
                "last_update": "2026-08-28T12:00:00Z",
                "markets": [
                    {
                        "key": "totals",
                        "outcomes": [
                            {"name": "Over", "price": 1.91, "point": 2.5},
                            {"name": "Under", "price": 1.95, "point": 2.5},
                        ],
                    },
                    {
                        "key": "spreads",
                        "outcomes": [
                            {"name": "Arsenal", "price": 1.88, "point": -0.5},
                            {"name": "Chelsea", "price": 2.02, "point": 0.5},
                        ],
                    },
                ],
            }
        ],
    }
    catalogue, offers = MarketInventoryNormalizer("The Odds API · Markets").the_odds_api(
        event, event_id="canonical-1"
    )
    assert {row["family"] for row in catalogue} == {"total", "handicap"}
    over = next(row for row in offers if row["selection_label"] == "Over")
    assert over["bookmaker"] == "Book A"
    assert over["family"] == "total"
    assert over["line"] == 2.5
    assert over["side"] == "over"
    assert over["decimal_odds"] == 1.91


def test_embedded_fixture_odds_do_not_lose_explicit_market_identity():
    event = {
        "sport": "tennis",
        "home": "Player A",
        "away": "Player B",
        "odds": [
            {
                "label": "Over 22.5",
                "decimal_odds": 1.87,
                "market": "total games",
                "line": 22.5,
                "bookmaker": "SportyBet",
            }
        ],
    }
    catalogue, offers = MarketInventoryNormalizer("SportyBet").embedded(event, event_id="evt")
    assert catalogue[0]["family"] == "total"
    assert offers[0]["line"] == 22.5
    assert offers[0]["bookmaker"] == "SportyBet"
