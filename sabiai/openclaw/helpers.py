from __future__ import annotations

from sabiai.domain.models import Ticket, TicketLeg


def ticket_from_args(app, args: dict) -> Ticket:
    normalized = app.ticket_normalizer.normalize(
        args.get("legs", []),
        bookmaker=args.get("bookmaker"),
        source_type=str(args.get("source_type", "instruction")),
        source_reference=args.get("source_reference"),
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
