#!/usr/bin/env python3
"""Deterministic local acceptance for the V2.5 intelligence-engine contract.

This script deliberately does not call a model, a bookmaker, or a metered source. It checks
the installed code, schema, gateway surface, pricing math, and recovery planner only.
"""

from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
REQUIRED_TOOLS = (
    "engine.completeness",
    "engine.sport_profile",
    "engine.next_actions",
    "engine.price.assess",
    "engine.evidence.build",
    "engine.calibration",
)


def _git_sha() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def run(db_path: Path | None = None) -> dict:
    from sabiai.config import Settings
    from sabiai.openclaw import SabiToolGateway
    from sabiai.research import EngineCompletenessService, EngineGapPlanner
    from sabiai.sports import engine_sport_profiles
    from sabiai.storage import SabiDatabase

    settings = replace(Settings.from_env(), repo_root=REPO_ROOT)
    if db_path is not None:
        settings = replace(settings, v2_db=db_path)
    database = SabiDatabase(settings.v2_db)
    database.initialize()

    checks: list[dict] = []

    profiles = engine_sport_profiles()
    checks.append({
        "name": "31 proactive sport profiles",
        "ok": len(profiles) == 31 and all(profile.slug for profile in profiles),
        "detail": f"{len(profiles)} first-class profiles",
    })

    completeness = EngineCompletenessService(settings, database).inspect()
    checks.append({
        "name": "engine completeness",
        "ok": completeness["engine_code_complete"] and not completeness["missing_contracts"],
        "detail": completeness["label"],
        "data": completeness,
    })

    gateway = SabiToolGateway(settings)
    available = set(gateway.list_tools()["tools"])
    missing_tools = [name for name in REQUIRED_TOOLS if name not in available]
    checks.append({
        "name": "V2.5 gateway tools",
        "ok": not missing_tools,
        "detail": "all six engine tools exposed" if not missing_tools else f"missing: {', '.join(missing_tools)}",
    })

    price = gateway.dispatch(
        "engine.price.assess",
        {"estimated_probability_pct": 60, "decimal_odds": 2.0, "confidence_pct": 60},
    )
    checks.append({
        "name": "exact price assessment",
        "ok": bool(price.get("ok")) and price.get("data", {}).get("expected_value_pct") == 20.0,
        "detail": "60% at 2.00 produces +20.00% expected value",
        "data": price.get("data"),
    })

    gap = EngineGapPlanner(settings).plan({"sport": "horse_racing", "event": "Acceptance Stakes"})
    checks.append({
        "name": "actionable degradation planner",
        "ok": gap.get("next_action", {}).get("code") == "event_not_canonical",
        "detail": gap.get("next_action", {}).get("code") or "no next action",
        "data": gap,
    })

    checks.append({
        "name": "decision-context schema",
        "ok": database.schema_version() is not None and database.schema_version() >= 18,
        "detail": f"schema version {database.schema_version()}",
    })

    ok = all(check["ok"] for check in checks)
    return {
        "ok": ok,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "commit": _git_sha(),
        "database": str(settings.v2_db),
        "checks": checks,
        "note": "Deterministic acceptance only; live source coverage and Dell timers require a separate controlled run.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, help="Use an isolated V2 database for the checks.")
    args = parser.parse_args(argv)
    try:
        result = run(args.db)
    except Exception as exc:  # pragma: no cover - command-line failure formatting
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, indent=2))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
