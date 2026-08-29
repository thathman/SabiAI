#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sabiai import __version__
from sabiai.config import Settings
from sabiai.storage import SabiDatabase


REQUIRED_TOOLS = {
    "research.discovery.refresh",
    "research.radar",
    "research.market_inventory",
    "research.event.sources",
    "research.coverage.funnel",
    "research.action_price.gaps",
}
REQUIRED_FILES = (
    "scripts/sabi_v2_discovery_radar.py",
    "systemd/sabi-boy-coverage.service",
    "systemd/sabi-boy-coverage.timer",
    "dashboard/v2/coverage_funnel.js",
    "sabiai/storage/migrations/0017_coverage_engine.sql",
    "sabiai/research/prefilter.py",
    "sabiai/research/action_price.py",
    "skills/sabi-boy-coverage-engine/SKILL.md",
)


def gateway(python_bin: Path, tool: str, args: dict | None = None) -> dict:
    request = json.dumps({"tool": tool, "args": args or {}}, separators=(",", ":"))
    proc = subprocess.run(
        [str(python_bin), str(ROOT / "scripts" / "sabiai_v2_tool.py"), "--request", request],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=90,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or f"gateway exited {proc.returncode}")
    payload = json.loads(proc.stdout)
    if not isinstance(payload, dict) or not payload.get("ok"):
        raise RuntimeError(f"Gateway rejected {tool}: {payload}")
    return payload["data"]


def main() -> int:
    parser = argparse.ArgumentParser(description="Fail-closed Sabi Boy V2.4 coverage-engine acceptance.")
    parser.add_argument("--report")
    args = parser.parse_args()

    settings = Settings.from_env()
    python_bin = ROOT / ".venv" / "bin" / "python"
    if not python_bin.exists():
        python_bin = Path(sys.executable)

    checks: list[dict] = []

    def add(name: str, ok: bool, detail: str, data=None) -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": detail, "data": data})

    add("version", __version__ == "2.4.0.0", f"Package version is {__version__}.")

    missing = [path for path in REQUIRED_FILES if not (ROOT / path).is_file()]
    add(
        "coverage_files",
        not missing,
        "All V2.4 coverage runtime files exist." if not missing else "Missing: " + ", ".join(missing),
        {"missing": missing},
    )

    skill = ROOT / "skills" / "sabi-boy-coverage-engine" / "SKILL.md"
    try:
        skill_text = skill.read_text(encoding="utf-8")
        skill_ok = skill_text.startswith("---\n") and "name: sabi-boy-coverage-engine" in skill_text.split("---", 2)[1]
        add("coverage_skill", skill_ok, "Current-format coverage-engine skill package is valid.")
    except Exception as exc:
        add("coverage_skill", False, f"Coverage skill check failed: {exc}")

    try:
        database = SabiDatabase(settings.v2_db)
        database.initialize()
        version = database.schema_version()
        with database.connect() as conn:
            tables = {
                str(row[0])
                for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            }
        required_tables = {
            "coverage_events",
            "coverage_event_sources",
            "coverage_market_catalogue",
            "coverage_market_offers",
            "coverage_discovery_runs",
        }
        missing_tables = sorted(required_tables - tables)
        add(
            "coverage_schema",
            not missing_tables and int(version or 0) >= 17,
            f"Schema version {version}; coverage tables present." if not missing_tables else "Missing coverage tables: " + ", ".join(missing_tables),
            {"schema_version": version, "missing_tables": missing_tables},
        )
    except Exception as exc:
        add("coverage_schema", False, f"Coverage schema check failed: {type(exc).__name__}: {str(exc)[:400]}")

    try:
        tools = set(gateway(python_bin, "system.tools").get("tools") or [])
        missing_tools = sorted(REQUIRED_TOOLS - tools)
        add(
            "coverage_tools",
            not missing_tools,
            "All required V2.4 coverage tools are registered." if not missing_tools else "Missing tools: " + ", ".join(missing_tools),
            {"missing_tools": missing_tools, "tool_count": len(tools)},
        )
        funnel = gateway(python_bin, "research.coverage.funnel")
        add(
            "coverage_funnel",
            isinstance(funnel, dict) and "discovered" in funnel and "selected" in funnel,
            "Coverage funnel read succeeds.",
            funnel,
        )
    except Exception as exc:
        add("coverage_tools", False, f"Coverage gateway check failed: {type(exc).__name__}: {str(exc)[:400]}")

    service = ROOT / "systemd" / "sabi-boy-coverage.service"
    timer = ROOT / "systemd" / "sabi-boy-coverage.timer"
    try:
        service_text = service.read_text(encoding="utf-8")
        timer_text = timer.read_text(encoding="utf-8")
        ok = "sabi_v2_discovery_radar.py" in service_text and "OnUnitActiveSec=30min" in timer_text
        add("coverage_scheduler", ok, "Coverage service uses the no-model radar runner on a 30-minute timer.")
    except Exception as exc:
        add("coverage_scheduler", False, f"Coverage scheduler check failed: {exc}")

    ok = all(check["ok"] for check in checks)
    report = {"ok": ok, "product": "Sabi Boy", "version": __version__, "checks": checks}
    if args.report:
        path = Path(args.report).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
