#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import traceback

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient

from dashboard.v2_app import app as dashboard_app
from sabiai.config import Settings
from sabiai.migration import V1Migrator
from sabiai.openclaw import SabiToolGateway
from sabiai.ops import BackupService
from sabiai.storage import SabiDatabase


@dataclass(slots=True)
class Gate:
    name: str
    ok: bool
    detail: object


class Acceptance:
    def __init__(self, settings: Settings, *, migrate_v1: bool, run_tests: bool, backup_drill: bool):
        self.settings = settings
        self.migrate_v1 = migrate_v1
        self.run_tests = run_tests
        self.backup_drill = backup_drill
        self.gates: list[Gate] = []

    def gate(self, name: str, fn) -> None:
        try:
            detail = fn()
            ok = not (isinstance(detail, dict) and detail.get("ok") is False)
            self.gates.append(Gate(name, ok, detail))
        except Exception as exc:
            self.gates.append(
                Gate(
                    name,
                    False,
                    {
                        "error": str(exc),
                        "type": type(exc).__name__,
                        "traceback": traceback.format_exc(limit=6),
                    },
                )
            )

    def run(self) -> dict:
        self.gate("branch", self._branch)
        self.gate("database_initialize", self._database_initialize)
        if self.migrate_v1:
            self.gate("v1_migration_reconciliation", self._migration)
        else:
            self.gate("migration_state", self._migration_state)
        if self.run_tests:
            self.gate("pytest", self._pytest)
        self.gate("openclaw_gateway", self._gateway)
        self.gate("dashboard_read_only", self._dashboard)
        if self.backup_drill:
            self.gate("backup_restore_drill", self._backup_restore)

        failed = [gate.name for gate in self.gates if not gate.ok]
        return {
            "ok": not failed,
            "product": "Sabi Boy",
            "branch_required": "v2",
            "repository": str(ROOT),
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "failed_gates": failed,
            "gates": [asdict(gate) for gate in self.gates],
        }

    def _branch(self) -> dict:
        branch = self._cmd(["git", "rev-parse", "--abbrev-ref", "HEAD"]).strip()
        commit = self._cmd(["git", "rev-parse", "HEAD"]).strip()
        return {"ok": branch == "v2", "branch": branch, "commit": commit}

    def _database_initialize(self) -> dict:
        db = SabiDatabase(self.settings.v2_db)
        db.initialize()
        with db.connect() as conn:
            integrity = str(conn.execute("PRAGMA quick_check").fetchone()[0])
        return {
            "ok": integrity.casefold() == "ok" and db.schema_version() is not None,
            "path": str(self.settings.v2_db),
            "schema_version": db.schema_version(),
            "integrity": integrity,
            "counts": db.table_counts(),
        }

    def _migration(self) -> dict:
        if not self.settings.legacy_bets_db.is_file():
            return {
                "ok": False,
                "error": f"V1 database not found: {self.settings.legacy_bets_db}",
            }
        report = V1Migrator(self.settings.legacy_bets_db, self.settings.v2_db).migrate()
        data = report.as_dict()
        data["ok"] = bool(report.ready)
        return data

    def _migration_state(self) -> dict:
        db = SabiDatabase(self.settings.v2_db)
        with db.connect() as conn:
            source = conn.execute(
                "SELECT value FROM v2_meta WHERE key='v1_migration_source'"
            ).fetchone()
            completed = conn.execute(
                "SELECT value FROM v2_meta WHERE key='v1_migration_completed_at'"
            ).fetchone()
        legacy_exists = self.settings.legacy_bets_db.is_file()
        migrated = bool(source and completed)
        return {
            "ok": migrated or not legacy_exists,
            "legacy_database_exists": legacy_exists,
            "migration_recorded": migrated,
            "source": source[0] if source else None,
            "completed_at": completed[0] if completed else None,
            "note": "Use --migrate-v1 for release acceptance when a V1 database exists." if legacy_exists and not migrated else None,
        }

    def _pytest(self) -> dict:
        command = [sys.executable, "-m", "pytest", "-q"]
        proc = subprocess.run(
            command,
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=900,
            check=False,
        )
        output = proc.stdout[-20000:]
        return {
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "command": command,
            "output": output,
        }

    def _gateway(self) -> dict:
        gateway = SabiToolGateway(self.settings)
        tools = gateway.dispatch("system.tools", {})
        health = gateway.dispatch("system.health", {})
        readiness = gateway.dispatch("system.readiness", {})
        health_data = health.get("data") or {}
        readiness_data = readiness.get("data") or {}
        state = str(readiness_data.get("state") or "")
        ok = bool(
            tools.get("ok")
            and health.get("ok")
            and readiness.get("ok")
            and health_data.get("database_ok")
            and state != "ACTION LOCKED"
        )
        return {
            "ok": ok,
            "tool_count": (tools.get("data") or {}).get("count"),
            "database_ok": health_data.get("database_ok"),
            "schema_version": health_data.get("schema_version"),
            "readiness": state,
            "issues": readiness_data.get("issues", []),
        }

    def _dashboard(self) -> dict:
        disallowed: list[dict] = []
        for route in dashboard_app.routes:
            path = getattr(route, "path", "")
            if not path.startswith("/api/v2"):
                continue
            methods = sorted(set(getattr(route, "methods", set()) or set()))
            bad = [method for method in methods if method not in {"GET", "HEAD", "OPTIONS"}]
            if bad:
                disallowed.append({"path": path, "methods": methods})

        client = TestClient(dashboard_app)
        health = client.get("/health")
        overview = client.get("/api/v2/overview")
        return {
            "ok": not disallowed and health.status_code == 200 and overview.status_code == 200,
            "disallowed_routes": disallowed,
            "health_status": health.status_code,
            "health": health.json() if health.status_code == 200 else health.text,
            "overview_status": overview.status_code,
        }

    def _backup_restore(self) -> dict:
        if not self.settings.v2_db.is_file():
            return {"ok": False, "error": "V2 database does not exist for backup drill."}
        service = BackupService()
        with tempfile.TemporaryDirectory(prefix="sabi-boy-acceptance-") as tmp:
            root = Path(tmp)
            manifest = service.create(
                {"v2": self.settings.v2_db},
                destination_root=root / "backups",
            )
            verify = service.verify(manifest.manifest_path)
            restored = root / "restored-v2.db"
            restore = service.restore(
                manifest.manifest_path,
                label="v2",
                destination=restored,
                overwrite=False,
            )
            with SabiDatabase(restored).connect() as conn:
                integrity = str(conn.execute("PRAGMA quick_check").fetchone()[0])
            return {
                "ok": bool(verify.get("ok") and restore.get("ok") and integrity.casefold() == "ok"),
                "verified": verify,
                "restore": restore,
                "restored_integrity": integrity,
            }

    @staticmethod
    def _cmd(command: list[str]) -> str:
        proc = subprocess.run(
            command,
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"Command failed ({proc.returncode}): {' '.join(command)}\n{proc.stdout}")
        return proc.stdout


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Sabi Boy V2 release acceptance gates.")
    parser.add_argument(
        "--migrate-v1",
        action="store_true",
        help="Run the deterministic/idempotent V1 -> V2 migration and require reconciliation.",
    )
    parser.add_argument("--skip-tests", action="store_true")
    parser.add_argument("--skip-backup-drill", action="store_true")
    parser.add_argument(
        "--report",
        help="Optional report path. Defaults to data/release/acceptance-latest.json.",
    )
    args = parser.parse_args()

    settings = Settings.from_env()
    acceptance = Acceptance(
        settings,
        migrate_v1=args.migrate_v1,
        run_tests=not args.skip_tests,
        backup_drill=not args.skip_backup_drill,
    )
    report = acceptance.run()

    report_path = Path(args.report).expanduser() if args.report else settings.data_dir / "release" / "acceptance-latest.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"Acceptance report: {report_path}", file=sys.stderr)
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
