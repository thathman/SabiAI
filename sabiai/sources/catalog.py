from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from sabiai.config import Settings

from .betfair import BetfairExchangeAdapter
from .espn import EspnPublicAdapter
from .expansion import (
    ApiSportsAdapter,
    CricsheetAdapter,
    FastF1Adapter,
    JolpicaF1Adapter,
    NbaLiveDataAdapter,
    OpenLigaDBAdapter,
    PandaScoreAdapter,
    SportMonksAdapter,
    SportsDataIOAdapter,
    SportsGameOddsAdapter,
    StatsBombOpenDataAdapter,
)
from .football_data import FootballDataAdapter
from .parse_bot import ParseBotAdapter, SportsBettingAnalyzerAdapter
from .registry import Source, SourceCost, SourceKind, SourceRegistry
from .service import Fetcher
from .the_odds import TheOddsApiDiscoveryAdapter, TheOddsApiMarketsAdapter
from .thesportsdb import TheSportsDBAdapter


@dataclass(frozen=True)
class SourceBundle:
    registry: SourceRegistry
    fetchers: Mapping[str, Fetcher]


def default_source_bundle(settings: Settings) -> SourceBundle:
    """Build Sabi Boy's full source catalogue.

    Discovery and market pricing are separate concerns. Where a provider has free discovery
    but metered odds, it is registered as two sources so a broad fixture scan cannot spend
    market credits by accident.
    """

    registry = SourceRegistry()
    fetchers: dict[str, Fetcher] = {}

    sportsdb = TheSportsDBAdapter(api_key=settings.thesportsdb_key)
    registry.register(sportsdb.source)
    fetchers[sportsdb.name] = sportsdb.fetch

    espn = EspnPublicAdapter()
    registry.register(espn.source)
    fetchers[espn.name] = espn.fetch

    if settings.football_data_token:
        football_data = FootballDataAdapter(token=settings.football_data_token)
        registry.register(football_data.source)
        fetchers[football_data.name] = football_data.fetch

    if settings.parse_api_key:
        parse_sources = []
        if settings.parse_flashscore_scraper_id:
            parse_sources.append(
                ParseBotAdapter(
                    name="Parse · Flashscore",
                    api_key=settings.parse_api_key,
                    scraper_id=settings.parse_flashscore_scraper_id,
                    endpoints={
                        "search": "search",
                        "fixtures": "get_daily_fixtures",
                        "fixtures_with_odds": "get_fixtures_with_odds",
                        "live_scores": "get_live_scores",
                        "event_search": "get_match_detail",
                        "event_events": "get_match_events",
                        "event_stats": "get_match_statistics",
                        "stats": "get_match_statistics",
                        "league_table": "get_league_standings",
                        "lineup": "get_match_lineups",
                        "availability": "get_match_lineups",
                        "odds": "get_match_odds",
                        "preview": "get_match_preview",
                        "form": "get_team_results",
                    },
                    notes="Connected Flashscore Parse API using limited free Parse credits.",
                )
            )
        if settings.parse_livescore_scraper_id:
            parse_sources.append(
                ParseBotAdapter(
                    name="Parse · LiveScore",
                    api_key=settings.parse_api_key,
                    scraper_id=settings.parse_livescore_scraper_id,
                    endpoints={
                        "fixtures": "get_scores_by_date_and_sport",
                        "live_scores": "get_scores_by_date_and_sport",
                        "schedule": "get_league_fixtures",
                        "event_results": "get_league_results",
                        "league_table": "get_league_standings",
                        "event_stats": "get_match_summary",
                        "stats": "get_league_stats",
                        "team_profile": "get_team_overview",
                        "team_search": "search_teams_and_competitions",
                    },
                    sports={"football", "soccer"},
                    notes="Connected LiveScore Parse API using limited free Parse credits.",
                )
            )
        if settings.parse_sportybet_scraper_id:
            parse_sources.append(
                ParseBotAdapter(
                    name="Parse · SportyBet",
                    api_key=settings.parse_api_key,
                    scraper_id=settings.parse_sportybet_scraper_id,
                    endpoints={
                        "fixtures:football": "get_prematch_football_events",
                        "fixtures:soccer": "get_prematch_football_events",
                        "fixtures:basketball": "get_prematch_basketball_events",
                        "fixtures:ice_hockey": "get_prematch_ice_hockey_events",
                        "odds:football": "get_prematch_football_markets",
                        "odds:soccer": "get_prematch_football_markets",
                    },
                    sports={"football", "soccer", "basketball", "ice_hockey"},
                    notes=(
                        "Connected read-only SportyBet Parse API using limited free Parse credits. "
                        "The booking endpoint is deliberately excluded and Sabi Boy never places wagers."
                    ),
                )
            )
        if settings.parse_espn_scraper_id:
            parse_sources.append(
                ParseBotAdapter(
                    name="Parse · ESPN",
                    api_key=settings.parse_api_key,
                    scraper_id=settings.parse_espn_scraper_id,
                    endpoints={
                        "fixtures": "get_scoreboard",
                        "fixtures_with_odds": "get_scoreboard",
                        "league_table": "get_standings",
                        "team_search": "get_teams",
                        "team_profile": "get_team_roster",
                        "news": "get_news",
                        "search": "search",
                    },
                    notes="Connected ESPN Parse API using limited free Parse credits.",
                )
            )
        for adapter in parse_sources:
            registry.register(adapter.source)
            fetchers[adapter.name] = adapter.fetch

    if settings.the_odds_api_key:
        odds_discovery = TheOddsApiDiscoveryAdapter(api_key=settings.the_odds_api_key)
        registry.register(odds_discovery.source)
        fetchers[odds_discovery.name] = odds_discovery.fetch
        odds_markets = TheOddsApiMarketsAdapter(
            api_key=settings.the_odds_api_key,
            regions=settings.the_odds_regions,
        )
        registry.register(odds_markets.source)
        fetchers[odds_markets.name] = odds_markets.fetch

    if settings.betfair_app_key and settings.betfair_session_token:
        betfair = BetfairExchangeAdapter(
            app_key=settings.betfair_app_key,
            session_token=settings.betfair_session_token,
        )
        registry.register(betfair.source)
        fetchers[betfair.name] = betfair.fetch

    if settings.sports_betting_analyzer_api_key:
        analyzer = SportsBettingAnalyzerAdapter(api_key=settings.sports_betting_analyzer_api_key)
        registry.register(analyzer.source)
        fetchers[analyzer.name] = analyzer.fetch

    # V2.5 approved source expansion. Optional authenticated providers are still registered
    # when absent, with an explicit not_configured/disabled state in the source catalogue.
    _register_optional_keyed(
        registry,
        fetchers,
        key=settings.api_sports_key,
        adapter_cls=ApiSportsAdapter,
        name="API-Sports",
        sports={"football", "basketball", "baseball", "ice_hockey", "hockey", "volleyball", "handball", "rugby", "mma", "motorsport"},
        capabilities={"fixtures", "event_lookup", "teams", "players", "standings", "form", "stats", "injuries", "availability", "odds", "results"},
        notes="Metered/free-allowance API-Sports family; targeted enrichment only.",
        priority_bias=20,
    )
    _register_optional_keyed(
        registry,
        fetchers,
        key=settings.sportsgameodds_key,
        adapter_cls=SportsGameOddsAdapter,
        name="SportsGameOdds",
        sports={"football", "basketball", "baseball", "ice_hockey", "hockey", "tennis", "golf", "mma", "american_football"},
        capabilities={"fixtures", "event_lookup", "sport_catalog", "league_catalog", "market_catalog", "teams", "players", "usage", "odds", "results"},
        notes="SportsGameOdds v2 market sensor; never an action bookmaker.",
        priority_bias=30,
    )
    _register_optional_keyed(
        registry,
        fetchers,
        key=settings.pandascore_token,
        adapter_cls=PandaScoreAdapter,
        name="PandaScore",
        sports={"esports"},
        capabilities={"fixtures", "results", "event_lookup", "teams", "players", "tournaments", "leagues", "series", "standings", "rosters", "stats"},
        notes="Authenticated esports evidence specialist; no automatic action-book capability.",
        priority_bias=20,
        credential_arg="token",
    )
    _register_optional_keyed(
        registry,
        fetchers,
        key=settings.sportsdataio_key,
        adapter_cls=SportsDataIOAdapter,
        name="SportsDataIO",
        sports={"american_football", "basketball", "baseball", "ice_hockey", "football", "soccer"},
        capabilities={"fixtures", "results", "standings", "stats", "injuries", "availability", "players", "teams", "odds"},
        notes="Commercial targeted evidence source; disabled unless a credential and paid access are explicitly enabled.",
        priority_bias=35,
    )
    _register_optional_keyed(
        registry,
        fetchers,
        key=settings.sportmonks_token,
        adapter_cls=SportMonksAdapter,
        name="SportMonks",
        sports={"cricket", "motorsport", "football"},
        capabilities={"fixtures", "results", "standings", "teams", "players", "drivers", "venues", "seasons", "schedules", "live_scores"},
        notes="Authenticated cricket and Motorsport API v3 specialist; deprecated Formula One v1 is not used.",
        priority_bias=40,
        credential_arg="token",
    )

    # Public/open sources are always visible in the catalogue. Local datasets/dependencies
    # become enabled only when their runtime location/dependency is present.
    _register_local(registry, fetchers, FastF1Adapter(cache_dir=settings.fastf1_cache_dir))
    _register_local(registry, fetchers, CricsheetAdapter(data_dir=settings.cricsheet_dir))
    _register_local(registry, fetchers, StatsBombOpenDataAdapter(data_dir=settings.statsbomb_dir))
    for adapter in (JolpicaF1Adapter(), OpenLigaDBAdapter(), NbaLiveDataAdapter()):
        registry.register(adapter.source)
        fetchers[adapter.name] = adapter.fetch

    registry.register(
        Source(
            name="OpenClaw Browser",
            kind=SourceKind.BROWSER,
            cost=SourceCost.FREE,
            capabilities=set(),
            priority_bias=0,
            notes="Interactive public-web fallback executed by OpenClaw, not by the Python source client.",
        )
    )
    registry.register(
        Source(
            name="OpenClaw Search",
            kind=SourceKind.SEARCH,
            cost=SourceCost.FREE,
            capabilities=set(),
            priority_bias=0,
            notes="General source-discovery fallback executed by OpenClaw after direct public sources are insufficient.",
        )
    )

    return SourceBundle(registry=registry, fetchers=fetchers)


def _register_optional_keyed(
    registry: SourceRegistry,
    fetchers: dict[str, Fetcher],
    *,
    key: str | None,
    adapter_cls,
    name: str,
    sports: set[str],
    capabilities: set[str],
    notes: str,
    priority_bias: int,
    credential_arg: str = "api_key",
) -> None:
    if key and key.strip():
        adapter = adapter_cls(**{credential_arg: key})
        registry.register(adapter.source)
        fetchers[adapter.name] = adapter.fetch
        return
    registry.register(
        Source(
            name=name,
            kind=SourceKind.PAID_API,
            cost=SourceCost.PAID,
            sports=sports,
            capabilities=capabilities,
            enabled=False,
            health="not_configured",
            notes=notes,
            priority_bias=priority_bias,
        )
    )


def _register_local(registry: SourceRegistry, fetchers: dict[str, Fetcher], adapter) -> None:
    registry.register(adapter.source)
    fetchers[adapter.name] = adapter.fetch


def coverage_source_bundle(settings: Settings) -> SourceBundle:
    """Source bundle for the frequent no-model discovery radar.

    Parse-backed sources consume limited account credits even when the account is called
    "free-tier". They are therefore omitted from the 30-minute union unless the operator
    explicitly enables SABIAI_DISCOVERY_PARSE_UNION. This does not remove Parse from normal
    Sabi Boy/OpenClaw research or target-book verification.
    """

    bundle = default_source_bundle(settings)
    if settings.discovery_parse_union_enabled:
        return bundle
    return SourceBundle(
        registry=bundle.registry,
        fetchers={
            name: fetcher
            for name, fetcher in bundle.fetchers.items()
            if not name.startswith("Parse ·")
        },
    )
