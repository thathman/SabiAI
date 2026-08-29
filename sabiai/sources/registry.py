from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable


class SourceCost(str, Enum):
    FREE = "free"
    PAID = "paid"


class SourceKind(str, Enum):
    CACHE = "cache"
    OPEN_DATA = "open_data"
    OFFICIAL = "official"
    PUBLIC_ENDPOINT = "public_endpoint"
    PUBLIC_WEB = "public_web"
    BROWSER = "browser"
    SEARCH = "search"
    PAID_API = "paid_api"


FREE_FIRST_ORDER = {
    SourceKind.CACHE: 0,
    SourceKind.OPEN_DATA: 10,
    SourceKind.OFFICIAL: 20,
    SourceKind.PUBLIC_ENDPOINT: 30,
    SourceKind.PUBLIC_WEB: 40,
    SourceKind.BROWSER: 50,
    SourceKind.SEARCH: 60,
    SourceKind.PAID_API: 100,
}


@dataclass(slots=True)
class Source:
    name: str
    kind: SourceKind
    cost: SourceCost = SourceCost.FREE
    sports: set[str] = field(default_factory=set)
    capabilities: set[str] = field(default_factory=set)
    enabled: bool = True
    health: str = "unknown"
    notes: str | None = None
    priority_bias: int = 0
    # Optional provider-call guardrails. These are enforced before a network fetch and are
    # intentionally kept in the runtime registry rather than persisted as secrets.
    request_budget_per_day: int | None = None
    object_budget_per_month: int | None = None

    @property
    def priority(self) -> int:
        """Lower runs first while preserving the overall free-first source-kind order."""
        return FREE_FIRST_ORDER[self.kind] + int(self.priority_bias)


@dataclass(slots=True)
class AccessDecision:
    source: Source | None
    allowed: bool
    reason: str
    free_sources_tried: tuple[str, ...] = ()


@dataclass
class SourceRegistry:
    _sources: dict[str, Source] = field(default_factory=dict)

    def register(self, source: Source) -> None:
        self._sources[source.name.casefold()] = source

    def all(self) -> list[Source]:
        return sorted(self._sources.values(), key=lambda item: (item.priority, item.name.casefold()))

    def candidates(
        self,
        *,
        sport: str | None = None,
        capability: str | None = None,
        include_paid: bool = True,
    ) -> list[Source]:
        result = []
        sport_key = (sport or "").casefold()
        capability_key = (capability or "").casefold()
        for source in self._sources.values():
            if not source.enabled:
                continue
            if not include_paid and source.cost is SourceCost.PAID:
                continue
            if sport_key and source.sports and sport_key not in {s.casefold() for s in source.sports}:
                continue
            if capability_key and source.capabilities and capability_key not in {
                c.casefold() for c in source.capabilities
            }:
                continue
            result.append(source)
        return sorted(result, key=lambda item: (item.priority, item.name.casefold()))

    def choose(
        self,
        *,
        sport: str | None = None,
        capability: str | None = None,
        failed_sources: Iterable[str] = (),
        allow_paid: bool = False,
        paid_reason: str | None = None,
    ) -> AccessDecision:
        failed = {name.casefold() for name in failed_sources}
        candidates = [
            source
            for source in self.candidates(sport=sport, capability=capability, include_paid=True)
            if source.name.casefold() not in failed
        ]

        for source in candidates:
            if source.cost is SourceCost.FREE:
                return AccessDecision(
                    source=source,
                    allowed=True,
                    reason="Use the best available free source first.",
                    free_sources_tried=tuple(failed_sources),
                )

        paid = next((source for source in candidates if source.cost is SourceCost.PAID), None)
        if paid is None:
            return AccessDecision(
                source=None,
                allowed=False,
                reason="No suitable source is available.",
                free_sources_tried=tuple(failed_sources),
            )
        if not allow_paid:
            return AccessDecision(
                source=paid,
                allowed=False,
                reason="A paid source is available, but paid access has not been approved for this request.",
                free_sources_tried=tuple(failed_sources),
            )
        if not paid_reason or not paid_reason.strip():
            return AccessDecision(
                source=paid,
                allowed=False,
                reason="Paid access needs a reason after free options have been tried.",
                free_sources_tried=tuple(failed_sources),
            )
        return AccessDecision(
            source=paid,
            allowed=True,
            reason=paid_reason.strip(),
            free_sources_tried=tuple(failed_sources),
        )
