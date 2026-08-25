#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sabiai.config import Settings
from sabiai.ops import BackupService


def main() -> int:
    settings = Settings.from_env()
    parser = argparse.ArgumentParser(description="Create or verify Sabi Boy database backups.")
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create")
    create.add_argument("--destination", default=str(settings.data_dir / "backups" / "sabi-boy"))
    create.add_argument("--legacy", default=str(settings.legacy_bets_db))
    create.add_argument("--v2", default=str(settings.v2_db))

    verify = sub.add_parser("verify")
    verify.add_argument("manifest")

    restore = sub.add_parser("restore")
    restore.add_argument("manifest")
    restore.add_argument("--label", required=True, choices=["v1", "v2"])
    restore.add_argument("--destination")
    restore.add_argument("--overwrite", action="store_true")

    args = parser.parse_args()
    service = BackupService()

    if args.command == "create":
        files = {"v1": args.legacy, "v2": args.v2}
        result = service.create(files, destination_root=args.destination).as_dict()
    elif args.command == "verify":
        result = service.verify(args.manifest)
    else:
        result = service.restore(
            args.manifest,
            label=args.label,
            destination=args.destination,
            overwrite=args.overwrite,
        )

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok", True) else 2


if __name__ == "__main__":
    raise SystemExit(main())
