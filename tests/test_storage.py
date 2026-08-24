import tempfile
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from sabiai.domain import Event, Participant, Sport, Ticket, TicketLeg
from sabiai.domain.models import Market, Selection
from sabiai.domain.types import MarketKind
from sabiai.storage import SabiDatabase


class StorageTests(unittest.TestCase):
    def test_initialize_and_save_ticket(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = SabiDatabase(Path(tmp) / "v2.db")
            db.initialize()
            sport = Sport("Football", "football")
            db.save_sport(sport)
            home = Participant("Arsenal", sport_id=sport.id)
            away = Participant("Chelsea", sport_id=sport.id)
            event = Event(sport_id=sport.id, name="Arsenal v Chelsea", starts_at=datetime.now(timezone.utc), home=home, away=away)
            db.save_event(event)
            market = Market(MarketKind.TOTAL, "Over 2.5 goals", metric="goals", line=Decimal("2.5"))
            selection = Selection(market.id, "Over 2.5 goals", side="over")
            ticket = Ticket()
            ticket.add_leg(TicketLeg(event.id, market, selection, Decimal("1.80")))
            db.save_ticket(ticket)
            counts = db.table_counts()
            self.assertEqual(counts["sports"], 1)
            self.assertEqual(counts["events"], 1)
            self.assertEqual(counts["tickets"], 1)
            self.assertEqual(counts["ticket_legs"], 1)


if __name__ == "__main__":
    unittest.main()
