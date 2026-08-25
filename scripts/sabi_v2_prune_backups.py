#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sabiai.config import Settings


def _candidate(path: Path) -> tuple[datetime, Path] | None:
    manifest = path / "manifest.json"
    if not path.is_dir() or not manifest.is_file():
        return None
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
        created = datetime.fromisoformat(str(data["created_at"]).replace("Z", "+00:00"))
        declared_dir = Path(str(data["directory"])).expanduser().resolve()
        files = data.get("files")
    except Exception:
        return None
    if declared_dir != path.resolve() or not isinstance(files, list) or not files:
        return None
    # Refuse to classify a directory as ours if any declared backup file escapes it.
    root = path.resolve()
    for row in files:
        if not isinstance(row, dict) or not row.get("backup"):
            return None
        backup = Path(str(row["backup"])).expanduser().resolve()
        if root not in backup.parents:
            return None
    return created, path


def main() -> int:
    settings = Settings.from_env()
    parser = argparse.ArgumentParser(description="Prune only recognized old Sabi Boy backup directories.")
    parser.add_argument(
        "--root",
        default=str(settings.data_dir / "backups" / "sabi-boy"),
        help="Backup root containing timestamp directories.",
    )
    parser.add_argument("--keep", type=int, default=30, help="Number of newest verified backup sets to keep.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.keep < 1:
        raise SystemExit("--keep must be at least 1")
    root = Path(args.root).expanduser()
    if not root.exists():
        print(json.dumps({"ok": True, "root": str(root), "kept": 0, "removed": [], "ignored": []}, indent=2))
        return 0
    if not root.is_dir():
        raise SystemExit(f"Backup root is not a directory: {root}")

    candidates = []
    ignored = []
    for child in root.iterdir():
        found = _candidate(child)
        if found is None:
            ignored.append(str(child))
        else:
            candidates.append(found)
    candidates.sort(key=lambda item: item[0], reverse=True)

    keep = candidates[: args.keep]
    prune = candidates[args.keep :]
    removed = []
    for _, path in prune:
        removed.append(str(path))
        if not args.dry_run:
            shutil.rmtree(path)

    result = {
        "ok": True,
        "root": str(root),
        "keep_limit": args.keep,
        "recognized": len(candidates),
        "kept": [str(path) for _, path in keep],
        "removed": removed,
        "ignored": sorted(ignored),
        "dry_run": bool(args.dry_run),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
