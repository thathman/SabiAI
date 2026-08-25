from __future__ import annotations

from dataclasses import dataclass, field
import re

from sabiai.domain.models import Ticket, TicketLeg
from sabiai.sports import ResearchPlanner


@dataclass(frozen=True, slots=True)
class TicketLegResearchPlan:
    leg_id: str
    event: str
    sport: str | None
    home: str | None
    away: str | None
    selection: str
    checklist: tuple[str, ...]
    market_focus: tuple[str, ...]
    needs_source_discovery: bool
    needs_specialist_scout: bool
    note: str | None = None


@dataclass(slots=True)
class TicketResearchPlan:
    ticket_id: str
    leg_count: int
    legs: list[TicketLegResearchPlan] = field(default_factory=list)
    skeptic_required: bool = False
    reasons: list[str] = field(default_factory=list)


class TicketResearchPlanner:
    """Plan research for every leg without inventing a strength score or decision."""

    _event_split = re.compile(r"\s+(?:vs\.?|v\.?)\s+", re.I)

    def __init__(self, planner: ResearchPlanner):
        self.planner = planner

    def plan(self, ticket: Ticket) -> TicketResearchPlan:
        result = TicketResearchPlan(ticket_id=ticket.id, leg_count=len(ticket.legs))
        unfamiliar = 0
        unresolved_participants = 0
        specialist = 0

        for leg in ticket.legs:
            event = leg.event_label or leg.event_id
            home, away = self._participants(event)
            sport = leg.sport or "Unknown"
            research = self.planner.plan(
                sport,
                market_text=leg.selection.label,
                home=home,
                away=away,
            )
            needs_discovery = bool(research.needs_source_discovery)
            if needs_discovery:
                unfamiliar += 1
            if not home or not away:
                unresolved_participants += 1

            market_complex = bool(research.market_focus) or leg.market.period != "full_event"
            needs_scout = needs_discovery or market_complex or not home or not away
            if needs_scout:
                specialist += 1

            note = None
            if not home or not away:
                note = "Participants cannot be safely split into home/away from the visible event name; confirm event structure before research."
            elif needs_discovery:
                note = f"Learn {sport} rules/source coverage before treating this leg as researched."

            result.legs.append(
                TicketLegResearchPlan(
                    leg_id=leg.id,
                    event=event,
                    sport=leg.sport,
                    home=home,
                    away=away,
                    selection=leg.selection.label,
                    checklist=research.checklist,
                    market_focus=research.market_focus,
                    needs_source_discovery=needs_discovery,
                    needs_specialist_scout=needs_scout,
                    note=note,
                )
            )

        if len(ticket.legs) >= 6:
            result.skeptic_required = True
            result.reasons.append("Large ticket: review how one weak leg can kill the whole ticket.")
        if unfamiliar:
            result.skeptic_required = True
            result.reasons.append(f"{unfamiliar} leg(s) use sports/competition knowledge that still needs discovery.")
        if unresolved_participants:
            result.skeptic_required = True
            result.reasons.append(f"{unresolved_participants} leg(s) do not yet have safely resolved participants.")
        if specialist >= max(3, len(ticket.legs) // 2 + 1):
            result.skeptic_required = True
            result.reasons.append("A large share of the ticket needs market-specific specialist research.")

        return result

    def _participants(self, event: str) -> tuple[str | None, str | None]:
        parts = self._event_split.split(event.strip(), maxsplit=1)
        if len(parts) != 2:
            return None, None
        return parts[0].strip(), parts[1].strip()
