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

    OpenClaw can invoke the command in its controlled runtime. This wrapper lets V2
    advertise only the capabilities the legacy browser integration has actually proven.
    """

    bookmaker_slug: str
    command: str
    proven_capabilities: set[BookmakerCapability] = field(default_factory=set)
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
        )


def legacy_command_adapters() -> AdapterRegistry:
    """Register only capabilities demonstrated by existing V1 browser scripts.

    Import/conversion/search capabilities are deliberately not claimed yet.
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
            notes="V1 Playwright builder; must be revalidated on the controlled OpenClaw runtime before V2 release.",
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
            notes="V1 Playwright builder; must be revalidated on the controlled OpenClaw runtime before V2 release.",
        )
    )
    return registry
