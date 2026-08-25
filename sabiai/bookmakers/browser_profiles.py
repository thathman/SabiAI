from __future__ import annotations

from dataclasses import dataclass


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


@dataclass(frozen=True, slots=True)
class MarketSearchPlaybook:
    bookmaker_slug: str
    entry_url: str | None
    ready: bool
    search_method: str
    event_navigation: str
    market_navigation: str
    odds_format: str
    extraction_fields: tuple[str, ...]
    verified_on: str | None
    verification_note: str


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

MARKET_SEARCH_FIELDS = (
    "sport",
    "competition",
    "event",
    "home",
    "away",
    "event_ref",
    "market",
    "selection",
    "market_ref",
    "decimal_odds",
    "observed_at",
)


class BookmakerBrowserProfiles:
    """Human-readable browser playbooks for OpenClaw.

    These are intentionally not brittle DOM selectors. OpenClaw/browser should locate the
    visible controls described here, restore/read/search the sportsbook, and hand structured
    output to Sabi Boy's canonical validators. No profile authorizes wager placement.
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

        self._search_profiles = {
            "sportybet": MarketSearchPlaybook(
                bookmaker_slug="sportybet",
                entry_url="https://www.sportybet.com/ng/lite",
                ready=True,
                search_method=(
                    "Use the public Sports/Lite event listing and visible sport/category/tournament navigation. "
                    "Match both participant names; open the event when the requested market is not shown in the event row."
                ),
                event_navigation="Sport → competition/tournament → exact event; verify both home and away participants before reading a market.",
                market_navigation="Open the event's full market list, then locate the exact requested market, line and period.",
                odds_format="decimal",
                extraction_fields=MARKET_SEARCH_FIELDS,
                verified_on="2026-08-25",
                verification_note=(
                    "SportyBet NG public Lite sportsbook currently exposes event rows, 1/X/2 decimal prices and links to many additional markets. "
                    "Market availability and prices are live data and must be re-read at search time."
                ),
            ),
            "bet9ja": MarketSearchPlaybook(
                bookmaker_slug="bet9ja",
                entry_url="https://sports.bet9ja.com/",
                ready=True,
                search_method=(
                    "Use the public sportsbook sport/competition pages and visible event listing. Search or navigate to the competition, "
                    "then match both participant names before opening the event/markets."
                ),
                event_navigation="Sport → competition/league → exact event; never identify an event from one team name alone.",
                market_navigation="Open the event market view and locate the exact market label, line, period and selection; retain event/market references when visible.",
                odds_format="decimal",
                extraction_fields=MARKET_SEARCH_FIELDS,
                verified_on="2026-08-25",
                verification_note=(
                    "The existing Sabi Bet9ja browser integration uses the current public sportsbook root at sports.bet9ja.com. "
                    "Do not reuse its old hard-coded league guesses as authoritative market discovery; inspect the live page instead."
                ),
            ),
            "stake": MarketSearchPlaybook(
                bookmaker_slug="stake",
                entry_url="https://stake.com/sports/home",
                ready=True,
                search_method=(
                    "Use Stake Sportsbook's current sports menu or search bar to find the exact team/event, then open the event. "
                    "If region/account restrictions hide an event, report it unavailable rather than substituting another region or market."
                ),
                event_navigation="Search exact participants or browse Sport → competition → event; verify both participants and event date/context.",
                market_navigation="Open the event and locate the exact market/line/period; set/read decimal odds rather than converting American prices.",
                odds_format="decimal",
                extraction_fields=MARKET_SEARCH_FIELDS,
                verified_on="2026-08-25",
                verification_note=(
                    "Stake's current official sportsbook describes a search bar plus live/upcoming event browsing and supports decimal odds. "
                    "Availability is region/account dependent and must be verified at runtime."
                ),
            ),
            "1xbet": MarketSearchPlaybook(
                bookmaker_slug="1xbet",
                entry_url=None,
                ready=False,
                search_method="Discover and verify the configured regional sportsbook entry/search flow before automating market discovery.",
                event_navigation="Not yet verified for the configured region.",
                market_navigation="Not yet verified for the configured region.",
                odds_format="decimal",
                extraction_fields=MARKET_SEARCH_FIELDS,
                verified_on=None,
                verification_note=(
                    "Sabi Boy knows 1xBet as a bookmaker but does not yet claim a verified V2 public market-search playbook for the configured region."
                ),
            ),
        }

    def get(self, bookmaker_slug: str) -> BrowserPlaybook | None:
        return self._profiles.get((bookmaker_slug or "").casefold().strip())

    def all(self) -> tuple[BrowserPlaybook, ...]:
        return tuple(self._profiles[key] for key in sorted(self._profiles))

    def market_search(self, bookmaker_slug: str) -> MarketSearchPlaybook | None:
        return self._search_profiles.get((bookmaker_slug or "").casefold().strip())

    def all_market_search(self) -> tuple[MarketSearchPlaybook, ...]:
        return tuple(self._search_profiles[key] for key in sorted(self._search_profiles))
