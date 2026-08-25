#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STATE = ROOT / "data" / "release" / "staging-latest.json"


def fetch_json(url: str) -> tuple[int, dict]:
    with urllib.request.urlopen(url, timeout=10) as response:
        payload = json.loads(response.read().decode("utf-8"))
        return int(response.status), payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Finalize Sabi Boy V2 only after the operator/OpenClaw has changed the real external routing. "
            "This command verifies that external route; it does not guess or edit Cloudflare configuration."
        )
    )
    parser.add_argument("--health-url", required=True, help="Externally routed Sabi Boy /health URL to verify.")
    parser.add_argument("--state", default=str(DEFAULT_STATE))
    parser.add_argument(
        "--stop-v1",
        action="store_true",
        help="After external verification succeeds, stop the legacy sabiai-dashboard.service.",
    )
    args = parser.parse_args()

    state_path = Path(args.state).expanduser()
    if not state_path.is_file():
        print(f"Missing staging state: {state_path}", file=sys.stderr)
        return 2
    state = json.loads(state_path.read_text(encoding="utf-8"))

    # Cutover is a commit-pinned release operation. If the checkout moved after staging,
    # re-stage/re-accept it instead of routing an unaccepted commit into production.
    current_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if current_commit.returncode != 0:
        print(current_commit.stderr.strip() or "Could not resolve current git commit.", file=sys.stderr)
        return 3
    current_sha = current_commit.stdout.strip()
    if state.get("commit") != current_sha:
        print(
            f"Checkout moved after staging: staged {state.get('commit')}, current {current_sha}. Re-stage before cutover.",
            file=sys.stderr,
        )
        return 4

    # The dashboard alone is not Sabi Boy V2. OpenClaw must also prove it is attached to this
    # workspace, sees the required current-format skills/tools, and has the V2 scheduled jobs.
    openclaw_state = state.get("openclaw")
    if not isinstance(openclaw_state, dict):
        print(
            "OpenClaw activation is missing from staging state. Run scripts/sabi_v2_activate_openclaw.sh first.",
            file=sys.stderr,
        )
        return 5
    if not openclaw_state.get("skills_verified") or not openclaw_state.get("automations_installed"):
        print(f"OpenClaw activation is incomplete: {openclaw_state}", file=sys.stderr)
        return 6
    openclaw_report_path = Path(str(openclaw_state.get("acceptance_report") or "")).expanduser()
    if not openclaw_report_path.is_file():
        print(f"OpenClaw acceptance report is missing: {openclaw_report_path}", file=sys.stderr)
        return 7
    openclaw_report = json.loads(openclaw_report_path.read_text(encoding="utf-8"))
    if not openclaw_report.get("ok"):
        print("OpenClaw acceptance report is not green.", file=sys.stderr)
        return 8

    # Local process must still be healthy.
    try:
        local_host = str(state.get("v2_host") or "127.0.0.1")
        local_port = int(state.get("v2_port") or 8091)
        local_status, local = fetch_json(f"http://{local_host}:{local_port}/health")
    except Exception as exc:
        print(f"Local Sabi Boy health failed: {exc}", file=sys.stderr)
        return 9
    if local_status != 200 or not local.get("ok") or local.get("product") != "Sabi Boy" or local.get("read_only") is not True:
        print(f"Unexpected local health response: {local}", file=sys.stderr)
        return 10

    # The caller supplies the actual external URL after inspecting/updating routing.
    try:
        external_status, external = fetch_json(args.health_url)
    except Exception as exc:
        print(f"External Sabi Boy health failed: {exc}", file=sys.stderr)
        return 11
    if external_status != 200 or not external.get("ok") or external.get("product") != "Sabi Boy" or external.get("read_only") is not True:
        print(f"External route does not resolve to Sabi Boy V2: {external}", file=sys.stderr)
        return 12

    v1_stopped = False
    if args.stop_v1:
        proc = subprocess.run(
            ["systemctl", "--user", "stop", "sabiai-dashboard.service"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        if proc.returncode != 0:
            print(proc.stdout, file=sys.stderr)
            return 13
        v1_stopped = True

    state.update(
        {
            "external_cutover_performed": True,
            "external_health_url": args.health_url,
            "external_health": external,
            "cutover_verified_at": datetime.now(timezone.utc).isoformat(),
            "v1_stopped": v1_stopped,
        }
    )
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(state, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
