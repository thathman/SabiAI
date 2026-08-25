from __future__ import annotations

from dataclasses import asdict

from sabiai.bookmakers import TargetOffer
from sabiai.system import SystemReadinessService

from .helpers import ticket_from_args
from .serializers import conversion_to_dict, json_value


class BookmakerTools:
    def __init__(self, app):
        self.app = app

    def handlers(self) -> dict:
        return {
            "bookmaker.resolve": self.resolve,
            "bookmaker.capabilities": self.capabilities,
            "bookmaker.booking_code.import_plan": self.booking_code_import_plan,
            "bookmaker.search.plan": self.search_plan,
            "bookmaker.convert.plan": self.convert_plan,
            "bookmaker.build.plan": self.build_plan,
            "bookmaker.build.execute": self.build_execute,
        }

    def resolve(self, args: dict) -> dict:
        bookmaker = self.app.bookmakers.resolve(str(args.get("name", "")))
        if bookmaker is None:
            return {"found": False, "name": args.get("name")}
        adapter = self.app.bookmaker_adapters.get(bookmaker.slug)
        proven = sorted(cap.value for cap in adapter.capabilities()) if adapter else []
        return {
            "found": True,
            "id": bookmaker.id,
            "name": bookmaker.name,
            "slug": bookmaker.slug,
            "proven_capabilities": proven,
        }

    def capabilities(self, args: dict) -> dict:
        name = args.get("name")
        if name:
            bookmaker = self.app.bookmakers.resolve(str(name))
            if bookmaker is None:
                return {"found": False, "name": name}
            adapter = self.app.bookmaker_adapters.get(bookmaker.slug)
            return {
                "found": True,
                "bookmaker": bookmaker.name,
                "slug": bookmaker.slug,
                "adapter": json_value(adapter.status()) if adapter else None,
            }
        return {
            "bookmakers": [json_value(status) for status in self.app.bookmaker_adapters.statuses()]
        }

    def booking_code_import_plan(self, args: dict) -> dict:
        plan = self.app.bookmaker_execution.import_booking_code(
            bookmaker=str(args.get("bookmaker", "")),
            booking_code=str(args.get("booking_code", "")),
        )
        return json_value(plan)

    def search_plan(self, args: dict) -> dict:
        ticket = ticket_from_args(self.app, args)
        target = str(args.get("target_bookmaker") or "")
        plan = self.app.bookmaker_discovery.plan_conversion(
            ticket,
            target_bookmaker=target,
        )
        return json_value(plan)

    def convert_plan(self, args: dict) -> dict:
        source_ticket = ticket_from_args(self.app, args)
        target_name = str(args.get("target_bookmaker", ""))
        target = self.app.bookmakers.resolve(target_name)
        if target is None:
            raise ValueError(f"Unknown target bookmaker: {target_name}")

        offers = [
            TargetOffer(
                event=str(raw["event"]),
                market=str(raw.get("market") or raw.get("pick") or ""),
                odds=raw["odds"],
                bookmaker_slug=str(raw.get("bookmaker_slug") or target.slug),
                event_ref=raw.get("event_ref"),
                market_ref=raw.get("market_ref"),
                home=raw.get("home"),
                away=raw.get("away"),
                sport=raw.get("sport"),
            )
            for raw in args.get("target_offers", [])
        ]

        source_book = None
        if args.get("bookmaker"):
            resolved = self.app.bookmakers.resolve(str(args["bookmaker"]))
            source_book = resolved.slug if resolved else str(args["bookmaker"])

        plan = self.app.ticket_converter.plan(
            source_ticket,
            target_bookmaker=target.name,
            offers=offers,
            source_bookmaker_slug=source_book,
        )
        return conversion_to_dict(plan)

    def build_plan(self, args: dict) -> dict:
        ticket = ticket_from_args(self.app, args)
        target = str(args.get("target_bookmaker") or args.get("bookmaker") or "")
        return json_value(self.app.bookmaker_execution.build(ticket, bookmaker=target))

    def build_execute(self, args: dict) -> dict:
        readiness = SystemReadinessService(self.app._db(initialize=True)).assess()
        if not readiness.can_build_ticket:
            return {
                "executed": False,
                "reason": f"Sabi Boy is currently {readiness.label}; ticket-building execution is paused.",
                "readiness": json_value(readiness),
            }

        ticket = ticket_from_args(self.app, args)
        target = str(args.get("target_bookmaker") or args.get("bookmaker") or "")
        plan = self.app.bookmaker_execution.build(ticket, bookmaker=target)
        result = self.app.bookmaker_runner.execute(
            plan,
            repo_root=self.app.settings.repo_root,
            dry_run=bool(args.get("dry_run", False)),
            timeout_seconds=int(args.get("timeout_seconds", 120)),
        )
        return {
            "executed": True,
            "plan": json_value(plan),
            "result": json_value(result),
        }
