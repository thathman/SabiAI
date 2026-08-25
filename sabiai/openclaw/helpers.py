from __future__ import annotations

from sabiai.domain.models import Ticket, TicketLeg


def ticket_from_args(app, args: dict) -> Ticket:
    working = dict(args)
    legs = working.get("legs")
    if (not isinstance(legs, list) or not legs) and working.get("draft_id"):
        draft_id = str(working["draft_id"])
        draft = app._draft_store().get(draft_id)
        if draft is None:
            raise ValueError(f"Unknown ticket draft: {draft_id}")
        payload = draft.payload if isinstance(draft.payload, dict) else {}
        ticket_payload = payload.get("ticket") if isinstance(payload.get("ticket"), dict) else payload
        draft_legs = ticket_payload.get("legs") if isinstance(ticket_payload, dict) else None
        if not isinstance(draft_legs, list) or not draft_legs:
            raise ValueError(f"Ticket draft {draft_id} does not contain usable ticket legs.")
        working["legs"] = draft_legs
        if not working.get("bookmaker"):
            working["bookmaker"] = draft.target_bookmaker_slug or draft.source_bookmaker_slug
        working.setdefault("source_type", "draft")
        working.setdefault("source_reference", draft_id)

    normalized = app.ticket_normalizer.normalize(
        working.get("legs", []),
        bookmaker=working.get("bookmaker"),
        source_type=str(working.get("source_type", "instruction")),
        source_reference=working.get("source_reference"),
    )
    errors = [issue.message for issue in normalized.issues if issue.level == "error"]
    if errors or not normalized.ticket.legs:
        raise ValueError("; ".join(errors) or "Ticket needs at least one usable leg.")
    return normalized.ticket


def bookmaker_slug(app, value) -> str | None:
    if not value:
        return None
    resolved = app.bookmakers.resolve(str(value))
    return resolved.slug if resolved else str(value).strip().casefold()


def find_leg(ticket: Ticket, leg_id=None, event_label=None) -> TicketLeg | None:
    if leg_id:
        target = str(leg_id)
        return next((leg for leg in ticket.legs if leg.id == target), None)
    if event_label:
        target = str(event_label).strip().casefold()
        return next(
            (
                leg
                for leg in ticket.legs
                if (leg.event_label or "").strip().casefold() == target
            ),
            None,
        )
    return None


def target_leg_ids(ticket: Ticket, args: dict) -> set[str]:
    ids = {str(item) for item in args.get("leg_ids", [])}
    events = {str(item).strip().casefold() for item in args.get("events", [])}
    for leg in ticket.legs:
        if (leg.event_label or "").strip().casefold() in events:
            ids.add(leg.id)
    if not ids:
        raise ValueError("Specify leg_ids or event names.")
    return ids
