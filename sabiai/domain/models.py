from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import uuid4

from .types import (
    EventStatus,
    MarketKind,
    Outcome,
    ParticipantType,
    TicketStatus,
)


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def decimal_odds(value: Decimal | float | int | str) -> Decimal:
    try:
        odds = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError("Decimal odds must be a number.") from exc
    if odds <= Decimal("1"):
        raise ValueError("Decimal odds must be greater than 1.00.")
    return odds.quantize(Decimal("0.001"))


@dataclass(slots=True)
class Sport:
    name: str
    slug: str
    id: str = field(default_factory=lambda: _id("sport"))
    aliases: set[str] = field(default_factory=set)


@dataclass(slots=True)
class Competition:
    sport_id: str
    name: str
    country: str | None = None
    season: str | None = None
    id: str = field(default_factory=lambda: _id("competition"))
    aliases: set[str] = field(default_factory=set)


@dataclass(slots=True)
class Participant:
    name: str
    participant_type: ParticipantType = ParticipantType.TEAM
    sport_id: str | None = None
    id: str = field(default_factory=lambda: _id("participant"))
    aliases: set[str] = field(default_factory=set)


@dataclass(slots=True)
class Event:
    sport_id: str
    name: str
    starts_at: datetime
    home: Participant | None = None
    away: Participant | None = None
    competition_id: str | None = None
    status: EventStatus = EventStatus.SCHEDULED
    venue: str | None = None
    id: str = field(default_factory=lambda: _id("event"))
    source_ids: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.starts_at.tzinfo is None:
            self.starts_at = self.starts_at.replace(tzinfo=timezone.utc)

    @property
    def explicit_name(self) -> str:
        if self.home and self.away:
            return f"{self.home.name} vs {self.away.name}"
        return self.name


@dataclass(slots=True)
class Market:
    kind: MarketKind
    label: str
    metric: str | None = None
    line: Decimal | None = None
    period: str = "full_event"
    participant_id: str | None = None
    id: str = field(default_factory=lambda: _id("market"))
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Selection:
    market_id: str
    label: str
    side: str | None = None
    participant_id: str | None = None
    id: str = field(default_factory=lambda: _id("selection"))


@dataclass(slots=True)
class Bookmaker:
    name: str
    slug: str
    id: str = field(default_factory=lambda: _id("bookmaker"))
    aliases: set[str] = field(default_factory=set)
    capabilities: set[str] = field(default_factory=set)


@dataclass(slots=True)
class Pick:
    event_id: str
    market: Market
    selection: Selection
    odds: Decimal
    bookmaker_id: str | None = None
    confidence_pct: float | None = None
    rationale: str | None = None
    outcome: Outcome = Outcome.PENDING
    id: str = field(default_factory=lambda: _id("pick"))
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        self.odds = decimal_odds(self.odds)
        if self.confidence_pct is not None and not 0 <= self.confidence_pct <= 100:
            raise ValueError("Confidence must be between 0 and 100.")


@dataclass(slots=True)
class TicketLeg:
    event_id: str
    market: Market
    selection: Selection
    odds: Decimal
    event_label: str | None = None
    bookmaker_id: str | None = None
    locked: bool = False
    outcome: Outcome = Outcome.PENDING
    id: str = field(default_factory=lambda: _id("leg"))
    note: str | None = None

    def __post_init__(self) -> None:
        self.odds = decimal_odds(self.odds)


@dataclass(slots=True)
class Ticket:
    bookmaker_id: str | None = None
    source_type: str = "instruction"
    source_reference: str | None = None
    parent_ticket_id: str | None = None
    status: TicketStatus = TicketStatus.DRAFT
    id: str = field(default_factory=lambda: _id("ticket"))
    legs: list[TicketLeg] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    notes: list[str] = field(default_factory=list)

    @property
    def combined_odds(self) -> Decimal:
        total = Decimal("1")
        for leg in self.legs:
            total *= leg.odds
        return total.quantize(Decimal("0.01"))

    def add_leg(self, leg: TicketLeg) -> None:
        self.legs.append(leg)
