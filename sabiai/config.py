from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os


@dataclass(frozen=True)
class Settings:
    """Runtime settings with safe local defaults.

    Secrets are read from environment variables only. They are never embedded in source.
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

    @classmethod
    def from_env(cls) -> "Settings":
        repo_root = Path(
            os.getenv("SABIAI_REPO_ROOT", "~/.openclaw/workspace")
        ).expanduser()
        data_dir = Path(
            os.getenv("SABIAI_DATA_DIR", str(repo_root / "data"))
        ).expanduser()
        football_data_token = os.getenv("FOOTBALL_DATA_API_TOKEN") or os.getenv(
            "SABIAI_FOOTBALL_DATA_TOKEN"
        )
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
            legacy_bets_db=Path(
                os.getenv("SABIAI_LEGACY_DB", str(data_dir / "bets.db"))
            ).expanduser(),
            v2_db=Path(
                os.getenv("SABIAI_V2_DB", str(data_dir / "sabiai_v2_core.db"))
            ).expanduser(),
            timezone=os.getenv("SABIAI_TIMEZONE", "Africa/Lagos"),
            paid_sources_enabled=os.getenv("SABIAI_PAID_SOURCES", "1").strip().lower()
            not in {"0", "false", "no", "off"},
            football_data_token=football_data_token.strip()
            if football_data_token and football_data_token.strip()
            else None,
            thesportsdb_key=os.getenv("SABIAI_THESPORTSDB_KEY", "123").strip() or "123",
            vapid_public_key=(os.getenv("SABIAI_VAPID_PUBLIC_KEY") or "").strip() or None,
            vapid_private_key_file=Path(private_key).expanduser()
            if private_key and private_key.strip()
            else None,
            vapid_subject=os.getenv(
                "SABIAI_VAPID_SUBJECT", "https://picks.hendrix.com.ng"
            ).strip()
            or "https://picks.hendrix.com.ng",
            dashboard_allowed_origins=origins,
            parse_api_key=(os.getenv("SABIAI_PARSE_API_KEY") or "").strip() or None,
            parse_flashscore_scraper_id=(
                os.getenv("SABIAI_PARSE_FLASHSCORE_SCRAPER_ID") or ""
            ).strip()
            or None,
            parse_livescore_scraper_id=(
                os.getenv("SABIAI_PARSE_LIVESCORE_SCRAPER_ID") or ""
            ).strip()
            or None,
            parse_sportybet_scraper_id=(
                os.getenv("SABIAI_PARSE_SPORTYBET_SCRAPER_ID") or ""
            ).strip()
            or None,
            parse_espn_scraper_id=(
                os.getenv("SABIAI_PARSE_ESPN_SCRAPER_ID") or ""
            ).strip()
            or None,
            sports_betting_analyzer_api_key=(
                os.getenv("SABIAI_SPORTS_BETTING_ANALYZER_API_KEY")
                or os.getenv("SBMA_API_KEY")
                or ""
            ).strip()
            or None,
        )


settings = Settings.from_env()
