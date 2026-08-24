from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
import math
from typing import Iterable

from sabiai.domain.models import Market, Selection, Ticket, TicketLeg


class TicketWorkshopError(ValueError):
    pass


def _product(legs: Iterable[TicketLeg]) -> Decimal:
    total = Decimal("1")
    for leg in legs:
        total *= leg.odds
    return total.quantize(Decimal("0.01"))


class TicketWorkshop:
    def split(self, ticket: Ticket, slips: int) -> list[Ticket]:
        if slips < 2:
            raise TicketWorkshopError("Split count must be at least 2.")
        if slips > len(ticket.legs):
            raise TicketWorkshopError("Cannot create more slips than ticket legs.")
        ordered = sorted(ticket.legs, key=lambda leg: (leg.odds, leg.id))
        buckets = [[] for _ in range(slips)]
        products = [Decimal("1") for _ in range(slips)]
        for leg in ordered:
            idx = min(range(slips), key=lambda i: (products[i], len(buckets[i]), i))
            buckets[idx].append(leg)
            products[idx] *= leg.odds
        children = []
        for index, legs in enumerate(buckets, start=1):
            children.append(
                Ticket(
                    bookmaker_id=ticket.bookmaker_id,
                    source_type="split",
                    source_reference=ticket.source_reference,
                    parent_ticket_id=ticket.id,
                    status=ticket.status,
                    legs=[replace(leg) for leg in legs],
                    notes=[*ticket.notes, f"Split {index} of {slips} from ticket {ticket.id}."],
                )
            )
        return children

    def split_by_size(self, ticket: Ticket, games_per_slip: int) -> list[Ticket]:
        if games_per_slip < 1:
            raise TicketWorkshopError("Games per slip must be at least 1.")
        if games_per_slip >= len(ticket.legs):
            raise TicketWorkshopError("Games per slip must be smaller than the original ticket.")
        children = []
        chunks = [ticket.legs[i : i + games_per_slip] for i in range(0, len(ticket.legs), games_per_slip)]
        for index, legs in enumerate(chunks, start=1):
            children.append(
                Ticket(
                    bookmaker_id=ticket.bookmaker_id,
                    source_type="split",
                    source_reference=ticket.source_reference,
                    parent_ticket_id=ticket.id,
                    status=ticket.status,
                    legs=[replace(leg) for leg in legs],
                    notes=[*ticket.notes, f"Split {index} of {len(chunks)} with up to {games_per_slip} games."],
                )
            )
        return children

    def trim_to_target(
        self,
        ticket: Ticket,
        target_odds: Decimal | float | str,
        *,
        min_legs: int = 1,
        max_states: int = 1500,
    ) -> Ticket:
        target = Decimal(str(target_odds))
        if target <= Decimal("1"):
            raise TicketWorkshopError("Target odds must be greater than 1.00.")
        if min_legs < 1:
            raise TicketWorkshopError("Minimum legs must be at least 1.")
        if not ticket.legs:
            raise TicketWorkshopError("Ticket has no legs.")
        if min_legs > len(ticket.legs):
            raise TicketWorkshopError("Minimum legs exceeds ticket size.")
        locked = [leg for leg in ticket.legs if leg.locked]
        optional = [leg for leg in ticket.legs if not leg.locked]
        locked_product = _product(locked)
        states: list[tuple[list[TicketLeg], Decimal]] = [([], Decimal("1"))]
        for leg in optional:
            expanded = states + [(chosen + [leg], product * leg.odds) for chosen, product in states]
            ranked = {}
            for chosen, product in expanded:
                count = len(locked) + len(chosen)
                final_product = product * locked_product
                distance = abs(math.log(float(final_product)) - math.log(float(target)))
                key = (count, int(distance * 10000))
                incumbent = ranked.get(key)
                if incumbent is None or len(chosen) > len(incumbent[0]):
                    ranked[key] = (chosen, product)
            states = sorted(ranked.values(), key=lambda s: self._score(locked + s[0], target, min_legs))[:max_states]
        valid = [state for state in states if len(locked) + len(state[0]) >= min_legs]
        if not valid:
            raise TicketWorkshopError("No valid trimmed ticket could be built.")
        chosen, _ = min(valid, key=lambda s: self._score(locked + s[0], target, min_legs))
        final_legs = locked + chosen
        return Ticket(
            bookmaker_id=ticket.bookmaker_id,
            source_type="trim",
            source_reference=ticket.source_reference,
            parent_ticket_id=ticket.id,
            status=ticket.status,
            legs=[replace(leg) for leg in final_legs],
            notes=[*ticket.notes, f"Trimmed from {ticket.combined_odds} to {_product(final_legs)} toward target {target.quantize(Decimal('0.01'))}."],
        )

    def remove(self, ticket: Ticket, leg_ids: set[str]) -> Ticket:
        if any(leg.id in leg_ids and leg.locked for leg in ticket.legs):
            raise TicketWorkshopError("A locked leg cannot be removed.")
        remaining = [replace(leg) for leg in ticket.legs if leg.id not in leg_ids]
        if len(remaining) == len(ticket.legs):
            raise TicketWorkshopError("None of the requested games were found on the ticket.")
        if not remaining:
            raise TicketWorkshopError("Removing those legs would leave an empty ticket.")
        return Ticket(
            bookmaker_id=ticket.bookmaker_id,
            source_type="edit",
            source_reference=ticket.source_reference,
            parent_ticket_id=ticket.id,
            status=ticket.status,
            legs=remaining,
            notes=[*ticket.notes, f"Removed {len(ticket.legs)-len(remaining)} leg(s)."],
        )

    def keep_only(self, ticket: Ticket, leg_ids: set[str]) -> Ticket:
        locked_ids = {leg.id for leg in ticket.legs if leg.locked}
        if not locked_ids.issubset(leg_ids):
            raise TicketWorkshopError("Locked legs must remain on the ticket.")
        remaining = [replace(leg) for leg in ticket.legs if leg.id in leg_ids]
        if not remaining:
            raise TicketWorkshopError("Keeping those games would leave an empty ticket.")
        return Ticket(
            bookmaker_id=ticket.bookmaker_id,
            source_type="edit",
            source_reference=ticket.source_reference,
            parent_ticket_id=ticket.id,
            status=ticket.status,
            legs=remaining,
            notes=[*ticket.notes, f"Kept {len(remaining)} selected leg(s)."],
        )

    def change_market(
        self,
        ticket: Ticket,
        leg_id: str,
        market: Market,
        selection: Selection,
        *,
        odds: Decimal | float | str | None = None,
        note: str | None = None,
    ) -> Ticket:
        changed = False
        legs: list[TicketLeg] = []
        for leg in ticket.legs:
            if leg.id != leg_id:
                legs.append(replace(leg))
                continue
            if leg.locked:
                raise TicketWorkshopError("A locked leg cannot be changed.")
            changed = True
            legs.append(
                replace(
                    leg,
                    market=market,
                    selection=selection,
                    odds=leg.odds if odds is None else Decimal(str(odds)),
                    note=note or leg.note,
                )
            )
        if not changed:
            raise TicketWorkshopError("The requested game was not found on the ticket.")
        return Ticket(
            bookmaker_id=ticket.bookmaker_id,
            source_type="edit",
            source_reference=ticket.source_reference,
            parent_ticket_id=ticket.id,
            status=ticket.status,
            legs=legs,
            notes=[*ticket.notes, f"Changed the market on leg {leg_id}."],
        )

    def replace_leg(self, ticket: Ticket, leg_id: str, replacement: TicketLeg) -> Ticket:
        changed = False
        legs: list[TicketLeg] = []
        for leg in ticket.legs:
            if leg.id != leg_id:
                legs.append(replace(leg))
                continue
            if leg.locked:
                raise TicketWorkshopError("A locked leg cannot be replaced.")
            changed = True
            legs.append(replace(replacement))
        if not changed:
            raise TicketWorkshopError("The requested game was not found on the ticket.")
        return Ticket(
            bookmaker_id=ticket.bookmaker_id,
            source_type="edit",
            source_reference=ticket.source_reference,
            parent_ticket_id=ticket.id,
            status=ticket.status,
            legs=legs,
            notes=[*ticket.notes, f"Replaced leg {leg_id}."],
        )

    @staticmethod
    def _score(legs: list[TicketLeg], target: Decimal, min_legs: int) -> tuple[float, int]:
        if len(legs) < min_legs:
            return (10000 + (min_legs - len(legs)) * 100, -len(legs))
        distance = abs(math.log(float(_product(legs))) - math.log(float(target)))
        return (distance, -len(legs))
