from __future__ import annotations

from sabiai import __version__
from sabiai.sources import SourceHealthService
from sabiai.storage import DailyResearchLog
from sabiai.system import JobService, SystemReadinessService

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
            "system.jobs.seed": self.jobs_seed,
            "system.jobs.list": self.jobs_list,
            "system.jobs.register": self.jobs_register,
            "system.jobs.start": self.jobs_start,
            "system.jobs.success": self.jobs_success,
            "system.jobs.failure": self.jobs_failure,
            "system.jobs.enable": self.jobs_enable,
            "system.daily_research": self.daily_research,
        }

    def initialize(self, args: dict) -> dict:
        db = self.app._db(initialize=True)
        jobs = JobService(db).seed_defaults()
        return {
            "database": str(self.app.settings.v2_db),
            "schema_version": db.schema_version(),
            "counts": db.table_counts(),
            "jobs": [json_value(job) for job in jobs],
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
                "jobs": [json_value(job) for job in JobService(db).list(enabled_only=True)],
                "latest_daily_research": DailyResearchLog(db).latest(),
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

    def daily_research(self, args: dict) -> dict:
        """Return the direct system scan so Sabi Boy can use it as conversation context."""
        return DailyResearchLog(self.app._db(initialize=True)).context(
            limit=int(args.get("limit", 5))
        )

    def jobs_seed(self, args: dict) -> dict:
        jobs = JobService(self.app._db(initialize=True)).seed_defaults()
        return {"jobs": [json_value(job) for job in jobs]}

    def jobs_list(self, args: dict) -> dict:
        jobs = JobService(self.app._db(initialize=True)).list(
            enabled_only=bool(args.get("enabled_only", False))
        )
        return {"jobs": [json_value(job) for job in jobs]}

    def jobs_register(self, args: dict) -> dict:
        job = JobService(self.app._db(initialize=True)).register(
            str(args.get("name") or ""),
            description=args.get("description"),
            expected_interval_seconds=(
                int(args["expected_interval_seconds"])
                if args.get("expected_interval_seconds") is not None
                else None
            ),
            enabled=bool(args.get("enabled", True)),
        )
        return json_value(job)

    def jobs_start(self, args: dict) -> dict:
        return json_value(JobService(self.app._db(initialize=True)).start(str(args.get("name") or "")))

    def jobs_success(self, args: dict) -> dict:
        return json_value(JobService(self.app._db(initialize=True)).success(str(args.get("name") or "")))

    def jobs_failure(self, args: dict) -> dict:
        return json_value(
            JobService(self.app._db(initialize=True)).failure(
                str(args.get("name") or ""),
                str(args.get("error") or "job failed"),
            )
        )

    def jobs_enable(self, args: dict) -> dict:
        return json_value(
            JobService(self.app._db(initialize=True)).set_enabled(
                str(args.get("name") or ""), bool(args.get("enabled", True))
            )
        )
