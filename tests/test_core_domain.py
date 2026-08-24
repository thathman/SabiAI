import unittest
from datetime import datetime, timezone
from decimal import Decimal

from sabiai.bookmakers import default_bookmakers
from sabiai.domain import Event, Participant, Sport, Ticket, TicketLeg
from sabiai.domain.models import Market, Selection
from sabiai.domain.types import MarketKind
from sabiai.markets import MarketInterpreter
from sabiai.sources import Source, SourceCost, SourceKind, SourceRegistry


class DomainTests(unittest.TestCase):
    def setUp(self):
        self.sport = Sport(name="Football", slug="football")
        self.home = Participant(name="Arsenal", sport_id=self.sport.id)
        self.away = Participant(name="Chelsea", sport_id=self.sport.id)
        self.event = Event(sport_id=self.sport.id, name="Arsenal v Chelsea", starts_at=datetime.now(timezone.utc), home=self.home, away=self.away)

    def test_event_is_explicit(self):
        self.assertEqual(self.event.explicit_name, "Arsenal vs Chelsea")

    def test_ticket_decimal_odds(self):
        market = Market(kind=MarketKind.WINNER, label="Arsenal to win")
        selection = Selection(market_id=market.id, label="Arsenal to win")
        ticket = Ticket()
        ticket.add_leg(TicketLeg(self.event.id, market, selection, Decimal("1.50")))
        ticket.add_leg(TicketLeg(self.event.id, market, selection, Decimal("2.00")))
        self.assertEqual(ticket.combined_odds, Decimal("3.00"))

    def test_bookmaker_aliases(self):
        registry = default_bookmakers()
        self.assertEqual(registry.resolve("Sporty Bet").slug, "sportybet")
        self.assertEqual(registry.resolve("1X Bet").slug, "1xbet")


class MarketTests(unittest.TestCase):
    def setUp(self):
        self.interpreter = MarketInterpreter()

    def test_home_win_is_explicit(self):
        parsed = self.interpreter.interpret("1", home="Arsenal", away="Chelsea")
        self.assertEqual(parsed.plain_label, "Arsenal to win")

    def test_double_chance_is_explicit(self):
        parsed = self.interpreter.interpret("X2", home="Arsenal", away="Chelsea")
        self.assertEqual(parsed.plain_label, "Chelsea or Draw — Double Chance")

    def test_total_is_plain(self):
        parsed = self.interpreter.interpret("Over 2.5 Goals")
        self.assertEqual(parsed.plain_label, "Over 2.5 goals")
        self.assertEqual(parsed.line, Decimal("2.5"))

    def test_handicap_names_team(self):
        parsed = self.interpreter.interpret("Chelsea handicap +1.5", home="Arsenal", away="Chelsea")
        self.assertEqual(parsed.plain_label, "Chelsea +1.5 handicap")


class SourceTests(unittest.TestCase):
    def test_free_source_always_wins_before_paid(self):
        registry = SourceRegistry()
        registry.register(Source("Paid Feed", SourceKind.PAID_API, SourceCost.PAID, {"football"}, {"injuries"}))
        registry.register(Source("Official League", SourceKind.OFFICIAL, SourceCost.FREE, {"football"}, {"injuries"}))
        decision = registry.choose(sport="football", capability="injuries", allow_paid=True, paid_reason="fallback")
        self.assertEqual(decision.source.name, "Official League")

    def test_paid_requires_reason(self):
        registry = SourceRegistry()
        registry.register(Source("Paid Feed", SourceKind.PAID_API, SourceCost.PAID, {"football"}, {"injuries"}))
        decision = registry.choose(sport="football", capability="injuries", failed_sources=("official",), allow_paid=True)
        self.assertFalse(decision.allowed)


if __name__ == "__main__":
    unittest.main()
