from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().casefold() not in {"0", "false", "no", "off", "disabled"}


@dataclass(frozen=True)
class Settings:
    """Runtime settings with safe local defaults.

    Secrets are read from environment variables only. They are never embedded in source.
    V2.4 separates cheap discovery from expensive analysis so a large event universe does not
    imply a large model/API bill.
    """

    repo_root: Path
    data_dir: Path
    legacy_bets_db: Path
    v2_db: Path
    timezone: str
    paid_sources_enabled: bool
    football_data_token: str | None = None
    thesportsdb_key: str = "123"
    vapid_public_key: str | None = None
    vapid_private_key_file: Path | None = None
    vapid_subject: str = "https://picks.hendrix.com.ng"
    dashboard_allowed_origins: tuple[str, ...] = (
        "https://picks.hendrix.com.ng",
        "http://127.0.0.1:8090",
        "http://127.0.0.1:8091",
        "http://localhost:8090",
        "http://localhost:8091",
        "http://testserver",
    )
    parse_api_key: str | None = None
    parse_flashscore_scraper_id: str | None = None
    parse_livescore_scraper_id: str | None = None
    parse_sportybet_scraper_id: str | None = None
    parse_espn_scraper_id: str | None = None
    sports_betting_analyzer_api_key: str | None = None
    the_odds_api_key: str | None = None
    the_odds_regions: str = "uk,eu"
    betfair_app_key: str | None = None
    betfair_session_token: str | None = None
    research_api_key: str | None = None
    research_api_base_url: str = "https://token-plan.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1"
    research_model: str = "qwen3.8-max-preview"
    research_fallback_model: str | None = None
    research_fallback_api_key: str | None = None
    research_fallback_api_base_url: str | None = None
    research_sports: tuple[str, ...] = (
        "football", "basketball", "volleyball", "tennis", "table_tennis", "baseball",
        "ice_hockey", "cricket", "golf", "handball", "rugby", "darts", "snooker",
        "badminton", "mma", "boxing", "motorsport", "cycling", "futsal", "water_polo",
        "beach_volleyball", "padel", "floorball", "aussie_rules", "esports",
        "american_football", "horse_racing", "greyhound_racing", "rugby_league",
        "athletics", "winter_sports",
    )
    research_max_events: int = 120
    research_max_events_per_sport: int = 40
    research_slice_workers: int = 4
    research_slice_ttl_seconds: int = 86400
    research_max_recommendations: int = 18
    discovery_horizon_hours: int = 72
    discovery_long_horizon_hours: int = 168
    discovery_event_horizon_hours: int = 336
    discovery_max_events: int = 2000
    discovery_max_source_requests: int = 300
    discovery_source_ttl_seconds: int = 3600
    discovery_refresh_minutes: int = 30
    discovery_parse_union_enabled: bool = False
    prefilter_max_events: int = 300
    market_inventory_max_offers: int = 5000
    market_refresh_seconds: int = 1800
    market_history_keep_days: int = 21
    action_price_enrichment_enabled: bool = True
    action_price_max_events_per_sport: int = 1000
    coverage_metered_markets_enabled: bool = False
    coverage_metered_sport_limit: int = 12
    coverage_deep_markets_enabled: bool = False
    coverage_deep_market_event_limit: int = 20
    coverage_deep_market_key_limit: int = 12
    the_odds_max_leagues_per_sport: int = 30
    betfair_max_markets_per_sport: int = 500
    betfair_prices_enabled: bool = True

    @classmethod
    def from_env(cls) -> "Settings":
        repo_root = Path(os.getenv("SABIAI_REPO_ROOT", "~/.openclaw/workspace")).expanduser()
        data_dir = Path(os.getenv("SABIAI_DATA_DIR", str(repo_root / "data"))).expanduser()
        football_data_token = os.getenv("FOOTBALL_DATA_API_TOKEN") or os.getenv("SABIAI_FOOTBALL_DATA_TOKEN")
        private_key = os.getenv("SABIAI_VAPID_PRIVATE_KEY_FILE")
        origins = tuple(
            origin.strip().rstrip("/")
            for origin in os.getenv(
                "SABIAI_DASHBOARD_ALLOWED_ORIGINS",
                "https://picks.hendrix.com.ng,http://127.0.0.1:8090,http://127.0.0.1:8091,"
                "http://localhost:8090,http://localhost:8091,http://testserver",
            ).split(",")
            if origin.strip()
        )
        return cls(
            repo_root=repo_root,
            data_dir=data_dir,
            legacy_bets_db=Path(os.getenv("SABIAI_LEGACY_DB", str(data_dir / "bets.db"))).expanduser(),
            v2_db=Path(os.getenv("SABIAI_V2_DB", str(data_dir / "sabiai_v2_core.db"))).expanduser(),
            timezone=os.getenv("SABIAI_TIMEZONE", "Africa/Lagos"),
            paid_sources_enabled=_env_bool("SABIAI_PAID_SOURCES", True),
            football_data_token=football_data_token.strip() if football_data_token and football_data_token.strip() else None,
            thesportsdb_key=os.getenv("SABIAI_THESPORTSDB_KEY", "123").strip() or "123",
            vapid_public_key=(os.getenv("SABIAI_VAPID_PUBLIC_KEY") or "").strip() or None,
            vapid_private_key_file=Path(private_key).expanduser() if private_key and private_key.strip() else None,
            vapid_subject=os.getenv("SABIAI_VAPID_SUBJECT", "https://picks.hendrix.com.ng").strip() or "https://picks.hendrix.com.ng",
            dashboard_allowed_origins=origins,
            parse_api_key=(os.getenv("SABIAI_PARSE_API_KEY") or "").strip() or None,
            parse_flashscore_scraper_id=(os.getenv("SABIAI_PARSE_FLASHSCORE_SCRAPER_ID") or "").strip() or None,
            parse_livescore_scraper_id=(os.getenv("SABIAI_PARSE_LIVESCORE_SCRAPER_ID") or "").strip() or None,
            parse_sportybet_scraper_id=(os.getenv("SABIAI_PARSE_SPORTYBET_SCRAPER_ID") or "").strip() or None,
            parse_espn_scraper_id=(os.getenv("SABIAI_PARSE_ESPN_SCRAPER_ID") or "").strip() or None,
            sports_betting_analyzer_api_key=(os.getenv("SABIAI_SPORTS_BETTING_ANALYZER_API_KEY") or os.getenv("SBMA_API_KEY") or "").strip() or None,
            the_odds_api_key=(os.getenv("SABIAI_THE_ODDS_API_KEY") or os.getenv("THE_ODDS_API_KEY") or "").strip() or None,
            the_odds_regions=os.getenv("SABIAI_THE_ODDS_REGIONS", "uk,eu").strip() or "uk,eu",
            betfair_app_key=(os.getenv("SABIAI_BETFAIR_APP_KEY") or "").strip() or None,
            betfair_session_token=(os.getenv("SABIAI_BETFAIR_SESSION_TOKEN") or "").strip() or None,
            research_api_key=(os.getenv("SABIAI_RESEARCH_API_KEY") or os.getenv("ALIYUN_TOKEN_PLAN_COMPATIBLE_KEY") or "").strip() or None,
            research_api_base_url=(os.getenv("SABIAI_RESEARCH_API_BASE_URL", "https://token-plan.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1").strip().rstrip("/") or "https://token-plan.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1"),
            research_model=os.getenv("SABIAI_RESEARCH_MODEL", "qwen3.8-max-preview").strip() or "qwen3.8-max-preview",
            research_fallback_model=os.getenv("SABIAI_RESEARCH_FALLBACK_MODEL", "qwen3.6-flash").strip() or "qwen3.6-flash",
            research_fallback_api_key=(os.getenv("SABIAI_RESEARCH_FALLBACK_API_KEY") or os.getenv("SABIAI_RESEARCH_API_KEY") or os.getenv("ALIYUN_TOKEN_PLAN_COMPATIBLE_KEY") or "").strip() or None,
            research_fallback_api_base_url=((os.getenv("SABIAI_RESEARCH_FALLBACK_API_BASE_URL") or os.getenv("SABIAI_RESEARCH_API_BASE_URL", "https://token-plan.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1")).strip().rstrip("/") or None),
            research_sports=tuple(
                item.strip()
                for item in os.getenv(
                    "SABIAI_RESEARCH_SPORTS",
                    "football,basketball,volleyball,tennis,table_tennis,baseball,ice_hockey,cricket,golf,handball,rugby,darts,snooker,badminton,mma,boxing,motorsport,cycling,futsal,water_polo,beach_volleyball,padel,floorball,aussie_rules,esports,american_football,horse_racing,greyhound_racing,rugby_league,athletics,winter_sports",
                ).split(",") if item.strip()
            ) or cls.research_sports,
            research_max_events=max(1, int(os.getenv("SABIAI_RESEARCH_MAX_EVENTS", "120"))),
            research_max_events_per_sport=max(1, int(os.getenv("SABIAI_RESEARCH_MAX_EVENTS_PER_SPORT", "40"))),
            research_slice_workers=max(1, min(int(os.getenv("SABIAI_RESEARCH_SLICE_WORKERS", "4")), 12)),
            research_slice_ttl_seconds=max(300, int(os.getenv("SABIAI_RESEARCH_SLICE_TTL_SECONDS", "86400"))),
            research_max_recommendations=max(1, min(int(os.getenv("SABIAI_RESEARCH_MAX_RECOMMENDATIONS", "18")), 100)),
            discovery_horizon_hours=max(24, int(os.getenv("SABIAI_DISCOVERY_HORIZON_HOURS", "72"))),
            discovery_long_horizon_hours=max(72, int(os.getenv("SABIAI_DISCOVERY_LONG_HORIZON_HOURS", "168"))),
            discovery_event_horizon_hours=max(168, int(os.getenv("SABIAI_DISCOVERY_EVENT_HORIZON_HOURS", "336"))),
            discovery_max_events=max(100, int(os.getenv("SABIAI_DISCOVERY_MAX_EVENTS", "2000"))),
            discovery_max_source_requests=max(10, int(os.getenv("SABIAI_DISCOVERY_MAX_SOURCE_REQUESTS", "300"))),
            discovery_source_ttl_seconds=max(300, int(os.getenv("SABIAI_DISCOVERY_SOURCE_TTL_SECONDS", "3600"))),
            discovery_refresh_minutes=max(10, int(os.getenv("SABIAI_DISCOVERY_REFRESH_MINUTES", "30"))),
            discovery_parse_union_enabled=_env_bool("SABIAI_DISCOVERY_PARSE_UNION", False),
            prefilter_max_events=max(20, int(os.getenv("SABIAI_PREFILTER_MAX_EVENTS", "300"))),
            market_inventory_max_offers=max(100, int(os.getenv("SABIAI_MARKET_INVENTORY_MAX_OFFERS", "5000"))),
            market_refresh_seconds=max(120, int(os.getenv("SABIAI_MARKET_REFRESH_SECONDS", "1800"))),
            market_history_keep_days=max(7, int(os.getenv("SABIAI_MARKET_HISTORY_KEEP_DAYS", "21"))),
            action_price_enrichment_enabled=_env_bool("SABIAI_ACTION_PRICE_ENRICHMENT", True),
            action_price_max_events_per_sport=max(1, int(os.getenv("SABIAI_ACTION_PRICE_MAX_EVENTS_PER_SPORT", "1000"))),
            coverage_metered_markets_enabled=_env_bool("SABIAI_COVERAGE_METERED_MARKETS", False),
            coverage_metered_sport_limit=max(1, int(os.getenv("SABIAI_COVERAGE_METERED_SPORT_LIMIT", "12"))),
            coverage_deep_markets_enabled=_env_bool("SABIAI_COVERAGE_DEEP_MARKETS", False),
            coverage_deep_market_event_limit=max(1, int(os.getenv("SABIAI_COVERAGE_DEEP_MARKET_EVENT_LIMIT", "20"))),
            coverage_deep_market_key_limit=max(1, int(os.getenv("SABIAI_COVERAGE_DEEP_MARKET_KEY_LIMIT", "12"))),
            the_odds_max_leagues_per_sport=max(1, int(os.getenv("SABIAI_THE_ODDS_MAX_LEAGUES_PER_SPORT", "30"))),
            betfair_max_markets_per_sport=max(10, min(int(os.getenv("SABIAI_BETFAIR_MAX_MARKETS_PER_SPORT", "500")), 1000)),
            betfair_prices_enabled=_env_bool("SABIAI_BETFAIR_PRICES", True),
        )


settings = Settings.from_env()
