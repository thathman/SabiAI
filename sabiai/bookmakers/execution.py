from __future__ import annotations

from dataclasses import dataclass, field
import re

from sabiai.domain.models import Ticket

from .adapters import AdapterRegistry, BookmakerCapability, legacy_command_adapters
from .browser_profiles import BookmakerBrowserProfiles
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
        "leg_count",
        "combined_odds",
    )
    next_tool: str = "bookmaker.booking_code.restore"
    entry_url: str | None = None
    code_prompt: str | None = None
    load_action: str | None = None
    verified_on: str | None = None
    verification_note: str | None = None


class BookmakerExecutionPlanner:
    """Create controlled runtime plans without executing bookmaker pages in domain code."""

    _code = re.compile(r"^[A-Za-z0-9_-]{3,40}$")

    def __init__(
        self,
        *,
        bookmakers: BookmakerRegistry | None = None,
        adapters: AdapterRegistry | None = None,
        browser_profiles: BookmakerBrowserProfiles | None = None,
    ):
        self.bookmakers = bookmakers or default_bookmakers()
        self.adapters = adapters or legacy_command_adapters()
        self.browser_profiles = browser_profiles or BookmakerBrowserProfiles()

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
        supported_sports = {value.casefold() for value in getattr(adapter, "supported_sports", set())}
        supported_markets = {value.casefold() for value in getattr(adapter, "supported_market_kinds", set())}
        supported_periods = {value.casefold() for value in getattr(adapter, "supported_periods", set())}

        for index, leg in enumerate(ticket.legs, start=1):
            sport_key = (leg.sport or "").strip().casefold()
            market_key = leg.market.kind.value.casefold()
            period_key = (leg.market.period or "full_event").strip().casefold()

            if not leg.event_label:
                missing.append(f"Leg {index}: event name")
            if not leg.selection.label:
                missing.append(f"Leg {index}: selection")
            if not leg.sport:
                missing.append(f"Leg {index}: sport")
            if supported_sports and sport_key not in supported_sports:
                missing.append(
                    f"Leg {index}: {target.name} legacy builder is not proven for sport '{leg.sport}'."
                )
            if supported_markets and market_key not in supported_markets:
                missing.append(
                    f"Leg {index}: {target.name} legacy builder is not proven for market '{leg.market.label}' ({market_key})."
                )
            if supported_periods and period_key not in supported_periods:
                missing.append(
                    f"Leg {index}: {target.name} legacy builder is not proven for period '{leg.market.period}'."
                )

            legs.append(
                {
                    "match": leg.event_label or leg.event_id,
                    "pick": leg.selection.label,
                    "market": leg.market.label,
                    "market_kind": leg.market.kind.value,
                    "period": leg.market.period,
                    "sport": leg.sport,
                    "decimal_odds": str(leg.odds),
                    "target_market_ref": leg.market.metadata.get("target_market_ref"),
                }
            )

        if missing:
            return BuildExecutionPlan(
                target.slug,
                False,
                (
                    "The ticket is understood, but the registered legacy builder is missing context or is not proven "
                    "for every requested sport/market/period. Use bookmaker search/browser planning instead of executing it."
                ),
                command=getattr(adapter, "command", None),
                legs=tuple(legs),
                expects_booking_code=BookmakerCapability.BOOKING_CODE_CREATE in adapter.capabilities(),
                missing=tuple(missing),
            )

        return BuildExecutionPlan(
            target.slug,
            True,
            "Every leg is inside the explicitly proven scope of the registered builder.",
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
                "Use the registered bookmaker importer, then validate the returned slip with bookmaker.booking_code.restore.",
            )

        profile = self.browser_profiles.get(target.slug)
        if profile and profile.public_restore and profile.entry_url:
            return BookingCodeImportPlan(
                target.slug,
                code,
                True,
                "openclaw_browser",
                (
                    f"Open {profile.entry_url} in the controlled OpenClaw browser, locate '{profile.code_prompt or 'the bet-code field'}', "
                    f"enter booking code {code}, use '{profile.load_action or 'the visible load action'}', and read the restored slip without placing a wager. "
                    "Extract every visible leg plus displayed leg count/combined odds, then call bookmaker.booking_code.restore."
                ),
                extraction_fields=profile.extraction_fields,
                entry_url=profile.entry_url,
                code_prompt=profile.code_prompt,
                load_action=profile.load_action,
                verified_on=profile.verified_on,
                verification_note=profile.verification_note,
            )

        note = profile.verification_note if profile else "No browser restoration profile exists yet."
        return BookingCodeImportPlan(
            target.slug,
            code,
            False,
            "discover_current_flow",
            (
                f"A current public booking-code restoration flow has not been verified for {target.name}. "
                "Use OpenClaw source/browser discovery to verify the live public flow before importing this code."
            ),
            verified_on=profile.verified_on if profile else None,
            verification_note=note,
        )
