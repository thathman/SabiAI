from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
import re

from sabiai.domain.aliases import normalize_name
from sabiai.domain.models import Market, Selection, Ticket, TicketLeg, decimal_odds
from sabiai.markets import MarketInterpreter

from .registry import BookmakerRegistry, default_bookmakers


@dataclass(frozen=True, slots=True)
class TargetOffer:
    """One target-bookmaker selection discovered by an adapter/browser worker."""

    event: str
    market: str
    odds: Decimal | str | float
    bookmaker_slug: str
    event_ref: str | None = None
    market_ref: str | None = None
    home: str | None = None
    away: str | None = None
    sport: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "odds", decimal_odds(self.odds))
        if not self.event.strip():
            raise ValueError("Target offer needs an event name.")
        if not self.market.strip():
            raise ValueError("Target offer needs a market/selection.")
        if not self.bookmaker_slug.strip():
            raise ValueError("Target offer needs a bookmaker slug.")


@dataclass(frozen=True, slots=True)
class ConversionLeg:
    source_leg_id: str
    source_event: str
    source_selection: str
    source_odds: Decimal
    status: str
    reason: str
    target_event: str | None = None
    target_selection: str | None = None
    target_odds: Decimal | None = None
    target_event_ref: str | None = None
    target_market_ref: str | None = None


@dataclass(slots=True)
class ConversionPlan:
    source_ticket_id: str
    source_bookmaker_slug: str | None
    target_bookmaker_slug: str
    legs: list[ConversionLeg] = field(default_factory=list)
    target_ticket: Ticket | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def ready(self) -> bool:
        return bool(self.legs) and all(leg.status == "matched" for leg in self.legs) and self.target_ticket is not None

    @property
    def missing_count(self) -> int:
        return sum(1 for leg in self.legs if leg.status != "matched")


class TicketConversionService:
    """Map one normalized ticket to exact equivalent offers at another bookmaker.

    The service does not browse bookmakers itself. OpenClaw/bookmaker adapters discover
    target offers, then this service decides whether they are truly equivalent. It never
    silently substitutes a different market just because it looks similar.
    """

    _event_split = re.compile(r"\s+(?:vs\.?|v\.?)\s+", re.I)

    def __init__(
        self,
        *,
        bookmakers: BookmakerRegistry | None = None,
        interpreter: MarketInterpreter | None = None,
    ):
        self.bookmakers = bookmakers or default_bookmakers()
        self.interpreter = interpreter or MarketInterpreter()

    def plan(
        self,
        source_ticket: Ticket,
        *,
        target_bookmaker: str,
        offers: list[TargetOffer],
        source_bookmaker_slug: str | None = None,
    ) -> ConversionPlan:
        target = self.bookmakers.resolve(target_bookmaker)
        if target is None:
            raise ValueError(f"Unknown target bookmaker: {target_bookmaker}")

        wrong_book = [offer for offer in offers if normalize_name(offer.bookmaker_slug) != normalize_name(target.slug)]
        if wrong_book:
            raise ValueError("All target offers must belong to the requested target bookmaker.")

        plan = ConversionPlan(
            source_ticket_id=source_ticket.id,
            source_bookmaker_slug=source_bookmaker_slug,
            target_bookmaker_slug=target.slug,
        )
        mapped: list[tuple[TicketLeg, TargetOffer, object]] = []

        for source_leg in source_ticket.legs:
            source_event = source_leg.event_label or source_leg.event_id
            event_offers = [offer for offer in offers if self._same_event(source_leg, offer)]
            if not event_offers:
                plan.legs.append(
                    ConversionLeg(
                        source_leg_id=source_leg.id,
                        source_event=source_event,
                        source_selection=source_leg.selection.label,
                        source_odds=source_leg.odds,
                        status="missing_event",
                        reason="The target bookmaker event was not found with a safe identity match.",
                    )
                )
                continue

            exact: list[tuple[TargetOffer, object]] = []
            for offer in event_offers:
                parsed = self.interpreter.interpret(offer.market, home=offer.home, away=offer.away)
                if not parsed.understood:
                    continue
                if self._same_market(source_leg, parsed):
                    exact.append((offer, parsed))

            if not exact:
                plan.legs.append(
                    ConversionLeg(
                        source_leg_id=source_leg.id,
                        source_event=source_event,
                        source_selection=source_leg.selection.label,
                        source_odds=source_leg.odds,
                        status="missing_market",
                        reason="The event exists, but no exact equivalent market/line/period was verified.",
                    )
                )
                continue

            best_offer, parsed = max(exact, key=lambda item: item[0].odds)
            plan.legs.append(
                ConversionLeg(
                    source_leg_id=source_leg.id,
                    source_event=source_event,
                    source_selection=source_leg.selection.label,
                    source_odds=source_leg.odds,
                    status="matched",
                    reason="Exact equivalent verified; best available matching target price selected.",
                    target_event=best_offer.event,
                    target_selection=parsed.plain_label,
                    target_odds=best_offer.odds,
                    target_event_ref=best_offer.event_ref,
                    target_market_ref=best_offer.market_ref,
                )
            )
            mapped.append((source_leg, best_offer, parsed))

        if len(mapped) == len(source_ticket.legs) and source_ticket.legs:
            target_ticket = Ticket(
                bookmaker_id=target.id,
                source_type="conversion",
                source_reference=(
                    f"{source_bookmaker_slug or 'unknown'}->{target.slug}:"
                    f"{source_ticket.source_reference or source_ticket.id}"
                ),
                parent_ticket_id=source_ticket.id,
            )
            for index, (source_leg, offer, parsed) in enumerate(mapped, start=1):
                market = Market(
                    kind=parsed.kind,
                    label=parsed.plain_label,
                    metric=parsed.metric,
                    line=parsed.line,
                    period=parsed.period,
                    metadata={
                        "target_market_ref": offer.market_ref,
                        "converted_from_leg_id": source_leg.id,
                    },
                )
                selection = Selection(
                    market_id=market.id,
                    label=parsed.plain_label,
                    side=parsed.side,
                )
                target_ticket.add_leg(
                    TicketLeg(
                        event_id=offer.event_ref or f"target_event_{index}",
                        event_label=offer.event,
                        sport=offer.sport or source_leg.sport,
                        market=market,
                        selection=selection,
                        odds=offer.odds,
                        bookmaker_id=target.id,
                        locked=source_leg.locked,
                        note=f"Converted from {source_leg.selection.label}",
                    )
                )
            target_ticket.notes.append(
                f"Converted from {source_bookmaker_slug or 'source bookmaker'} to {target.name}; exact-equivalent markets only."
            )
            plan.target_ticket = target_ticket
        else:
            plan.notes.append("Conversion is not ready to build until every leg has an exact verified target equivalent.")

        return plan

    def _same_event(self, source_leg: TicketLeg, offer: TargetOffer) -> bool:
        source_event = source_leg.event_label or source_leg.event_id
        if normalize_name(source_event) == normalize_name(offer.event):
            return self._sport_compatible(source_leg.sport, offer.sport)

        source_teams = self._participants(source_event)
        offer_teams = self._participants(offer.event)
        if source_teams and offer_teams and source_teams == offer_teams:
            return self._sport_compatible(source_leg.sport, offer.sport)

        if source_teams and offer.home and offer.away:
            explicit = (normalize_name(offer.home), normalize_name(offer.away))
            if source_teams == explicit:
                return self._sport_compatible(source_leg.sport, offer.sport)

        return False

    def _same_market(self, source_leg: TicketLeg, target) -> bool:
        source = source_leg.market

        # Exact plain-language labels are the strongest signal.
        if normalize_name(source_leg.selection.label) == normalize_name(target.plain_label):
            return source.period == target.period

        if source.kind != target.kind:
            return False
        if (source.metric or None) != (target.metric or None):
            return False
        if source.line != target.line:
            return False
        if source.period != target.period:
            return False
        if source_leg.selection.side and source_leg.selection.side != target.side:
            return False

        # Player/team identity must not disappear during structural matching.
        source_label = normalize_name(source_leg.selection.label)
        if target.participant and normalize_name(target.participant) not in source_label:
            source_side = source_leg.selection.side
            if source_side not in {"home", "away", "home_or_draw", "away_or_draw", "draw", "yes", "no", "over", "under"}:
                return False

        return True

    def _participants(self, event: str) -> tuple[str, str] | None:
        parts = self._event_split.split((event or "").strip(), maxsplit=1)
        if len(parts) != 2:
            return None
        return normalize_name(parts[0]), normalize_name(parts[1])

    @staticmethod
    def _sport_compatible(source: str | None, target: str | None) -> bool:
        if not source or not target:
            return True
        return normalize_name(source) == normalize_name(target)
