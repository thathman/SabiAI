from sabiai.domain.types import MarketKind
from sabiai.tickets import TicketNormalizer


def test_explicit_event_label_supplies_home_away_context_for_named_winner():
    result = TicketNormalizer().normalize(
        [
            {
                "sport": "Football",
                "event": "Arsenal vs Chelsea",
                "market": "Arsenal to win",
                "odds": "1.72",
            }
        ]
    )

    assert result.usable is True
    leg = result.ticket.legs[0]
    assert leg.market.kind is MarketKind.WINNER
    assert leg.selection.label == "Arsenal to win"
    assert leg.selection.side == "home"


def test_explicit_event_label_supplies_away_context_for_named_winner():
    result = TicketNormalizer().normalize(
        [
            {
                "sport": "Football",
                "event": "Arsenal vs Chelsea",
                "market": "Chelsea to win",
                "odds": "2.40",
            }
        ]
    )

    assert result.usable is True
    leg = result.ticket.legs[0]
    assert leg.market.kind is MarketKind.WINNER
    assert leg.selection.label == "Chelsea to win"
    assert leg.selection.side == "away"


def test_round_trip_style_payload_keeps_double_chance_identity_without_explicit_participants():
    result = TicketNormalizer().normalize(
        [
            {
                "sport": "Football",
                "event": "Arsenal vs Chelsea",
                "market": "Arsenal or Draw — Double Chance",
                "odds": "1.31",
            }
        ]
    )

    assert result.usable is True
    leg = result.ticket.legs[0]
    assert leg.market.kind is MarketKind.DOUBLE_CHANCE
    assert leg.selection.label == "Arsenal or Draw — Double Chance"
    assert leg.selection.side == "home_or_draw"
