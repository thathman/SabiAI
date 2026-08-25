from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol


class BookmakerCapability(str, Enum):
    EVENT_SEARCH = "event_search"
    MARKET_SEARCH = "market_search"
    ODDS_READ = "odds_read"
    BOOKING_CODE_IMPORT = "booking_code_import"
    TICKET_BUILD = "ticket_build"
    BOOKING_CODE_CREATE = "booking_code_create"


@dataclass(frozen=True, slots=True)
class AdapterStatus:
    bookmaker_slug: str
    capabilities: tuple[str, ...]
    enabled: bool = True
    health: str = "unknown"
    notes: str | None = None
    supported_sports: tuple[str, ...] = ()
    supported_market_kinds: tuple[str, ...] = ()
    supported_periods: tuple[str, ...] = ()


class BookmakerAdapter(Protocol):
    bookmaker_slug: str

    def capabilities(self) -> set[BookmakerCapability]: ...

    def status(self) -> AdapterStatus: ...


@dataclass
class AdapterRegistry:
    """Runtime registry for proven bookmaker integrations.

    A bookmaker being known to Sabi does not mean every integration feature is ready.
    Capabilities are exposed only by an adapter that actually implements them.
    """

    _adapters: dict[str, BookmakerAdapter] = field(default_factory=dict)

    def register(self, adapter: BookmakerAdapter) -> None:
        self._adapters[adapter.bookmaker_slug.casefold()] = adapter

    def get(self, bookmaker_slug: str) -> BookmakerAdapter | None:
        return self._adapters.get((bookmaker_slug or "").casefold())

    def supports(self, bookmaker_slug: str, capability: BookmakerCapability) -> bool:
        adapter = self.get(bookmaker_slug)
        return bool(adapter and capability in adapter.capabilities())

    def statuses(self) -> list[AdapterStatus]:
        return [
            adapter.status()
            for _, adapter in sorted(self._adapters.items(), key=lambda item: item[0])
        ]


@dataclass
class CommandBookmakerAdapter:
    """Describe an existing browser/command integration without executing it here.

    The allow-lists below are deliberately narrow. A legacy builder may technically click
    other text, but V2 only sends it sports/markets/periods that have been explicitly judged
    safe enough for that implementation. Everything else stays in planning/browser mode.
    """

    bookmaker_slug: str
    command: str
    proven_capabilities: set[BookmakerCapability] = field(default_factory=set)
    supported_sports: set[str] = field(default_factory=set)
    supported_market_kinds: set[str] = field(default_factory=set)
    supported_periods: set[str] = field(default_factory=lambda: {"full_event"})
    enabled: bool = True
    health: str = "unknown"
    notes: str | None = None

    def capabilities(self) -> set[BookmakerCapability]:
        return set(self.proven_capabilities)

    def status(self) -> AdapterStatus:
        return AdapterStatus(
            bookmaker_slug=self.bookmaker_slug,
            capabilities=tuple(sorted(cap.value for cap in self.proven_capabilities)),
            enabled=self.enabled,
            health=self.health,
            notes=self.notes,
            supported_sports=tuple(sorted(self.supported_sports)),
            supported_market_kinds=tuple(sorted(self.supported_market_kinds)),
            supported_periods=tuple(sorted(self.supported_periods)),
        )


def legacy_command_adapters() -> AdapterRegistry:
    """Register only capabilities demonstrated by existing V1 browser scripts.

    Import/conversion/search capabilities are deliberately not claimed yet. Market scope is
    intentionally narrower than the long-term V2 Ticket Workshop.
    """

    registry = AdapterRegistry()
    registry.register(
        CommandBookmakerAdapter(
            bookmaker_slug="sportybet",
            command="python3 scripts/sportybet_book.py",
            proven_capabilities={
                BookmakerCapability.TICKET_BUILD,
                BookmakerCapability.BOOKING_CODE_CREATE,
            },
            supported_market_kinds={"win_draw_lose", "winner"},
            supported_periods={"full_event"},
            notes=(
                "V1 Playwright text-search builder. V2 currently permits only full-event match-winner/1X2 selections; "
                "broader markets require a new verified adapter."
            ),
        )
    )
    registry.register(
        CommandBookmakerAdapter(
            bookmaker_slug="bet9ja",
            command="python3 scripts/bet9ja_book.py",
            proven_capabilities={
                BookmakerCapability.TICKET_BUILD,
                BookmakerCapability.BOOKING_CODE_CREATE,
            },
            supported_sports={"football", "soccer"},
            supported_market_kinds={"win_draw_lose"},
            supported_periods={"full_event"},
            notes=(
                "V1 Playwright builder clicks Bet9ja's 1X2 market id. V2 restricts it to full-event football 1X2 until "
                "new market-aware selectors are implemented and validated."
            ),
        )
    )
    return registry
