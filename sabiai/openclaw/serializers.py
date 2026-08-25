from __future__ import annotations

from dataclasses import asdict, is_dataclass
from decimal import Decimal
from enum import Enum

from sabiai.domain.models import Ticket


def json_value(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {key: json_value(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_value(item) for item in value]
    return value


def ticket_to_dict(ticket: Ticket) -> dict:
    return {
        "id": ticket.id,
        "parent_ticket_id": ticket.parent_ticket_id,
        "source_type": ticket.source_type,
        "source_reference": ticket.source_reference,
        "combined_odds": str(ticket.combined_odds),
        "legs": [
            {
                "id": leg.id,
                "event_id": leg.event_id,
                "event": leg.event_label,
                "sport": leg.sport,
                "market": leg.market.label,
                "pick": leg.selection.label,
                "odds": str(leg.odds),
                "locked": leg.locked,
            }
            for leg in ticket.legs
        ],
        "notes": list(ticket.notes),
    }


def draft_to_dict(draft) -> dict:
    return {
        "id": draft.id,
        "parent_draft_id": draft.parent_draft_id,
        "source_type": draft.source_type,
        "source_reference": draft.source_reference,
        "source_bookmaker_slug": draft.source_bookmaker_slug,
        "target_bookmaker_slug": draft.target_bookmaker_slug,
        "status": draft.status,
        "payload": draft.payload,
        "issues": draft.issues,
        "created_at": draft.created_at,
        "updated_at": draft.updated_at,
    }


def ledger_to_dict(entry) -> dict:
    return {
        "id": entry.id,
        "occurred_at": entry.occurred_at,
        "kind": entry.kind,
        "amount": str(entry.amount),
        "balance_after": str(entry.balance_after) if entry.balance_after is not None else None,
        "pick_id": entry.pick_id,
        "ticket_id": entry.ticket_id,
        "legacy_bet_id": entry.legacy_bet_id,
        "note": entry.note,
    }


def arbitrage_to_dict(result) -> dict:
    return {
        "found": result.found,
        "reason": result.reason,
        "event_key": result.event_key,
        "market_key": result.market_key,
        "implied_total_pct": str(result.implied_total_pct) if result.implied_total_pct is not None else None,
        "profit_pct": str(result.profit_pct) if result.profit_pct is not None else None,
        "total_stake": str(result.total_stake) if result.total_stake is not None else None,
        "locked_return": str(result.locked_return) if result.locked_return is not None else None,
        "locked_profit": str(result.locked_profit) if result.locked_profit is not None else None,
        "prices": [
            {
                "selection": quote.selection_label,
                "bookmaker": quote.bookmaker,
                "odds": str(quote.odds),
                "period": quote.rules.period,
                "includes_overtime": quote.rules.includes_overtime,
                "void_rule": quote.rules.void_rule,
                "line_key": quote.rules.line_key,
            }
            for quote in result.quotes
        ],
        "stake_split": [
            {
                "selection": row.selection_label,
                "bookmaker": row.bookmaker,
                "odds": str(row.odds),
                "stake": str(row.stake),
                "return": str(row.expected_return),
            }
            for row in result.allocations
        ],
    }


def conversion_to_dict(plan) -> dict:
    return {
        "ready": plan.ready,
        "source_ticket_id": plan.source_ticket_id,
        "source_bookmaker": plan.source_bookmaker_slug,
        "target_bookmaker": plan.target_bookmaker_slug,
        "missing_count": plan.missing_count,
        "legs": [
            {
                "source_leg_id": leg.source_leg_id,
                "source_event": leg.source_event,
                "source_selection": leg.source_selection,
                "source_odds": str(leg.source_odds),
                "status": leg.status,
                "reason": leg.reason,
                "target_event": leg.target_event,
                "target_selection": leg.target_selection,
                "target_odds": str(leg.target_odds) if leg.target_odds is not None else None,
                "target_event_ref": leg.target_event_ref,
                "target_market_ref": leg.target_market_ref,
            }
            for leg in plan.legs
        ],
        "target_ticket": ticket_to_dict(plan.target_ticket) if plan.target_ticket is not None else None,
        "notes": list(plan.notes),
    }
