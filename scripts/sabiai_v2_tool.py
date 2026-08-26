#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
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


DEFAULT_ENV_FILE = Path.home() / ".config" / "sabi-boy" / "sabi-boy.env"


def _load_env_file(path: Path) -> None:
    """Load the private runtime file without executing it as shell code.

    Existing process variables win so systemd, tests and deliberate one-off overrides keep
    their normal precedence. This also makes direct OpenClaw tool calls use the installed V2
    database instead of silently falling back to a legacy workspace path.
    """

    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key or key in os.environ:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        os.environ[key] = os.path.expandvars(os.path.expanduser(value))


def main() -> int:
    parser = argparse.ArgumentParser(description="Sabi Boy V2 OpenClaw tool bridge")
    parser.add_argument("--init-db", action="store_true")
    parser.add_argument(
        "--env-file",
        default=os.environ.get("SABIAI_ENV_FILE", str(DEFAULT_ENV_FILE)),
        help="Private Sabi Boy runtime environment file",
    )
    parser.add_argument("--request", help="JSON request; stdin is used when omitted")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON for manual debugging")
    args = parser.parse_args()

    _load_env_file(Path(args.env_file).expanduser())
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
