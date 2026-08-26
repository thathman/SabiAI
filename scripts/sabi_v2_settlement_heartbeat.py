#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sabiai.config import Settings
from sabiai.notifications import WebPushService
from sabiai.settlement import AutomaticSettlementService
from sabiai.storage import SabiDatabase
from sabiai.system import JobService


def main() -> int:
    settings = Settings.from_env()
    db = SabiDatabase(settings.v2_db)
    db.initialize()
    jobs = JobService(db)
    jobs.register(
        "auto-settlement",
        description="Poll live/final event results and settle supported pending selections.",
        expected_interval_seconds=600,
    )
    jobs.start("auto-settlement")
    try:
        report = AutomaticSettlementService(db, settings=settings).run()
        if report.source_errors:
            raise RuntimeError("; ".join(report.source_errors))
        delivery = None
        if report.changed:
            delivery = WebPushService(db, settings).send(
                {
                    "title": "Sabi Boy settled new results",
                    "body": (
                        f"{report.picks_settled} pick(s) and "
                        f"{report.ticket_legs_settled} ticket leg(s) updated."
                    ),
                    "tag": "sabi-boy-settlement",
                    "url": "/history",
                    "renotify": True,
                }
            )
        jobs.success("auto-settlement")
    except Exception as exc:
        jobs.failure("auto-settlement", f"{type(exc).__name__}: {str(exc)[:500]}")
        print(json.dumps({"ok": False, "error": str(exc)[:500]}))
        return 1

    payload = {"ok": True, "settlement": report.as_dict()}
    if delivery is not None:
        payload["push"] = {
            "enabled": delivery.enabled,
            "attempted": delivery.attempted,
            "delivered": delivery.delivered,
            "expired": delivery.expired,
            "failed": delivery.failed,
        }
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
