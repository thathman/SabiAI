#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sabiai.config import Settings
from sabiai.research import CoverageDiscoveryEngine
from sabiai.sources import coverage_source_bundle
from sabiai.storage import SabiDatabase


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Refresh Sabi Boy's deterministic event/market discovery radar without waking an LLM."
    )
    parser.add_argument("--horizon-hours", type=int, default=None)
    parser.add_argument(
        "--allow-metered",
        action="store_true",
        help="Allow configured quota-consuming market sensors. Runtime must also explicitly enable them.",
    )
    args = parser.parse_args()
    settings = Settings.from_env()
    if args.allow_metered and not settings.coverage_metered_markets_enabled:
        print(json.dumps({"ok": False, "error": "SABIAI_COVERAGE_METERED_MARKETS is disabled."}))
        return 2
    database = SabiDatabase(settings.v2_db)
    database.initialize()
    try:
        result = CoverageDiscoveryEngine(
            settings,
            database,
            bundle=coverage_source_bundle(settings),
        ).refresh(
            horizon_hours=args.horizon_hours,
            allow_metered=args.allow_metered,
        )
    except Exception as exc:
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:600]}"}))
        return 1
    print(json.dumps({"ok": True, **result.as_dict()}, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
