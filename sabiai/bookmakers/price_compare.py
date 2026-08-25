from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from sabiai.domain.models import Ticket

from .conversion import TicketConversionService
from .search_results import OfferBatch


@dataclass(frozen=True, slots=True)
class BookmakerLegPrice:
    bookmaker_slug: str
    odds: Decimal
    event: str
    selection: str
    event_ref: str | None = None
    market_ref: str | None = None


@dataclass(slots=True)
class TicketLegPriceComparison:
    source_leg_id: str
    event: str
    selection: str
    source_ticket_odds: Decimal
    prices: list[BookmakerLegPrice] = field(default_factory=list)

    @property
    def best(self) -> BookmakerLegPrice | None:
        if not self.prices:
            return None
        return max(self.prices, key=lambda row: (row.odds, row.bookmaker_slug.casefold()))


@dataclass(slots=True)
class TicketPriceComparison:
    ticket_id: str
    legs: list[TicketLegPriceComparison] = field(default_factory=list)
    bookmaker_notes: dict[str, list[str]] = field(default_factory=dict)

    @property
    def priced_legs(self) -> int:
        return sum(1 for leg in self.legs if leg.prices)

    @property
    def complete(self) -> bool:
        return bool(self.legs) and all(leg.prices for leg in self.legs)


class TicketPriceComparisonService:
    """Compare exact equivalent ticket selections across several bookmaker result batches.

    Browser/search rows are validated before they reach this service. Exact market identity is
    then rechecked through the same conversion engine used for cross-book rebuilds, so a better
    price on a different line/period is never presented as the same selection.

    The odds carried on the source ticket are shown only as historical/source context. They are
    not included in the live 'best price' ranking unless that bookmaker is also supplied as a
    fresh search batch.
    """

    def __init__(self, converter: TicketConversionService):
        self.converter = converter

    def compare(
        self,
        ticket: Ticket,
        *,
        batches: list[OfferBatch],
        source_bookmaker_slug: str | None = None,
    ) -> TicketPriceComparison:
        result = TicketPriceComparison(
            ticket_id=ticket.id,
            legs=[
                TicketLegPriceComparison(
                    source_leg_id=leg.id,
                    event=leg.event_label or leg.event_id,
                    selection=leg.selection.label,
                    source_ticket_odds=leg.odds,
                )
                for leg in ticket.legs
            ],
        )
        by_leg = {leg.source_leg_id: leg for leg in result.legs}

        for batch in batches:
            slug = batch.target_bookmaker_slug
            notes = [issue.message for issue in batch.issues]
            if not batch.offers:
                notes.append("No fresh valid offers were available for exact-market comparison.")
                result.bookmaker_notes[slug] = notes
                continue

            plan = self.converter.plan(
                ticket,
                target_bookmaker=slug,
                offers=[item.offer for item in batch.offers],
                source_bookmaker_slug=source_bookmaker_slug,
            )
            for row in plan.legs:
                if row.status != "matched" or row.target_odds is None:
                    notes.append(f"{row.source_event} — {row.source_selection}: {row.reason}")
                    continue
                target = by_leg.get(row.source_leg_id)
                if target is None:
                    continue
                target.prices.append(
                    BookmakerLegPrice(
                        bookmaker_slug=slug,
                        odds=row.target_odds,
                        event=row.target_event or row.source_event,
                        selection=row.target_selection or row.source_selection,
                        event_ref=row.target_event_ref,
                        market_ref=row.target_market_ref,
                    )
                )
            result.bookmaker_notes[slug] = notes

        for leg in result.legs:
            leg.prices.sort(key=lambda row: (-row.odds, row.bookmaker_slug.casefold()))
        return result
