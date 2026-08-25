import unittest

from sabiai.tickets import TicketNormalizer, TicketTextImporter


class TicketTextImportTests(unittest.TestCase):
    def setUp(self):
        self.importer = TicketTextImporter()
        self.normalizer = TicketNormalizer()

    def test_inline_ticket_lines(self):
        extracted = self.importer.extract(
            """
            Arsenal vs Chelsea — Arsenal to win @ 1.60
            Barcelona vs Sevilla — Over 2.5 goals @ 1.75
            """
        )
        self.assertTrue(extracted.complete)
        self.assertEqual(len(extracted.legs), 2)
        result = self.normalizer.normalize(
            [leg.as_dict() for leg in extracted.legs], bookmaker="SportyBet"
        )
        self.assertTrue(result.usable)
        self.assertEqual(result.ticket.legs[0].event_label, "Arsenal vs Chelsea")
        self.assertEqual(result.ticket.legs[0].selection.label, "Arsenal to win")

    def test_event_then_pick_on_next_line(self):
        extracted = self.importer.extract(
            """
            Arsenal vs Chelsea
            Arsenal or Draw 1.25
            """
        )
        self.assertTrue(extracted.complete)
        self.assertEqual(extracted.legs[0].market, "Arsenal or Draw")
        self.assertEqual(extracted.legs[0].odds, "1.25")

    def test_pipe_share_format(self):
        extracted = self.importer.extract(
            "Arsenal vs Chelsea | Over 2.5 goals | 1.80"
        )
        self.assertTrue(extracted.complete)
        self.assertEqual(extracted.legs[0].home, "Arsenal")
        self.assertEqual(extracted.legs[0].away, "Chelsea")

    def test_noise_is_ignored(self):
        extracted = self.importer.extract(
            """
            Booking code: ABC123
            Combined odds: 3.20
            Arsenal vs Chelsea — Draw @ 3.20
            """
        )
        self.assertTrue(extracted.complete)
        self.assertEqual(len(extracted.legs), 1)

    def test_unparsed_lines_are_not_silently_lost(self):
        extracted = self.importer.extract("Someone's mystery tip with no price")
        self.assertFalse(extracted.complete)
        self.assertEqual(len(extracted.unparsed_lines), 1)


if __name__ == "__main__":
    unittest.main()
