from __future__ import annotations

from sabiai.bookmakers import BookmakerBrowserProfiles
from sabiai.system import SystemReadinessService

from .helpers import ticket_from_args
from .serializers import json_value


class BookmakerBrowserBuildTools:
    """Plan rich market-aware booking-code construction through OpenClaw Browser.

    This path creates a reusable bookmaker code only. It never authorizes stake entry,
    payment, or wager placement. The generated code must be restored and checked with
    `bookmaker.build.verify` before Sabi Boy calls the rebuild successful.
    """

    def __init__(self, app):
        self.app = app
        self.profiles = BookmakerBrowserProfiles()

    def handlers(self) -> dict:
        return {
            "bookmaker.browser_build.playbook": self.playbook,
            "bookmaker.browser_build.plan": self.plan,
        }

    def playbook(self, args: dict) -> dict:
        bookmaker = self.app.bookmakers.resolve(
            str(args.get("bookmaker") or args.get("target_bookmaker") or "")
        )
        if bookmaker is None:
            return {
                "found": False,
                "ready": False,
                "bookmaker": args.get("bookmaker") or args.get("target_bookmaker"),
            }
        profile = self.profiles.browser_build(bookmaker.slug)
        return {
            "found": profile is not None,
            "ready": bool(profile and profile.ready and profile.entry_url),
            "bookmaker": bookmaker.name,
            "slug": bookmaker.slug,
            "playbook": json_value(profile) if profile else None,
        }

    def plan(self, args: dict) -> dict:
        expected_draft_id = str(args.get("expected_draft_id") or args.get("draft_id") or "").strip() or None
        expected_draft = None
        if expected_draft_id:
            expected_draft = self.app._draft_store().get(expected_draft_id)
            if expected_draft is None:
                raise ValueError(f"Unknown converted ticket draft: {expected_draft_id}")

        target_name = str(args.get("target_bookmaker") or args.get("bookmaker") or "").strip()
        if not target_name and expected_draft and expected_draft.target_bookmaker_slug:
            target_name = expected_draft.target_bookmaker_slug
        if not target_name:
            raise ValueError(
                "bookmaker.browser_build.plan needs target_bookmaker, unless the converted draft already records its target bookmaker."
            )

        bookmaker = self.app.bookmakers.resolve(target_name)
        if bookmaker is None:
            raise ValueError(f"Unknown target bookmaker: {target_name}")

        if expected_draft and expected_draft.target_bookmaker_slug:
            recorded = self.app.bookmakers.resolve(expected_draft.target_bookmaker_slug)
            recorded_slug = recorded.slug if recorded else expected_draft.target_bookmaker_slug.casefold()
            if recorded_slug != bookmaker.slug:
                raise ValueError(
                    f"Converted draft targets {expected_draft.target_bookmaker_slug}; refusing to build it on {bookmaker.name}."
                )

        working_args = dict(args)
        if expected_draft and not working_args.get("legs"):
            payload = expected_draft.payload.get("ticket") if isinstance(expected_draft.payload, dict) else None
            if payload is None and isinstance(expected_draft.payload, dict):
                payload = expected_draft.payload
            legs = payload.get("legs") if isinstance(payload, dict) else None
            if not isinstance(legs, list) or not legs:
                raise ValueError("Converted ticket draft has no ticket legs to build.")
            working_args["legs"] = legs
            working_args["bookmaker"] = bookmaker.name

        ticket = ticket_from_args(self.app, working_args)
        profile = self.profiles.browser_build(bookmaker.slug)
        search = self.app.bookmaker_discovery.plan_conversion(
            ticket,
            target_bookmaker=bookmaker.name,
        )
        readiness = SystemReadinessService(self.app._db(initialize=True)).assess()
        profile_ready = bool(profile and profile.ready and profile.entry_url)
        ready = bool(profile_ready and search.ready and readiness.can_build_ticket)

        steps = []
        if profile_ready:
            steps.extend(
                [
                    f"Open {profile.entry_url} using the controlled OpenClaw browser.",
                    profile.event_navigation,
                    profile.selection_action,
                    (
                        "After each leg, confirm the visible event, exact market/line/period and current decimal odds still match the plan. "
                        "If a price moved, record the new price; if the market changed or disappeared, stop and re-plan that leg."
                    ),
                    profile.booking_action or "Stop: no verified booking-code creation action is available.",
                    profile.booking_code_field or "Stop: no verified booking-code field is available.",
                    (
                        "Restore the newly generated code through the bookmaker restoration playbook and call "
                        "bookmaker.build.verify before returning the code to the user."
                    ),
                ]
            )

        reasons = []
        if not profile_ready:
            reasons.append(f"{bookmaker.name} does not yet have a verified rich browser build profile.")
        if not search.ready:
            reasons.extend(search.missing_context)
        if not readiness.can_build_ticket:
            reasons.append(f"Sabi Boy is {readiness.label}; booking-code build execution is paused.")

        return {
            "ready": ready,
            "bookmaker": bookmaker.name,
            "slug": bookmaker.slug,
            "expected_draft_id": expected_draft_id,
            "ticket_id": ticket.id,
            "leg_count": len(ticket.legs),
            "combined_odds_at_plan_time": str(ticket.combined_odds),
            "readiness": json_value(readiness),
            "playbook": json_value(profile) if profile else None,
            "tasks": json_value(search.tasks),
            "missing_context": list(search.missing_context),
            "steps": steps,
            "reasons_not_ready": reasons,
            "verification_tool": "bookmaker.build.verify",
            "scope": "create_booking_code_only",
        }
