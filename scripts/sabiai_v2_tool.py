#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, sys
from sabiai.config import Settings
from sabiai.openclaw import SabiToolGateway
from sabiai.storage import SabiDatabase

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--init-db", action="store_true")
    parser.add_argument("--request")
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
    result = SabiToolGateway(settings).dispatch(str(payload.get("tool", "")), payload.get("args") or {})
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0 if result.get("ok") else 1

if __name__ == "__main__":
    raise SystemExit(main())
