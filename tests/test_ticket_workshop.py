import unittest
from decimal import Decimal
from sabiai.domain.models import Market, Selection, Ticket, TicketLeg
from sabiai.domain.types import MarketKind
from sabiai.openclaw import SabiToolGateway
from sabiai.tickets import TicketWorkshop

def leg(name: str, odds: str, locked: bool = False) -> TicketLeg:
    market = Market(MarketKind.WINNER, f"{name} to win")
    selection = Selection(market.id, f"{name} to win")
    return TicketLeg(event_id=f"event_{name}", market=market, selection=selection, odds=Decimal(odds), locked=locked)

class TicketWorkshopTests(unittest.TestCase):
    def test_split(self):
        ticket=Ticket(legs=[leg("A","1.20"),leg("B","1.30"),leg("C","1.80"),leg("D","2.00")])
        children=TicketWorkshop().split(ticket,2)
        self.assertEqual(len(children),2)
        self.assertEqual(sum(len(c.legs) for c in children),4)
        self.assertTrue(all(c.parent_ticket_id==ticket.id for c in children))

    def test_trim_preserves_locked(self):
        locked=leg("A","1.40",True)
        ticket=Ticket(legs=[locked,leg("B","1.50"),leg("C","2.00"),leg("D","2.50")])
        trimmed=TicketWorkshop().trim_to_target(ticket,"3.00",min_legs=2)
        self.assertIn(locked.selection.label,[x.selection.label for x in trimmed.legs])

    def test_gateway_plain_market(self):
        result=SabiToolGateway().dispatch("market.interpret",{"text":"X2","home":"Arsenal","away":"Chelsea"})
        self.assertTrue(result["ok"])
        self.assertEqual(result["data"]["plain_label"],"Chelsea or Draw — Double Chance")

    def test_gateway_trim(self):
        result=SabiToolGateway().dispatch("ticket.trim",{"target_odds":"3.00","min_legs":2,"legs":[{"event_id":"1","market":"1","home":"Arsenal","away":"Chelsea","odds":"1.40","locked":True},{"event_id":"2","market":"2","home":"Milan","away":"Inter","odds":"1.50"},{"event_id":"3","market":"Over 2.5 goals","home":"PSG","away":"Lyon","odds":"2.00"}]})
        self.assertTrue(result["ok"])
        self.assertGreaterEqual(len(result["data"]["ticket"]["legs"]),2)

if __name__=="__main__":
    unittest.main()
