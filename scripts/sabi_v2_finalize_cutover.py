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

    # Local process must still be healthy.
    try:
        local_status, local = fetch_json("http://127.0.0.1:8091/health")
    except Exception as exc:
        print(f"Local Sabi Boy health failed: {exc}", file=sys.stderr)
        return 3
    if local_status != 200 or not local.get("ok") or local.get("product") != "Sabi Boy" or local.get("read_only") is not True:
        print(f"Unexpected local health response: {local}", file=sys.stderr)
        return 4

    # The caller supplies the actual external URL after inspecting/updating routing.
    try:
        external_status, external = fetch_json(args.health_url)
    except Exception as exc:
        print(f"External Sabi Boy health failed: {exc}", file=sys.stderr)
        return 5
    if external_status != 200 or not external.get("ok") or external.get("product") != "Sabi Boy" or external.get("read_only") is not True:
        print(f"External route does not resolve to Sabi Boy V2: {external}", file=sys.stderr)
        return 6

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
            return 7
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
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(state, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
