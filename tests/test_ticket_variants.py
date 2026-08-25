from decimal import Decimal

from sabiai.domain.models import Market, Selection, Ticket, TicketLeg
from sabiai.domain.types import MarketKind
from sabiai.tickets import TicketVariantPlanner


def _leg(event, kind, label, odds, *, line=None, metric=None, side=None, locked=False):
    market = Market(kind=kind, label=label, line=line, metric=metric)
    selection = Selection(market_id=market.id, label=label, side=side)
    return TicketLeg(
        event_id=f"event_{len(event)}_{label[:3]}",
        event_label=event,
        sport="football",
        market=market,
        selection=selection,
        odds=Decimal(str(odds)),
        locked=locked,
    )


def _ticket():
    return Ticket(
        legs=[
            _leg("Arsenal vs Chelsea", MarketKind.WIN_DRAW_LOSE, "Arsenal to win", "1.70", side="home", locked=True),
            _leg("Liverpool vs Everton", MarketKind.TOTAL, "Over 2.5 goals", "1.85", line=Decimal("2.5"), metric="goals", side="over"),
            _leg("Leeds vs Wolves", MarketKind.HANDICAP, "Leeds +1.5 handicap", "1.55", line=Decimal("1.5"), side="home"),
        ]
    )


def test_strongest_keeps_locked_and_highest_researched_leg():
    ticket = _ticket()
    planner = TicketVariantPlanner()
    child, ranking = planner.strongest(
        ticket,
        {
            ticket.legs[0].id: (70, "Good home evidence"),
            ticket.legs[1].id: (88, "Strong scoring evidence"),
            ticket.legs[2].id: (52, "Mixed evidence"),
        },
        count=2,
    )
    assert len(child.legs) == 2
    assert ticket.legs[0].selection.label in {leg.selection.label for leg in child.legs}
    assert ticket.legs[1].selection.label in {leg.selection.label for leg in child.legs}
    assert ranking[0].score == 88


def test_lower_risk_plan_proposes_explicit_plain_language_changes():
    suggestions = TicketVariantPlanner().lower_risk_plan(_ticket())
    assert suggestions[0].suggested_market == "Arsenal or Draw — Double Chance"
    assert suggestions[1].suggested_market == "Over 1.5 goals"
    assert suggestions[2].suggested_market == "Leeds +2.5 handicap"
    assert all(item.event for item in suggestions)
