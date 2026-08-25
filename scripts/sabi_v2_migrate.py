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
from sabiai.migration import V1Migrator


def main() -> int:
    settings = Settings.from_env()
    parser = argparse.ArgumentParser(
        description="Analyze or migrate the SabiAI V1 database into Sabi Boy V2. V1 is opened read-only."
    )
    parser.add_argument("--source", default=str(settings.legacy_bets_db))
    parser.add_argument("--target", default=str(settings.v2_db))
    parser.add_argument(
        "--analyze-only",
        action="store_true",
        help="Inspect source tables/counts without writing V2 data.",
    )
    parser.add_argument(
        "--require-ready",
        action="store_true",
        help="Exit non-zero unless migration reconciliation is fully ready.",
    )
    args = parser.parse_args()

    migrator = V1Migrator(args.source, args.target)
    report = migrator.analyze() if args.analyze_only else migrator.migrate()
    print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2, default=str))

    if report.blockers:
        return 2
    if args.require_ready and not report.ready:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
