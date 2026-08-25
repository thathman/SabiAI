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


@dataclass(frozen=True, slots=True)
class BrowserBuildPlaybook:
    bookmaker_slug: str
    entry_url: str | None
    ready: bool
    build_mode: str
    event_navigation: str
    selection_action: str
    booking_action: str | None
    booking_code_field: str | None
    verification_tool: str
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
    visible controls described here, restore/read/search/build the sportsbook, and hand
    structured output to Sabi Boy's canonical validators. Build profiles authorize creating
    a reusable booking code only; they do not authorize wager placement or payment.
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
                    "SportyBet NG public Lite sportsbook currently exposes event rows, decimal prices and links to additional markets. "
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
                    "Stake's current official sportsbook exposes sports browsing/search and a bet slip; availability is region/account dependent and must be verified at runtime."
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

        self._build_profiles = {
            "sportybet": BrowserBuildPlaybook(
                bookmaker_slug="sportybet",
                entry_url="https://www.sportybet.com/ng/lite",
                ready=True,
                build_mode="public_booking_code",
                event_navigation=(
                    "For each verified leg, navigate to the exact sport/event and reopen the exact market/line/period from the fresh-price search."
                ),
                selection_action=(
                    "Click only the exact verified selection and confirm the betslip text/decimal price after every addition. "
                    "SportyBet also documents Football Bet Builder for supported same-event combinations; use it only when the requested ticket actually requires that structure."
                ),
                booking_action="Use the visible Book bet / booking-code action after every planned leg is present. Do not place the wager.",
                booking_code_field="Capture the generated SportyBet booking code and immediately reload it for verification.",
                verification_tool="bookmaker.build.verify",
                verified_on="2026-08-25",
                verification_note=(
                    "SportyBet's current public help documents selecting sportsbook outcomes into the betslip and generating a booking code with Book bet. "
                    "The public betslip warns that odds/availability can change, so reload the generated code and verify it before returning it."
                ),
            ),
            "bet9ja": BrowserBuildPlaybook(
                bookmaker_slug="bet9ja",
                entry_url="https://sports.bet9ja.com/",
                ready=True,
                build_mode="public_booking_number",
                event_navigation=(
                    "While logged out, navigate/search to each exact event and open the requested market. Match both participants and the exact line/period before adding a selection."
                ),
                selection_action=(
                    "Add only the exact verified selection to the Bet9ja betslip and confirm the visible selection text and decimal price after every addition."
                ),
                booking_action="Use Bet9ja's Book Bet / booking-number flow while logged out. Do not continue to payment or wager placement.",
                booking_code_field="Capture the generated Bet9ja booking number and immediately load it again for verification.",
                verification_tool="bookmaker.build.verify",
                verified_on="2026-08-25",
                verification_note=(
                    "Bet9ja's current official help documents logged-out market selection followed by Book Bet/booking-number creation. "
                    "Odds may change, so the generated booking number must be reloaded and structurally verified."
                ),
            ),
            "stake": BrowserBuildPlaybook(
                bookmaker_slug="stake",
                entry_url="https://stake.com/sports/home",
                ready=False,
                build_mode="discover_share_or_bet_code_creation",
                event_navigation="Use the verified market-search playbook only after regional/account availability is confirmed.",
                selection_action="Do not claim ticket-code creation until the current account/region visibly exposes a supported copy/share/bet-code creation action.",
                booking_action=None,
                booking_code_field=None,
                verification_tool="bookmaker.build.verify",
                verified_on="2026-08-25",
                verification_note=(
                    "Stake currently exposes Use Bet Code for restoration, but Sabi Boy has not yet verified a public unauthenticated code-creation flow suitable for the V2 builder."
                ),
            ),
            "1xbet": BrowserBuildPlaybook(
                bookmaker_slug="1xbet",
                entry_url=None,
                ready=False,
                build_mode="discover_current_flow",
                event_navigation="Not yet verified for the configured region.",
                selection_action="Do not automate building until the configured regional market and code-generation flow is verified.",
                booking_action=None,
                booking_code_field=None,
                verification_tool="bookmaker.build.verify",
                verified_on=None,
                verification_note="No verified V2 rich browser builder exists for the configured 1xBet region yet.",
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

    def browser_build(self, bookmaker_slug: str) -> BrowserBuildPlaybook | None:
        return self._build_profiles.get((bookmaker_slug or "").casefold().strip())

    def all_browser_build(self) -> tuple[BrowserBuildPlaybook, ...]:
        return tuple(self._build_profiles[key] for key in sorted(self._build_profiles))
