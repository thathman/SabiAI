#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sabiai.config import Settings
from sabiai.ops import BackupService

DEFAULT_STATE = ROOT / "data" / "release" / "staging-latest.json"


def run_systemctl(*args: str) -> tuple[bool, str]:
    proc = subprocess.run(
        ["systemctl", "--user", *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    return proc.returncode == 0, proc.stdout.strip()


def _restore_timer(name: str, was_enabled: bool) -> tuple[bool, str]:
    if was_enabled:
        return run_systemctl("enable", "--now", name)
    return run_systemctl("disable", "--now", name)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Stop Sabi Boy V2 and restore the previous service/timer posture. External routing must also be reverted by the operator/OpenClaw."
    )
    parser.add_argument("--state", default=str(DEFAULT_STATE))
    parser.add_argument(
        "--restore-v2-database",
        action="store_true",
        help="Restore the pre-staging V2 database snapshot from the recorded backup manifest.",
    )
    args = parser.parse_args()

    settings = Settings.from_env()
    state_path = Path(args.state).expanduser()
    if not state_path.is_file():
        print(f"Missing staging state: {state_path}", file=sys.stderr)
        return 2
    state = json.loads(state_path.read_text(encoding="utf-8"))

    stopped, stop_output = run_systemctl("stop", "sabi-boy-dashboard.service")
    if not stopped:
        print(f"Warning: could not cleanly stop V2 service: {stop_output}", file=sys.stderr)

    # V2-only operational timers should not keep running after rollback. Preserve timers that
    # existed before staging, otherwise disable them. Coverage is included because it performs
    # deterministic network discovery even though it never wakes an LLM.
    timer_results: dict[str, dict] = {}
    timer_postures = {
        "sabi-boy-backup.timer": bool(state.get("backup_timer_was_enabled")),
        "sabi-boy-coverage.timer": bool(state.get("coverage_timer_was_enabled")),
    }
    for timer, was_enabled in timer_postures.items():
        ok, output = _restore_timer(timer, was_enabled)
        if not ok and "not loaded" not in output.casefold() and "does not exist" not in output.casefold():
            print(f"Warning: could not restore {timer} posture: {output}", file=sys.stderr)
        timer_results[timer] = {"restored": ok, "was_enabled": was_enabled}

    for timer in ("sabi-boy-settlement.timer", "sabi-boy-health.timer", "sabi-boy-research.timer"):
        ok, output = run_systemctl("disable", "--now", timer)
        if not ok and "not loaded" not in output.casefold() and "does not exist" not in output.casefold():
            print(f"Warning: could not disable {timer}: {output}", file=sys.stderr)
        timer_results[timer] = {"restored": ok, "was_enabled": False}

    v1_restarted = False
    if state.get("v1_service_was_active"):
        started, output = run_systemctl("start", "sabiai-dashboard.service")
        if not started:
            print(f"Could not restore V1 service: {output}", file=sys.stderr)
            return 3
        v1_restarted = True

    restored = None
    if args.restore_v2_database:
        manifest = state.get("backup_manifest")
        if not manifest:
            print("Staging state has no backup manifest; refusing V2 DB restore.", file=sys.stderr)
            return 4
        restored = BackupService().restore(
            manifest,
            label="v2",
            destination=settings.v2_db,
            overwrite=True,
        )

    rollback = {
        "product": "Sabi Boy",
        "rolled_back_at": datetime.now(timezone.utc).isoformat(),
        "v2_service_stopped": stopped,
        "timer_posture": timer_results,
        "v1_restarted": v1_restarted,
        "v2_database_restored": restored,
        "external_routing_requires_revert": bool(state.get("external_cutover_performed")),
        "previous_external_health_url": state.get("external_health_url"),
    }
    state["last_rollback"] = rollback
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(rollback, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
