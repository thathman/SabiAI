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

    @classmethod
    def from_env(cls) -> "Settings":
        repo_root = Path(
            os.getenv("SABIAI_REPO_ROOT", "~/.openclaw/workspace")
        ).expanduser()
        data_dir = Path(
            os.getenv("SABIAI_DATA_DIR", str(repo_root / "data"))
        ).expanduser()
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
        )


settings = Settings.from_env()
