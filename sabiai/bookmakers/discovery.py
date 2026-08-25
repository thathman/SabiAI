from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import re

from sabiai.domain.models import Ticket, TicketLeg

from .registry import BookmakerRegistry, default_bookmakers


@dataclass(frozen=True, slots=True)
class BookmakerSearchTask:
    leg_id: str
    bookmaker_slug: str
    sport: str | None
    event: str
    home: str | None
    away: str | None
    selection: str
    market_kind: str
    metric: str | None
    line: Decimal | None
    period: str
    side: str | None
    instruction: str

    @property
    def market_signature(self) -> str:
        parts = [self.market_kind, self.metric or "", str(self.line) if self.line is not None else "", self.period, self.side or ""]
        return "|".join(parts)


@dataclass(frozen=True, slots=True)
class BookmakerSearchPlan:
    target_bookmaker_slug: str
    tasks: tuple[BookmakerSearchTask, ...]
    ready: bool
    missing_context: tuple[str, ...] = ()


class BookmakerDiscoveryPlanner:
    """Tell OpenClaw/bookmaker adapters exactly what must be found for each ticket leg."""

    _event_split = re.compile(r"\s+(?:vs\.?|v\.?)\s+", re.I)

    def __init__(self, bookmakers: BookmakerRegistry | None = None):
        self.bookmakers = bookmakers or default_bookmakers()

    def plan_conversion(self, ticket: Ticket, *, target_bookmaker: str) -> BookmakerSearchPlan:
        target = self.bookmakers.resolve(target_bookmaker)
        if target is None:
            raise ValueError(f"Unknown target bookmaker: {target_bookmaker}")

        tasks: list[BookmakerSearchTask] = []
        missing: list[str] = []
        for index, leg in enumerate(ticket.legs, start=1):
            event = (leg.event_label or "").strip()
            if not event:
                missing.append(f"Leg {index}: visible event name")
                continue
            if not leg.sport:
                missing.append(f"Leg {index} ({event}): sport")
            home, away = self._teams(event)
            tasks.append(self._task(leg, target.slug, home, away))

        return BookmakerSearchPlan(
            target_bookmaker_slug=target.slug,
            tasks=tuple(tasks),
            ready=bool(tasks) and not missing and len(tasks) == len(ticket.legs),
            missing_context=tuple(missing),
        )

    def _task(
        self,
        leg: TicketLeg,
        target_slug: str,
        home: str | None,
        away: str | None,
    ) -> BookmakerSearchTask:
        market = leg.market
        event = leg.event_label or leg.event_id
        line_text = f" line {market.line}" if market.line is not None else ""
        metric_text = f" {market.metric.replace('_', ' ')}" if market.metric else ""
        period_text = "full event" if market.period == "full_event" else market.period.replace("_", " ")
        instruction = (
            f"On {target_slug}, find the {leg.sport or 'specified sport'} event {event}. "
            f"Find the exact equivalent of '{leg.selection.label}'. Match market type {market.kind.value}{metric_text}{line_text}, "
            f"period {period_text}, and selection side {leg.selection.side or 'as named'}. "
            "Return the target event name/id, exact market label/id and current decimal odds. Do not substitute a different line or period."
        )
        return BookmakerSearchTask(
            leg_id=leg.id,
            bookmaker_slug=target_slug,
            sport=leg.sport,
            event=event,
            home=home,
            away=away,
            selection=leg.selection.label,
            market_kind=market.kind.value,
            metric=market.metric,
            line=market.line,
            period=market.period,
            side=leg.selection.side,
            instruction=instruction,
        )

    def _teams(self, event: str) -> tuple[str | None, str | None]:
        parts = self._event_split.split(event.strip(), maxsplit=1)
        if len(parts) != 2:
            return None, None
        return parts[0].strip(), parts[1].strip()
