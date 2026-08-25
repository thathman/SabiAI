from __future__ import annotations

from sabiai.bookmakers import BookmakerBrowserHealthService

from .serializers import json_value


class BookmakerHealthTools:
    def __init__(self, app):
        self.app = app

    def handlers(self) -> dict:
        return {"bookmaker.browser_health": self.browser_health}

    def browser_health(self, args: dict) -> dict:
        service = BookmakerBrowserHealthService(
            self.app._db(initialize=True),
            bookmakers=self.app.bookmakers,
        )
        name = str(args.get("bookmaker") or "").strip()
        kwargs = {
            "verification_stale_days": int(args.get("verification_stale_days", 30)),
            "runtime_recent_hours": int(args.get("runtime_recent_hours", 24)),
        }
        if name:
            return json_value(service.one(name, **kwargs))
        rows = service.all(**kwargs)
        return {
            "bookmakers": [json_value(row) for row in rows],
            "note": "Configured playbooks and recent live execution are separate facts; no recent observation means unexercised, not automatically broken.",
        }
