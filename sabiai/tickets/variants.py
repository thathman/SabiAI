from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import re

from sabiai.domain.models import Ticket, TicketLeg
from sabiai.domain.types import MarketKind

from .workshop import TicketWorkshop, TicketWorkshopError


@dataclass(frozen=True, slots=True)
class RankedLeg:
    leg_id: str
    event: str
    selection: str
    score: float
    reason: str | None = None
    locked: bool = False


@dataclass(frozen=True, slots=True)
class MarketChangeSuggestion:
    leg_id: str
    event: str
    current_selection: str
    suggested_market: str | None
    reason: str
    requires_price_check: bool = True


class TicketVariantPlanner:
    """Plan ticket variants without pretending bookmaker prices are already known."""

    def __init__(self, workshop: TicketWorkshop | None = None):
        self.workshop = workshop or TicketWorkshop()

    def strongest(
        self,
        ticket: Ticket,
        scores: dict[str, tuple[float, str | None]],
        *,
        count: int,
    ) -> tuple[Ticket, list[RankedLeg]]:
        if count < 1:
            raise TicketWorkshopError("Strongest-N count must be at least 1.")
        if count > len(ticket.legs):
            raise TicketWorkshopError("Strongest-N count exceeds the ticket size.")

        locked = [leg for leg in ticket.legs if leg.locked]
        if len(locked) > count:
            raise TicketWorkshopError("Requested count is smaller than the number of locked legs.")

        ranked: list[RankedLeg] = []
        missing: list[str] = []
        for leg in ticket.legs:
            value = scores.get(leg.id)
            if value is None and leg.event_label:
                value = scores.get(leg.event_label.strip().casefold())
            if value is None:
                missing.append(leg.event_label or leg.id)
                continue
            score, reason = value
            if not 0 <= float(score) <= 100:
                raise TicketWorkshopError("Strength scores must be between 0 and 100.")
            ranked.append(
                RankedLeg(
                    leg_id=leg.id,
                    event=leg.event_label or leg.event_id,
                    selection=leg.selection.label,
                    score=float(score),
                    reason=reason,
                    locked=leg.locked,
                )
            )
        if missing:
            raise TicketWorkshopError(
                "Research strength is missing for: " + ", ".join(missing)
            )

        locked_ids = {leg.id for leg in locked}
        optional = sorted(
            (row for row in ranked if row.leg_id not in locked_ids),
            key=lambda row: (-row.score, row.event.casefold(), row.leg_id),
        )
        keep_ids = locked_ids | {
            row.leg_id for row in optional[: max(0, count - len(locked_ids))]
        }
        child = self.workshop.keep_only(ticket, keep_ids)
        child.source_type = "strongest"
        child.notes.append(
            f"Kept the {count} strongest researched leg(s), preserving locked selections."
        )
        return child, sorted(ranked, key=lambda row: (-row.score, row.event.casefold()))

    def lower_risk_plan(self, ticket: Ticket) -> list[MarketChangeSuggestion]:
        return [self._lower_risk(leg) for leg in ticket.legs]

    def _lower_risk(self, leg: TicketLeg) -> MarketChangeSuggestion:
        market = leg.market
        label = leg.selection.label.strip()
        event = leg.event_label or leg.event_id
        side = (leg.selection.side or "").casefold()

        if market.kind is MarketKind.WIN_DRAW_LOSE:
            team = self._winner_team(label)
            if team and side != "draw":
                return MarketChangeSuggestion(
                    leg.id,
                    event,
                    label,
                    f"{team} or Draw — Double Chance",
                    "Keeps the named team covered by both a win and a draw.",
                )

        if market.kind is MarketKind.DOUBLE_CHANCE:
            return MarketChangeSuggestion(
                leg.id,
                event,
                label,
                None,
                "This selection is already a broader double-chance outcome; do not weaken it automatically without researching another market.",
                False,
            )

        if market.kind in {MarketKind.TOTAL, MarketKind.TEAM_TOTAL, MarketKind.COUNT, MarketKind.PLAYER}:
            if market.line is not None:
                direction = self._direction(label, side)
                if direction == "over":
                    new_line = self._step_line(market.line, -Decimal("1.0"))
                    metric = (market.metric or "").replace("_", " ").strip()
                    prefix = self._entity_prefix(label, direction)
                    return MarketChangeSuggestion(
                        leg.id,
                        event,
                        label,
                        f"{prefix}Over {new_line}{f' {metric}' if metric else ''}".strip(),
                        "Moves an Over selection to a lower line while keeping the same direction.",
                    )
                if direction == "under":
                    new_line = self._step_line(market.line, Decimal("1.0"))
                    metric = (market.metric or "").replace("_", " ").strip()
                    prefix = self._entity_prefix(label, direction)
                    return MarketChangeSuggestion(
                        leg.id,
                        event,
                        label,
                        f"{prefix}Under {new_line}{f' {metric}' if metric else ''}".strip(),
                        "Moves an Under selection to a higher line while keeping the same direction.",
                    )

        if market.kind is MarketKind.HANDICAP and market.line is not None:
            team = self._handicap_team(label)
            if team:
                new_line = market.line + Decimal("1.0")
                return MarketChangeSuggestion(
                    leg.id,
                    event,
                    label,
                    f"{team} {self._signed(new_line)} handicap",
                    "Moves the handicap one step further in the named team's favour.",
                )

        return MarketChangeSuggestion(
            leg.id,
            event,
            label,
            None,
            "No generic lower-risk rewrite is trustworthy for this market; research a specific alternative instead.",
            False,
        )

    @staticmethod
    def _winner_team(label: str) -> str | None:
        match = re.match(r"^(.+?)\s+to win$", label, re.I)
        return match.group(1).strip() if match else None

    @staticmethod
    def _handicap_team(label: str) -> str | None:
        match = re.match(r"^(.+?)\s+[+-]?\d+(?:\.\d+)?\s+handicap$", label, re.I)
        return match.group(1).strip() if match else None

    @staticmethod
    def _direction(label: str, side: str) -> str | None:
        if side in {"over", "under"}:
            return side
        low = label.casefold()
        if " over " in f" {low} " or low.startswith("over "):
            return "over"
        if " under " in f" {low} " or low.startswith("under "):
            return "under"
        return None

    @staticmethod
    def _entity_prefix(label: str, direction: str) -> str:
        match = re.match(rf"^(.+?)\s+{direction}\s+", label, re.I)
        return f"{match.group(1).strip()} — " if match else ""

    @staticmethod
    def _step_line(line: Decimal, amount: Decimal) -> Decimal:
        result = line + amount
        return max(result, Decimal("0.5"))

    @staticmethod
    def _signed(line: Decimal) -> str:
        text = str(line.normalize())
        return f"+{text}" if line >= 0 else text
