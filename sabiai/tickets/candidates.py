from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from sabiai.domain.aliases import normalize_name
from sabiai.domain.models import Market, Selection, Ticket
from sabiai.markets import MarketInterpreter

from .workshop import TicketWorkshop, TicketWorkshopError


@dataclass(frozen=True, slots=True)
class VerifiedReplacement:
    leg_id: str
    event: str
    market: str
    odds: Decimal
    bookmaker: str
    observed_at: str
    home: str | None = None
    away: str | None = None
    note: str | None = None


@dataclass(frozen=True, slots=True)
class VariantChange:
    leg_id: str
    event: str
    before: str
    after: str
    before_odds: Decimal
    after_odds: Decimal
    bookmaker: str
    observed_at: str


@dataclass(slots=True)
class TicketCandidateSummary:
    label: str
    ticket_id: str
    leg_count: int
    combined_odds: Decimal
    odds_change_from_base: Decimal | None
    changed_legs: int
    locked_legs: int
    source_type: str
    notes: list[str] = field(default_factory=list)


class VerifiedVariantService:
    """Build/compare ticket variants using only already freshness-validated bookmaker rows.

    Freshness and bookmaker ownership are validated at the OpenClaw boundary before rows
    reach this service. This class still validates event/leg identity and market parsing and
    never fabricates odds for a changed selection.
    """

    def __init__(
        self,
        interpreter: MarketInterpreter | None = None,
        workshop: TicketWorkshop | None = None,
    ):
        self.interpreter = interpreter or MarketInterpreter()
        self.workshop = workshop or TicketWorkshop()

    def higher_odds(
        self,
        ticket: Ticket,
        replacements: list[VerifiedReplacement],
        *,
        require_increase: bool = True,
    ) -> tuple[Ticket, list[VariantChange]]:
        if not replacements:
            raise TicketWorkshopError("No fresh verified replacement prices were supplied.")
        child = ticket
        changes: list[VariantChange] = []
        used: set[str] = set()

        for replacement in replacements:
            original = next((leg for leg in child.legs if leg.id == replacement.leg_id), None)
            if original is None:
                raise TicketWorkshopError(f"Replacement refers to unknown ticket leg: {replacement.leg_id}")
            if replacement.leg_id in used:
                raise TicketWorkshopError(f"Only one replacement may be applied per leg: {replacement.leg_id}")
            event = original.event_label or original.event_id
            if normalize_name(event) != normalize_name(replacement.event):
                raise TicketWorkshopError(
                    f"Replacement event '{replacement.event}' does not match ticket event '{event}'."
                )
            if original.locked:
                raise TicketWorkshopError(f"Locked leg cannot be changed: {event}")

            home, away = replacement.home, replacement.away
            if not home and not away:
                home, away = self._participants(event)
            parsed = self.interpreter.interpret(replacement.market, home=home, away=away)
            if not parsed.understood:
                raise TicketWorkshopError(
                    parsed.reason or f"Replacement market could not be understood: {replacement.market}"
                )
            if require_increase and replacement.odds <= original.odds:
                raise TicketWorkshopError(
                    f"{event}: verified replacement {replacement.odds} is not higher than current {original.odds}."
                )

            market = Market(
                kind=parsed.kind,
                label=parsed.plain_label,
                metric=parsed.metric,
                line=parsed.line,
                period=parsed.period,
            )
            selection = Selection(
                market_id=market.id,
                label=parsed.plain_label,
                side=parsed.side,
            )
            before_label = original.selection.label
            before_odds = original.odds
            child = self.workshop.change_market(
                child,
                original.id,
                market,
                selection,
                odds=replacement.odds,
                note=(
                    replacement.note
                    or f"Changed using a fresh verified {replacement.bookmaker} price observed at {replacement.observed_at}."
                ),
            )
            changes.append(
                VariantChange(
                    leg_id=replacement.leg_id,
                    event=event,
                    before=before_label,
                    after=parsed.plain_label,
                    before_odds=before_odds,
                    after_odds=replacement.odds,
                    bookmaker=replacement.bookmaker,
                    observed_at=replacement.observed_at,
                )
            )
            used.add(replacement.leg_id)

        child.source_type = "higher_odds_variant"
        child.notes.append(
            f"Higher-odds variant made {len(changes)} change(s) using only fresh bookmaker prices supplied to Sabi Boy."
        )
        return child, changes

    def compare(
        self,
        base: Ticket,
        candidates: list[tuple[str, Ticket]],
    ) -> list[TicketCandidateSummary]:
        base_map = {self._leg_identity(leg): leg for leg in base.legs}
        rows: list[TicketCandidateSummary] = []
        for label, ticket in candidates:
            changed = 0
            for leg in ticket.legs:
                identity = self._leg_identity(leg)
                original = base_map.get(identity)
                if original is None:
                    changed += 1
                    continue
                if (
                    normalize_name(original.selection.label) != normalize_name(leg.selection.label)
                    or original.odds != leg.odds
                ):
                    changed += 1
            missing_base = len(set(base_map) - {self._leg_identity(leg) for leg in ticket.legs})
            changed += missing_base
            rows.append(
                TicketCandidateSummary(
                    label=str(label or "Candidate"),
                    ticket_id=ticket.id,
                    leg_count=len(ticket.legs),
                    combined_odds=ticket.combined_odds,
                    odds_change_from_base=(ticket.combined_odds - base.combined_odds).quantize(Decimal("0.01")),
                    changed_legs=changed,
                    locked_legs=sum(1 for leg in ticket.legs if leg.locked),
                    source_type=ticket.source_type,
                    notes=list(ticket.notes),
                )
            )
        return sorted(rows, key=lambda row: (-row.combined_odds, row.changed_legs, row.label.casefold()))

    @staticmethod
    def _participants(event: str) -> tuple[str | None, str | None]:
        low = event.casefold()
        for separator in (" vs ", " v ", " vs. ", " v. "):
            index = low.find(separator)
            if index > 0:
                return event[:index].strip(), event[index + len(separator):].strip()
        return None, None

    @staticmethod
    def _leg_identity(leg) -> str:
        return normalize_name(leg.event_label or leg.event_id)
