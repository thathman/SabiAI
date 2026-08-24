#!/usr/bin/env python3
"""Create verified, read-only-safe snapshots of SabiAI V1 SQLite data.

This tool is intentionally separate from migration. It never modifies a source DB.
It uses SQLite's backup API, verifies the copy with PRAGMA quick_check, hashes every
snapshot, and writes a manifest that can be used for rollback verification.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
from typing import Iterable

DEFAULT_DATA_DIR = Path(os.getenv("SABIAI_DATA_DIR", "~/.openclaw/workspace/data")).expanduser()
DEFAULT_BACKUP_ROOT = Path(os.getenv("SABIAI_BACKUP_DIR", str(DEFAULT_DATA_DIR / "backups" / "v2-preserve"))).expanduser()
DEFAULT_SOURCES = (DEFAULT_DATA_DIR / "bets.db", DEFAULT_DATA_DIR / "sabiai_v2.db")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sqlite_quick_check(path: Path, *, readonly: bool = True) -> str:
    if readonly:
        uri = f"file:{path.resolve()}?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
    else:
        conn = sqlite3.connect(path)
    try:
        row = conn.execute("PRAGMA quick_check").fetchone()
        return str(row[0] if row else "no-result")
    finally:
        conn.close()


def backup_sqlite(source: Path, destination: Path) -> dict:
    source = source.expanduser().resolve()
    destination = destination.expanduser().resolve()
    if not source.exists():
        return {"source": str(source), "status": "missing"}
    if source == destination:
        raise RuntimeError(f"Refusing to overwrite source database: {source}")
    if destination.exists():
        raise RuntimeError(f"Refusing to overwrite existing backup: {destination}")

    source_check = sqlite_quick_check(source, readonly=True)
    if source_check.lower() != "ok":
        raise RuntimeError(f"Source database failed quick_check: {source} -> {source_check}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    dst = sqlite3.connect(destination)
    try:
        src.backup(dst)
        dst.commit()
    finally:
        dst.close()
        src.close()

    os.chmod(destination, 0o600)
    backup_check = sqlite_quick_check(destination, readonly=True)
    if backup_check.lower() != "ok":
        raise RuntimeError(f"Backup database failed quick_check: {destination} -> {backup_check}")

    return {
        "source": str(source),
        "backup": str(destination),
        "status": "ok",
        "source_quick_check": source_check,
        "backup_quick_check": backup_check,
        "bytes": destination.stat().st_size,
        "sha256": sha256_file(destination),
    }


def snapshot(sources: Iterable[Path], backup_root: Path, *, label: str | None = None) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_label = "".join(ch for ch in (label or "") if ch.isalnum() or ch in {"-", "_"}).strip("-_")
    dirname = f"{stamp}-{safe_label}" if safe_label else stamp
    snapshot_dir = backup_root.expanduser().resolve() / dirname
    if snapshot_dir.exists():
        raise RuntimeError(f"Snapshot directory already exists: {snapshot_dir}")
    snapshot_dir.mkdir(parents=True, mode=0o700)

    records = []
    for source in sources:
        source = source.expanduser()
        records.append(backup_sqlite(source, snapshot_dir / source.name))

    manifest = {
        "format": "sabiai-v2-preservation-manifest-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "snapshot_dir": str(snapshot_dir),
        "records": records,
        "restore_policy": "Verify SHA-256 and SQLite quick_check before any restore. Never restore over a live DB while writers are running.",
    }
    manifest_path = snapshot_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(manifest_path, 0o600)
    return manifest_path


def verify_manifest(manifest_path: Path) -> tuple[bool, list[dict]]:
    manifest = json.loads(manifest_path.expanduser().read_text(encoding="utf-8"))
    results = []
    ok = True
    for record in manifest.get("records", []):
        if record.get("status") != "ok":
            results.append({"source": record.get("source"), "status": record.get("status")})
            continue
        path = Path(record["backup"])
        current = {
            "backup": str(path),
            "exists": path.exists(),
            "sha256_ok": False,
            "quick_check": None,
        }
        if path.exists():
            current["sha256_ok"] = sha256_file(path) == record.get("sha256")
            current["quick_check"] = sqlite_quick_check(path, readonly=True)
        current_ok = bool(current["exists"] and current["sha256_ok"] and str(current["quick_check"]).lower() == "ok")
        current["ok"] = current_ok
        ok = ok and current_ok
        results.append(current)
    return ok, results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Preserve SabiAI V1 SQLite databases before V2 migration work.")
    parser.add_argument("--source", action="append", type=Path, help="SQLite source. Repeat for multiple DBs. Defaults to bets.db and sabiai_v2.db.")
    parser.add_argument("--backup-root", type=Path, default=DEFAULT_BACKUP_ROOT)
    parser.add_argument("--label", help="Optional short label appended to the timestamped snapshot directory.")
    parser.add_argument("--verify", type=Path, help="Verify an existing preservation manifest instead of creating a snapshot.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.verify:
        ok, records = verify_manifest(args.verify)
        print(json.dumps({"ok": ok, "records": records}, indent=2))
        return 0 if ok else 1

    sources = tuple(args.source or DEFAULT_SOURCES)
    try:
        manifest = snapshot(sources, args.backup_root, label=args.label)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 1
    print(json.dumps({"ok": True, "manifest": str(manifest)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
