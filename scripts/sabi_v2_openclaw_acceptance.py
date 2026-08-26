#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shlex
import subprocess
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENV_FILE = Path.home() / ".config" / "sabi-boy" / "sabi-boy.env"
REQUIRED_SKILLS = (
    "sabi-boy-core",
    "sabi-boy-bookmaker-workflows",
    "sabi-boy-research-scout",
    "sabi-boy-skeptic",
    "sabi-boy-ticket-engineer",
    "sabi-boy-records",
    "sabi-boy-blog",
)
REQUIRED_TOOLS = (
    "system.tools",
    "system.readiness",
    "system.jobs.failure",
    "source.discovery.plan",
    "source.discovery.verify",
    "sports.match_snapshot",
    "research.evidence.ingest",
    "research.case.create",
    "research.case.attach",
    "research.case.summary",
    "ticket.research.plan",
    "ticket.draft.lineage",
    "ticket.higher_odds.from_verified_offers",
    "ticket.candidates.compare",
    "market.settlement.profile",
    "bookmaker.compare.plan",
    "bookmaker.compare.from_search",
    "bookmaker.convert.from_search",
    "bookmaker.browser_build.plan",
    "bookmaker.build.verify",
    "bookmaker.browser_health",
    "history.ticket_versions",
    "history.bookmaker_prices",
    "history.price_disagreements",
    "blog.reflection.context",
    "blog.triggers",
)


@dataclass
class Check:
    name: str
    ok: bool
    detail: str
    data: Any = None


class AcceptanceError(RuntimeError):
    pass


def _load_env_file(path: Path) -> None:
    """Load the simple KEY=VALUE runtime file without executing shell code."""
    if not path.exists():
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


def _run(command: list[str], *, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def _json_from_process(proc: subprocess.CompletedProcess[str], command: list[str]) -> Any:
    """Parse CLI JSON, with a narrow fallback for older OpenClaw stderr regressions.

    Some historical OpenClaw builds routed `skills ... --json` output through stderr even on
    success. Prefer stdout. If stdout is empty, accept stderr only when the *entire* stderr
    payload is valid JSON. Ordinary warnings/errors therefore never become a false green.
    """
    if proc.returncode != 0:
        raise AcceptanceError(
            f"Command failed ({proc.returncode}): {shlex.join(command)}\n"
            f"stdout: {proc.stdout.strip()}\nstderr: {proc.stderr.strip()}"
        )
    candidates = []
    if proc.stdout.strip():
        candidates.append(("stdout", proc.stdout.strip()))
    elif proc.stderr.strip():
        candidates.append(("stderr", proc.stderr.strip()))
    if not candidates:
        raise AcceptanceError(f"Command returned no JSON: {shlex.join(command)}")

    location, text = candidates[0]
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise AcceptanceError(
            f"Command did not return valid JSON on {location}: {shlex.join(command)}: {exc}\n{text[:1000]}"
        ) from exc


def _json_command(command: list[str], *, timeout: int = 60) -> Any:
    return _json_from_process(_run(command, timeout=timeout), command)


def _rows(payload: Any, keys: tuple[str, ...]) -> list[dict]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in keys:
            value = payload.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
        return [payload]
    return []


def _find_agent(payload: Any, wanted: str) -> dict | None:
    for row in _rows(payload, ("agents", "items", "entries", "data")):
        identifiers = {
            str(row.get(key) or "").strip()
            for key in ("id", "agentId", "agent_id", "name", "slug")
        }
        if wanted in identifiers:
            return row
    return None


def _workspace_from_agent(row: dict) -> str | None:
    direct = (
        row.get("workspace")
        or row.get("workspaceDir")
        or row.get("workspace_dir")
        or row.get("workspacePath")
        or row.get("workspace_path")
    )
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    for key in ("config", "agent", "paths"):
        nested = row.get(key)
        if not isinstance(nested, dict):
            continue
        value = (
            nested.get("workspace")
            or nested.get("workspaceDir")
            or nested.get("workspace_dir")
            or nested.get("workspacePath")
            or nested.get("workspace_path")
        )
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _skill_names(payload: Any) -> set[str]:
    found: set[str] = set()

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key in {"name", "slug", "skill", "skillName", "skill_name"} and isinstance(item, str):
                    found.add(item.strip())
                elif key in {"skills", "ready", "eligible", "items", "entries", "data"}:
                    walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(payload)
    return {name for name in found if name}


def _gateway_request(python_bin: Path, tool: str, args: dict | None = None) -> dict:
    request = json.dumps({"tool": tool, "args": args or {}}, separators=(",", ":"))
    proc = _run(
        [str(python_bin), str(REPO_ROOT / "scripts" / "sabiai_v2_tool.py"), "--request", request],
        timeout=90,
    )
    if proc.returncode != 0:
        raise AcceptanceError(
            f"Sabi Boy gateway request failed for {tool}: {proc.stderr.strip() or proc.stdout.strip()}"
        )
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise AcceptanceError(f"Sabi Boy gateway returned invalid JSON for {tool}: {proc.stdout[:1000]}") from exc
    if not isinstance(payload, dict) or not payload.get("ok"):
        raise AcceptanceError(f"Sabi Boy gateway rejected {tool}: {payload}")
    return payload


def _check_local_skill_packages() -> tuple[bool, str, dict]:
    missing = []
    malformed = []
    paths = {}
    for name in REQUIRED_SKILLS:
        path = REPO_ROOT / "skills" / name / "SKILL.md"
        paths[name] = str(path)
        if not path.exists():
            missing.append(name)
            continue
        text = path.read_text(encoding="utf-8")
        if not text.startswith("---\n") or f"name: {name}" not in text.split("---", 2)[1]:
            malformed.append(name)
    ok = not missing and not malformed
    parts = []
    if missing:
        parts.append("missing: " + ", ".join(missing))
    if malformed:
        parts.append("invalid frontmatter: " + ", ".join(malformed))
    return ok, ("All required current-format skill packages exist." if ok else "; ".join(parts)), paths


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify that OpenClaw is actually using Sabi Boy V2.")
    parser.add_argument("--env-file", default=str(DEFAULT_ENV_FILE))
    parser.add_argument("--report", help="Optional JSON report path")
    parser.add_argument(
        "--install-automations",
        action="store_true",
        help="Install/update Sabi Boy reflection jobs only after every required acceptance check passes.",
    )
    args = parser.parse_args()

    _load_env_file(Path(args.env_file).expanduser())
    openclaw = os.environ.get("OPENCLAW_BIN", "openclaw")
    agent_id = os.environ.get("SABIAI_OPENCLAW_AGENT_ID", "prediction").strip() or "prediction"
    configured_root = Path(os.environ.get("SABIAI_REPO_ROOT", str(REPO_ROOT))).expanduser().resolve()
    actual_root = REPO_ROOT.resolve()
    venv_python = actual_root / ".venv" / "bin" / "python"

    checks: list[Check] = []

    checks.append(
        Check(
            "repo_root",
            configured_root == actual_root,
            (
                f"Configured repo root matches checkout: {actual_root}"
                if configured_root == actual_root
                else f"Configured SABIAI_REPO_ROOT is {configured_root}, but this checkout is {actual_root}."
            ),
            {"configured": str(configured_root), "actual": str(actual_root)},
        )
    )

    skill_ok, skill_detail, skill_paths = _check_local_skill_packages()
    checks.append(Check("local_skill_packages", skill_ok, skill_detail, skill_paths))

    openclaw_path = None
    proc = _run(["bash", "-lc", f"command -v {shlex.quote(openclaw)}"], timeout=10)
    if proc.returncode == 0 and proc.stdout.strip():
        openclaw_path = proc.stdout.strip().splitlines()[-1]
    checks.append(
        Check(
            "openclaw_cli",
            bool(openclaw_path),
            f"OpenClaw CLI: {openclaw_path}" if openclaw_path else f"OpenClaw CLI not found: {openclaw}",
        )
    )

    agent_row = None
    if openclaw_path:
        try:
            agents_payload = _json_command([openclaw, "agents", "list", "--json"])
            agent_row = _find_agent(agents_payload, agent_id)
            checks.append(
                Check(
                    "openclaw_agent",
                    agent_row is not None,
                    f"OpenClaw agent '{agent_id}' exists." if agent_row else f"OpenClaw agent '{agent_id}' was not found.",
                    agent_row,
                )
            )
        except Exception as exc:
            checks.append(Check("openclaw_agent", False, str(exc)))

    if agent_row is not None:
        workspace = _workspace_from_agent(agent_row)
        workspace_path = Path(workspace).expanduser().resolve() if workspace else None
        checks.append(
            Check(
                "agent_workspace",
                workspace_path == actual_root,
                (
                    f"Agent '{agent_id}' workspace resolves to this V2 checkout: {actual_root}"
                    if workspace_path == actual_root
                    else (
                        f"Agent '{agent_id}' workspace is {workspace_path}; expected {actual_root}. "
                        "Refusing to silently retarget an existing agent."
                    )
                ),
                {"workspace": str(workspace_path) if workspace_path else None, "expected": str(actual_root)},
            )
        )

    if openclaw_path and agent_row is not None:
        try:
            skills_check = _json_command([openclaw, "skills", "check", "--agent", agent_id, "--json"])
            skills_list = _json_command([openclaw, "skills", "list", "--agent", agent_id, "--json"])
            visible = _skill_names(skills_check) | _skill_names(skills_list)
            missing = [name for name in REQUIRED_SKILLS if name not in visible]
            checks.append(
                Check(
                    "agent_skill_visibility",
                    not missing,
                    (
                        "All required Sabi Boy V2 skills are visible to OpenClaw."
                        if not missing
                        else "OpenClaw does not report these required Sabi Boy skills as visible: " + ", ".join(missing)
                    ),
                    {"visible": sorted(visible), "required": list(REQUIRED_SKILLS), "missing": missing},
                )
            )
        except Exception as exc:
            checks.append(Check("agent_skill_visibility", False, str(exc)))

    checks.append(
        Check(
            "venv_python",
            venv_python.exists() and os.access(venv_python, os.X_OK),
            f"V2 virtualenv Python: {venv_python}" if venv_python.exists() else f"Missing V2 virtualenv Python: {venv_python}",
        )
    )

    if venv_python.exists() and os.access(venv_python, os.X_OK):
        try:
            tools_payload = _gateway_request(venv_python, "system.tools")
            data = tools_payload.get("data") or {}
            visible_tools = set(data.get("tools") or [])
            missing_tools = [name for name in REQUIRED_TOOLS if name not in visible_tools]
            checks.append(
                Check(
                    "v2_tool_surface",
                    not missing_tools,
                    (
                        f"Sabi Boy V2 gateway exposes {len(visible_tools)} tools including all required acceptance tools."
                        if not missing_tools
                        else "V2 gateway is missing required tools: " + ", ".join(missing_tools)
                    ),
                    {"count": len(visible_tools), "missing": missing_tools, "required": list(REQUIRED_TOOLS)},
                )
            )
        except Exception as exc:
            checks.append(Check("v2_tool_surface", False, str(exc)))

        try:
            readiness_payload = _gateway_request(venv_python, "system.readiness")
            readiness = readiness_payload.get("data") or {}
            label = str(readiness.get("label") or readiness.get("state") or "UNKNOWN")
            blocked = label.upper() in {"ACTION LOCKED"}
            checks.append(
                Check(
                    "v2_readiness",
                    not blocked,
                    f"Sabi Boy readiness: {label}" + (" (setup blocked)" if blocked else ""),
                    readiness,
                )
            )
        except Exception as exc:
            checks.append(Check("v2_readiness", False, str(exc)))

    required_ok = all(check.ok for check in checks)
    automations_installed = False
    automation_detail = "Not requested."

    if args.install_automations:
        if not required_ok:
            automation_detail = "Skipped because required OpenClaw/V2 acceptance checks failed."
        else:
            script = actual_root / "scripts" / "sabi_v2_install_openclaw_automations.sh"
            proc = _run(["bash", str(script)], timeout=120)
            automations_installed = proc.returncode == 0
            automation_detail = (
                proc.stdout.strip()
                if proc.returncode == 0
                else f"Installer failed ({proc.returncode}): {proc.stderr.strip() or proc.stdout.strip()}"
            )
            checks.append(Check("openclaw_automations", automations_installed, automation_detail))
            required_ok = required_ok and automations_installed

    report = {
        "product": "Sabi Boy",
        "agent_id": agent_id,
        "repo_root": str(actual_root),
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "ok": required_ok,
        "automations_requested": bool(args.install_automations),
        "automations_installed": automations_installed,
        "checks": [asdict(check) for check in checks],
    }

    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.report:
        path = Path(args.report).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if required_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
