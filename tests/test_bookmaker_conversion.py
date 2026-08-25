import unittest
from decimal import Decimal

from sabiai.bookmakers import (
    BookmakerExecutionPlanner,
    TargetOffer,
    TicketConversionService,
)
from sabiai.tickets import TicketNormalizer


class ConversionTests(unittest.TestCase):
    def setUp(self):
        self.normalizer = TicketNormalizer()
        normalized = self.normalizer.normalize(
            [
                {
                    "sport": "Football",
                    "event": "Arsenal vs Chelsea",
                    "home": "Arsenal",
                    "away": "Chelsea",
                    "market": "Arsenal to win",
                    "odds": "1.70",
                },
                {
                    "sport": "Football",
                    "event": "Barcelona vs Sevilla",
                    "home": "Barcelona",
                    "away": "Sevilla",
                    "market": "Over 2.5 goals",
                    "odds": "1.80",
                },
            ],
            bookmaker="Bet9ja",
            source_type="booking_code",
            source_reference="ABC123",
        )
        self.assertTrue(normalized.usable)
        self.ticket = normalized.ticket

    def test_exact_conversion_selects_best_matching_price(self):
        offers = [
            TargetOffer(
                bookmaker_slug="sportybet",
                sport="Football",
                event="Arsenal vs Chelsea",
                home="Arsenal",
                away="Chelsea",
                market="1",
                odds="1.72",
                event_ref="sp_evt_1",
            ),
            TargetOffer(
                bookmaker_slug="sportybet",
                sport="Football",
                event="Arsenal vs Chelsea",
                home="Arsenal",
                away="Chelsea",
                market="Arsenal to win",
                odds="1.76",
                event_ref="sp_evt_1",
            ),
            TargetOffer(
                bookmaker_slug="sportybet",
                sport="Football",
                event="Barcelona vs Sevilla",
                home="Barcelona",
                away="Sevilla",
                market="Over 2.5 goals",
                odds="1.84",
                event_ref="sp_evt_2",
            ),
        ]
        plan = TicketConversionService().plan(
            self.ticket,
            target_bookmaker="SportyBet",
            source_bookmaker_slug="bet9ja",
            offers=offers,
        )
        self.assertTrue(plan.ready)
        self.assertEqual(plan.missing_count, 0)
        self.assertEqual(plan.target_ticket.parent_ticket_id, self.ticket.id)
        self.assertEqual(plan.target_ticket.legs[0].odds, Decimal("1.760"))
        self.assertEqual(plan.target_ticket.legs[0].sport, "Football")
        self.assertEqual(plan.target_ticket.legs[0].selection.label, "Arsenal to win")
        self.assertEqual(plan.target_ticket.combined_odds, Decimal("3.24"))

    def test_different_line_is_not_silently_substituted(self):
        offers = [
            TargetOffer(
                bookmaker_slug="sportybet",
                sport="Football",
                event="Arsenal vs Chelsea",
                home="Arsenal",
                away="Chelsea",
                market="Arsenal to win",
                odds="1.76",
            ),
            TargetOffer(
                bookmaker_slug="sportybet",
                sport="Football",
                event="Barcelona vs Sevilla",
                home="Barcelona",
                away="Sevilla",
                market="Over 3.5 goals",
                odds="2.30",
            ),
        ]
        plan = TicketConversionService().plan(
            self.ticket,
            target_bookmaker="SportyBet",
            offers=offers,
        )
        self.assertFalse(plan.ready)
        self.assertEqual(plan.missing_count, 1)
        missing = next(leg for leg in plan.legs if leg.status != "matched")
        self.assertEqual(missing.status, "missing_market")

    def test_sport_mismatch_blocks_event_match(self):
        offers = [
            TargetOffer(
                bookmaker_slug="sportybet",
                sport="Basketball",
                event="Arsenal vs Chelsea",
                home="Arsenal",
                away="Chelsea",
                market="Arsenal to win",
                odds="1.76",
            )
        ]
        one_leg = self.normalizer.normalize(
            [
                {
                    "sport": "Football",
                    "event": "Arsenal vs Chelsea",
                    "home": "Arsenal",
                    "away": "Chelsea",
                    "market": "Arsenal to win",
                    "odds": "1.70",
                }
            ]
        ).ticket
        plan = TicketConversionService().plan(
            one_leg,
            target_bookmaker="SportyBet",
            offers=offers,
        )
        self.assertFalse(plan.ready)
        self.assertEqual(plan.legs[0].status, "missing_event")


class ExecutionPlanTests(unittest.TestCase):
    def setUp(self):
        self.normalizer = TicketNormalizer()

    def test_build_plan_uses_explicit_match_pick_and_sport(self):
        ticket = self.normalizer.normalize(
            [
                {
                    "sport": "Football",
                    "event": "Arsenal vs Chelsea",
                    "home": "Arsenal",
                    "away": "Chelsea",
                    "market": "Arsenal to win",
                    "odds": "1.70",
                }
            ],
            bookmaker="SportyBet",
        ).ticket
        plan = BookmakerExecutionPlanner().build(ticket, bookmaker="SportyBet")
        self.assertTrue(plan.ready)
        self.assertTrue(plan.expects_booking_code)
        self.assertEqual(plan.legs[0]["match"], "Arsenal vs Chelsea")
        self.assertEqual(plan.legs[0]["pick"], "Arsenal to win")
        self.assertEqual(plan.legs[0]["sport"], "Football")

    def test_build_plan_refuses_missing_sport_context(self):
        ticket = self.normalizer.normalize(
            [
                {
                    "event": "Arsenal vs Chelsea",
                    "home": "Arsenal",
                    "away": "Chelsea",
                    "market": "Arsenal to win",
                    "odds": "1.70",
                }
            ]
        ).ticket
        plan = BookmakerExecutionPlanner().build(ticket, bookmaker="Bet9ja")
        self.assertFalse(plan.ready)
        self.assertIn("sport", plan.missing[0].lower())

    def test_booking_code_import_uses_openclaw_browser_until_adapter_exists(self):
        plan = BookmakerExecutionPlanner().import_booking_code(
            bookmaker="Bet9ja",
            booking_code="AB12CD",
        )
        self.assertTrue(plan.ready)
        self.assertEqual(plan.method, "openclaw_browser")
        self.assertEqual(plan.next_tool, "ticket.normalize")


if __name__ == "__main__":
    unittest.main()
