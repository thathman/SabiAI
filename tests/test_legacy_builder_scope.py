from decimal import Decimal

from sabiai.bookmakers import BookmakerExecutionPlanner
from sabiai.domain.models import Market, Selection, Ticket, TicketLeg
from sabiai.domain.types import MarketKind


def _ticket(*, sport="football", kind=MarketKind.WIN_DRAW_LOSE, label="Arsenal to win", line=None, side="home"):
    market = Market(kind=kind, label=label, line=line, metric="goals" if kind is MarketKind.TOTAL else None)
    selection = Selection(market_id=market.id, label=label, side=side)
    return Ticket(
        legs=[
            TicketLeg(
                event_id="e1",
                event_label="Arsenal vs Chelsea",
                sport=sport,
                market=market,
                selection=selection,
                odds=Decimal("1.80"),
            )
        ]
    )


def test_bet9ja_rejects_total_market_from_legacy_builder():
    plan = BookmakerExecutionPlanner().build(
        _ticket(kind=MarketKind.TOTAL, label="Over 2.5 goals", line=Decimal("2.5"), side="over"),
        bookmaker="Bet9ja",
    )
    assert plan.ready is False
    assert any("not proven for market" in item for item in plan.missing)


def test_bet9ja_allows_only_proven_full_event_football_1x2_scope():
    plan = BookmakerExecutionPlanner().build(_ticket(), bookmaker="Bet9ja")
    assert plan.ready is True

    named_team = BookmakerExecutionPlanner().build(
        _ticket(kind=MarketKind.WINNER, label="Arsenal to win"),
        bookmaker="Bet9ja",
    )
    assert named_team.ready is True

    basketball = BookmakerExecutionPlanner().build(
        _ticket(sport="basketball", kind=MarketKind.WIN_DRAW_LOSE, label="Lakers to win"),
        bookmaker="Bet9ja",
    )
    assert basketball.ready is False
    assert any("not proven for sport" in item for item in basketball.missing)


def test_sportybet_rejects_player_prop_until_new_market_aware_builder_exists():
    plan = BookmakerExecutionPlanner().build(
        _ticket(
            sport="basketball",
            kind=MarketKind.PLAYER,
            label="LeBron James — Over 7.5 rebounds",
            line=Decimal("7.5"),
            side="over",
        ),
        bookmaker="SportyBet",
    )
    assert plan.ready is False
    assert any("not proven for market" in item for item in plan.missing)
