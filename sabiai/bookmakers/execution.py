from __future__ import annotations

from dataclasses import dataclass, field
import re

from sabiai.domain.models import Ticket

from .adapters import AdapterRegistry, BookmakerCapability, legacy_command_adapters
from .registry import BookmakerRegistry, default_bookmakers


@dataclass(frozen=True, slots=True)
class BuildExecutionPlan:
    bookmaker_slug: str
    ready: bool
    reason: str
    command: str | None = None
    legs: tuple[dict, ...] = ()
    expects_booking_code: bool = False
    missing: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class BookingCodeImportPlan:
    bookmaker_slug: str
    booking_code: str
    ready: bool
    method: str
    reason: str
    extraction_fields: tuple[str, ...] = (
        "sport",
        "event",
        "home",
        "away",
        "market",
        "selection",
        "decimal_odds",
    )
    next_tool: str = "ticket.normalize"


class BookmakerExecutionPlanner:
    """Create controlled runtime plans without executing bookmaker pages in domain code."""

    _code = re.compile(r"^[A-Za-z0-9_-]{3,40}$")

    def __init__(
        self,
        *,
        bookmakers: BookmakerRegistry | None = None,
        adapters: AdapterRegistry | None = None,
    ):
        self.bookmakers = bookmakers or default_bookmakers()
        self.adapters = adapters or legacy_command_adapters()

    def build(self, ticket: Ticket, *, bookmaker: str) -> BuildExecutionPlan:
        target = self.bookmakers.resolve(bookmaker)
        if target is None:
            return BuildExecutionPlan("unknown", False, f"Unknown bookmaker: {bookmaker}")

        adapter = self.adapters.get(target.slug)
        if adapter is None or BookmakerCapability.TICKET_BUILD not in adapter.capabilities():
            return BuildExecutionPlan(
                target.slug,
                False,
                f"{target.name} does not yet have a proven V2 ticket builder.",
            )

        missing: list[str] = []
        legs: list[dict] = []
        for index, leg in enumerate(ticket.legs, start=1):
            if not leg.event_label:
                missing.append(f"Leg {index}: event name")
            if not leg.selection.label:
                missing.append(f"Leg {index}: selection")
            if not leg.sport:
                missing.append(f"Leg {index}: sport")
            legs.append(
                {
                    "match": leg.event_label or leg.event_id,
                    "pick": leg.selection.label,
                    "market": leg.market.label,
                    "sport": leg.sport,
                    "decimal_odds": str(leg.odds),
                    "target_market_ref": leg.market.metadata.get("target_market_ref"),
                }
            )

        if missing:
            return BuildExecutionPlan(
                target.slug,
                False,
                "The ticket is understood but is missing context required for safe bookmaker rebuilding.",
                command=getattr(adapter, "command", None),
                legs=tuple(legs),
                expects_booking_code=BookmakerCapability.BOOKING_CODE_CREATE in adapter.capabilities(),
                missing=tuple(missing),
            )

        return BuildExecutionPlan(
            target.slug,
            True,
            "Ticket has the event, sport and explicit selection context required by the registered builder.",
            command=getattr(adapter, "command", None),
            legs=tuple(legs),
            expects_booking_code=BookmakerCapability.BOOKING_CODE_CREATE in adapter.capabilities(),
        )

    def import_booking_code(self, *, bookmaker: str, booking_code: str) -> BookingCodeImportPlan:
        target = self.bookmakers.resolve(bookmaker)
        if target is None:
            return BookingCodeImportPlan(
                "unknown",
                booking_code,
                False,
                "none",
                f"Unknown bookmaker: {bookmaker}",
            )

        code = (booking_code or "").strip()
        if not self._code.fullmatch(code):
            return BookingCodeImportPlan(
                target.slug,
                code,
                False,
                "none",
                "The booking code format is empty or invalid.",
            )

        adapter = self.adapters.get(target.slug)
        if adapter and BookmakerCapability.BOOKING_CODE_IMPORT in adapter.capabilities():
            return BookingCodeImportPlan(
                target.slug,
                code,
                True,
                "adapter",
                "Use the registered bookmaker importer, then normalize the returned legs.",
            )

        # Until a proven direct importer exists, OpenClaw/browser is the honest fallback.
        return BookingCodeImportPlan(
            target.slug,
            code,
            True,
            "openclaw_browser",
            (
                f"Load booking code {code} on {target.name} using the controlled OpenClaw browser, "
                "read the restored slip without placing a wager, extract every visible leg and pass it to ticket.normalize."
            ),
        )
