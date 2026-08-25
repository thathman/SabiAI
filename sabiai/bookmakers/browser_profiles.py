from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class BrowserPlaybook:
    bookmaker_slug: str
    restoration_mode: str
    entry_url: str | None
    public_restore: bool
    code_prompt: str | None
    load_action: str | None
    extraction_fields: tuple[str, ...]
    verified_on: str | None
    verification_note: str
    source_reference: str | None = None


DEFAULT_EXTRACTION_FIELDS = (
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


class BookmakerBrowserProfiles:
    """Human-readable browser playbooks for OpenClaw.

    These are intentionally not brittle DOM selectors. OpenClaw/browser should locate the
    visible controls described here, restore/read the slip, and hand structured output to
    `bookmaker.booking_code.restore`, where canonical validation happens.
    """

    def __init__(self):
        self._profiles = {
            "sportybet": BrowserPlaybook(
                bookmaker_slug="sportybet",
                restoration_mode="booking_code",
                entry_url="https://www.sportybet.com/ng/lite/betslip",
                public_restore=True,
                code_prompt="Please insert booking code",
                load_action="Load",
                extraction_fields=DEFAULT_EXTRACTION_FIELDS,
                verified_on="2026-08-25",
                verification_note=(
                    "Official SportyBet NG lite betslip publicly exposes a booking-code input and Load action. "
                    "Odds/availability may change after restoration; capture current displayed prices."
                ),
                source_reference="SportyBet NG public lite betslip",
            ),
            "bet9ja": BrowserPlaybook(
                bookmaker_slug="bet9ja",
                restoration_mode="booking_code",
                entry_url="https://web.bet9ja.com/Pages/Tutorial_book/Guest?NoSwitch=&noswitch=",
                public_restore=True,
                code_prompt="Insert Booking Number",
                load_action="LOAD",
                extraction_fields=DEFAULT_EXTRACTION_FIELDS,
                verified_on="2026-08-25",
                verification_note=(
                    "Bet9ja's official help and public Book-a-Bet page document loading a known booking code while logged out. "
                    "Read the restored slip only; do not continue to payment/placement."
                ),
                source_reference="Bet9ja official Book-a-Bet help/public guest page",
            ),
            "stake": BrowserPlaybook(
                bookmaker_slug="stake",
                restoration_mode="bet_code_or_shared_bet",
                entry_url="https://stake.com/sports/home",
                public_restore=True,
                code_prompt="Use Bet Code",
                load_action="Use Bet Code / load the copied or shared bet",
                extraction_fields=DEFAULT_EXTRACTION_FIELDS,
                verified_on="2026-08-25",
                verification_note=(
                    "Stake's current sportsbook UI exposes Use Bet Code, and official Stake guidance documents copy/share flows that recreate bets. "
                    "Availability may be region/account dependent, so verify the visible control before claiming restoration succeeded."
                ),
                source_reference="Stake sportsbook/help copy-share flow",
            ),
            "1xbet": BrowserPlaybook(
                bookmaker_slug="1xbet",
                restoration_mode="discover_current_flow",
                entry_url=None,
                public_restore=False,
                code_prompt=None,
                load_action=None,
                extraction_fields=DEFAULT_EXTRACTION_FIELDS,
                verified_on=None,
                verification_note=(
                    "No current public booking-code restoration flow has been verified for the configured 1xBet region. "
                    "OpenClaw must discover/verify the live public flow before using a code importer."
                ),
                source_reference=None,
            ),
        }

    def get(self, bookmaker_slug: str) -> BrowserPlaybook | None:
        return self._profiles.get((bookmaker_slug or "").casefold().strip())

    def all(self) -> tuple[BrowserPlaybook, ...]:
        return tuple(self._profiles[key] for key in sorted(self._profiles))
