from __future__ import annotations

from sabiai import __version__
from sabiai.sources import SourceHealthService
from sabiai.system import SystemReadinessService

from .serializers import json_value


class SystemTools:
    def __init__(self, app):
        self.app = app

    def handlers(self) -> dict:
        return {
            "system.initialize": self.initialize,
            "system.health": self.health,
            "system.readiness": self.readiness,
            "system.sources": self.sources,
            "system.api_economy": self.api_economy,
        }

    def initialize(self, args: dict) -> dict:
        db = self.app._db(initialize=True)
        return {
            "database": str(self.app.settings.v2_db),
            "schema_version": db.schema_version(),
            "counts": db.table_counts(),
        }

    def health(self, args: dict) -> dict:
        db = self.app._db()
        exists = self.app.settings.v2_db.exists()
        if not exists:
            return {
                "version": __version__,
                "database": str(self.app.settings.v2_db),
                "database_exists": False,
                "database_ok": False,
            }
        try:
            version = db.schema_version()
            readiness = SystemReadinessService(db).assess(
                required_capabilities=tuple(str(x) for x in args.get("required_capabilities", []))
            )
            return {
                "version": __version__,
                "database": str(self.app.settings.v2_db),
                "database_exists": True,
                "database_ok": version is not None,
                "schema_version": version,
                "counts": db.table_counts(),
                "readiness": json_value(readiness),
            }
        except Exception as exc:
            return {
                "version": __version__,
                "database": str(self.app.settings.v2_db),
                "database_exists": True,
                "database_ok": False,
                "error": str(exc),
            }

    def readiness(self, args: dict) -> dict:
        report = SystemReadinessService(self.app._db(initialize=True)).assess(
            required_capabilities=tuple(str(x) for x in args.get("required_capabilities", [])),
            stale_settlement_hours=int(args.get("stale_settlement_hours", 24)),
        )
        data = json_value(report)
        data["state"] = report.label
        data["can_research"] = report.can_research
        data["can_build_ticket"] = report.can_build_ticket
        return data

    def sources(self, args: dict) -> dict:
        service = SourceHealthService(self.app._db(initialize=True))
        return {
            "sources": [json_value(item) for item in service.sources(
                recent_limit_per_source=int(args.get("recent_limit_per_source", 100))
            )]
        }

    def api_economy(self, args: dict) -> dict:
        return SourceHealthService(self.app._db(initialize=True)).economy()
