#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

# Make the repository package importable even when this script is launched from
# another working directory by OpenClaw/systemd/manual shell use.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sabiai.config import Settings
from sabiai.openclaw import SabiToolGateway
from sabiai.storage import SabiDatabase


def main() -> int:
    parser = argparse.ArgumentParser(description="Sabi Boy V2 OpenClaw tool bridge")
    parser.add_argument("--init-db", action="store_true")
    parser.add_argument("--request", help="JSON request; stdin is used when omitted")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON for manual debugging")
    args = parser.parse_args()

    settings = Settings.from_env()
    if args.init_db:
        SabiDatabase(settings.v2_db).initialize()

    text = args.request if args.request is not None else sys.stdin.read()
    if not text.strip():
        print(json.dumps({"ok": False, "error": "No request supplied."}))
        return 2

    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        print(json.dumps({"ok": False, "error": f"Invalid JSON: {exc}"}))
        return 2

    if not isinstance(payload, dict):
        print(json.dumps({"ok": False, "error": "Request must be one JSON object."}))
        return 2

    result = SabiToolGateway(settings).dispatch(
        str(payload.get("tool", "")),
        payload.get("args") or {},
    )
    if args.pretty:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
