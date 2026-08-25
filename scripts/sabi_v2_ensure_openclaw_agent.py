#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENV_FILE = Path.home() / ".config" / "sabi-boy" / "sabi-boy.env"


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if key in os.environ or not key:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        os.environ[key] = os.path.expandvars(os.path.expanduser(value))


def run_json(command: list[str]) -> Any:
    proc = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        timeout=60,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"Command failed ({proc.returncode}): {shlex.join(command)}\n"
            f"stdout: {proc.stdout.strip()}\nstderr: {proc.stderr.strip()}"
        )
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Command did not return JSON: {shlex.join(command)}: {proc.stdout[:1000]}") from exc


def rows(payload: Any) -> list[dict]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("agents", "items", "entries", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
        return [payload]
    return []


def find_agent(payload: Any, agent_id: str) -> dict | None:
    for row in rows(payload):
        values = {
            str(row.get(key) or "").strip()
            for key in ("id", "agentId", "agent_id", "name", "slug")
        }
        if agent_id in values:
            return row
    return None


def workspace(row: dict) -> Path | None:
    for container in (row, row.get("config"), row.get("agent"), row.get("paths")):
        if not isinstance(container, dict):
            continue
        value = (
            container.get("workspace")
            or container.get("workspaceDir")
            or container.get("workspace_dir")
            or container.get("workspacePath")
            or container.get("workspace_path")
        )
        if isinstance(value, str) and value.strip():
            return Path(value).expanduser().resolve()
    return None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create Sabi's technical OpenClaw agent if missing, but never silently retarget an existing agent."
    )
    parser.add_argument("--env-file", default=str(DEFAULT_ENV_FILE))
    parser.add_argument("--report")
    args = parser.parse_args()

    load_env(Path(args.env_file).expanduser())
    binary = os.environ.get("OPENCLAW_BIN", "openclaw")
    agent_id = os.environ.get("SABIAI_OPENCLAW_AGENT_ID", "sabi-ai").strip() or "sabi-ai"
    expected = Path(os.environ.get("SABIAI_REPO_ROOT", str(ROOT))).expanduser().resolve()
    actual = ROOT.resolve()

    if expected != actual:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": f"SABIAI_REPO_ROOT is {expected}, but the executing checkout is {actual}.",
                },
                indent=2,
            )
        )
        return 2

    try:
        payload = run_json([binary, "agents", "list", "--json"])
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 3

    existing = find_agent(payload, agent_id)
    created = False
    if existing is not None:
        current_workspace = workspace(existing)
        if current_workspace != actual:
            result = {
                "ok": False,
                "agent_id": agent_id,
                "created": False,
                "workspace": str(current_workspace) if current_workspace else None,
                "expected_workspace": str(actual),
                "error": (
                    f"Existing OpenClaw agent '{agent_id}' does not point at this Sabi Boy V2 checkout. "
                    "Refusing to retarget it automatically."
                ),
            }
            print(json.dumps(result, indent=2))
            return 4
    else:
        try:
            run_json(
                [
                    binary,
                    "agents",
                    "add",
                    agent_id,
                    "--workspace",
                    str(actual),
                    "--non-interactive",
                    "--json",
                ]
            )
            created = True
            payload = run_json([binary, "agents", "list", "--json"])
            existing = find_agent(payload, agent_id)
        except Exception as exc:
            print(json.dumps({"ok": False, "agent_id": agent_id, "error": str(exc)}, indent=2))
            return 5
        if existing is None or workspace(existing) != actual:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "agent_id": agent_id,
                        "created": created,
                        "error": "OpenClaw reported agent creation, but the agent/workspace could not be verified afterwards.",
                    },
                    indent=2,
                )
            )
            return 6

    result = {
        "ok": True,
        "agent_id": agent_id,
        "created": created,
        "workspace": str(actual),
        "note": (
            "Created the technical OpenClaw agent at the Sabi Boy V2 workspace."
            if created
            else "Existing technical OpenClaw agent already points at the Sabi Boy V2 workspace; preserved it."
        ),
    }
    text = json.dumps(result, indent=2)
    if args.report:
        path = Path(args.report).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
