from sabiai.bookmakers import default_bookmakers
from sabiai.markets import MarketInterpreter
from sabiai.tickets import RestoredSlipService, TicketNormalizer


def service():
    return RestoredSlipService(TicketNormalizer(default_bookmakers(), MarketInterpreter()))


def test_restored_slip_preserves_code_and_checks_combined_odds():
    result = service().normalize(
        bookmaker="SportyBet",
        booking_code="ABC123",
        payload={
            "leg_count": 2,
            "combined_odds": "2.40",
            "legs": [
                {
                    "sport": "Football",
                    "event": "Arsenal vs Chelsea",
                    "market": "1X2",
                    "selection": "Arsenal to win",
                    "decimal_odds": "1.50",
                },
                {
                    "sport": "Football",
                    "event": "Inter vs Torino",
                    "market": "1X2",
                    "selection": "Inter to win",
                    "decimal_odds": "1.60",
                },
            ],
        },
    )
    assert result.usable is True
    assert result.booking_code == "ABC123"
    assert str(result.computed_combined_odds) == "2.40"
    assert result.combined_odds_match is True
    assert result.ticket.source_type == "booking_code"
    assert result.ticket.legs[0].selection.label == "Arsenal to win"
    assert str(result.ticket.legs[0].odds) == "1.50"
    assert result.ticket.legs[1].selection.label == "Inter to win"


def test_restored_slip_blocks_incomplete_leg_extraction():
    result = service().normalize(
        bookmaker="Bet9ja",
        booking_code="CODE77",
        payload={
            "leg_count": 3,
            "legs": [
                {
                    "sport": "Football",
                    "event": "Arsenal vs Chelsea",
                    "market": "1X2",
                    "selection": "Arsenal to win",
                    "decimal_odds": "1.50",
                },
                {
                    "sport": "Football",
                    "event": "Inter vs Torino",
                    "market": "1X2",
                    "selection": "Inter to win",
                    "decimal_odds": "1.60",
                },
            ],
        },
    )
    assert result.usable is False
    assert any("only 2 were extracted" in issue.message for issue in result.issues)


def test_restored_slip_warns_when_displayed_total_does_not_match_legs():
    result = service().normalize(
        bookmaker="Bet9ja",
        booking_code="BET9JA1",
        payload={
            "combined_odds": "4.00",
            "legs": [
                {
                    "sport": "Basketball",
                    "event": "Team A vs Team B",
                    "market": "Winner",
                    "selection": "Team A to win",
                    "decimal_odds": "1.50",
                },
                {
                    "sport": "Basketball",
                    "event": "Team C vs Team D",
                    "market": "Winner",
                    "selection": "Team C to win",
                    "decimal_odds": "1.60",
                },
            ],
        },
    )
    assert result.combined_odds_match is False
    assert any(issue.level == "warning" and "displayed combined odds" in issue.message for issue in result.issues)
