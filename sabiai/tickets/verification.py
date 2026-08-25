from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from sabiai.domain.aliases import normalize_name
from sabiai.domain.models import Ticket, TicketLeg


@dataclass(frozen=True, slots=True)
class RebuiltLegVerification:
    expected_leg_id: str
    event: str
    expected_selection: str
    expected_odds: Decimal
    status: str
    reason: str
    restored_selection: str | None = None
    restored_odds: Decimal | None = None
    price_changed: bool = False


@dataclass(slots=True)
class RebuiltTicketVerification:
    expected_ticket_id: str
    restored_ticket_id: str
    legs: list[RebuiltLegVerification] = field(default_factory=list)
    extra_restored_legs: list[str] = field(default_factory=list)

    @property
    def structure_verified(self) -> bool:
        return bool(self.legs) and all(row.status == "matched" for row in self.legs) and not self.extra_restored_legs

    @property
    def prices_changed(self) -> bool:
        return any(row.price_changed for row in self.legs)

    @property
    def ready_to_return_code(self) -> bool:
        return self.structure_verified


class RebuiltTicketVerificationService:
    """Verify a booking code restored after building matches the planned ticket exactly.

    Market/event structure is strict. Decimal prices are compared but may legitimately move
    between discovery, build and reload; price movement is surfaced separately from a wrong
    event/market reconstruction.
    """

    def verify(self, expected: Ticket, restored: Ticket) -> RebuiltTicketVerification:
        result = RebuiltTicketVerification(
            expected_ticket_id=expected.id,
            restored_ticket_id=restored.id,
        )
        unmatched = list(restored.legs)
        for expected_leg in expected.legs:
            match_index = next(
                (index for index, candidate in enumerate(unmatched) if self._same_structure(expected_leg, candidate)),
                None,
            )
            event = expected_leg.event_label or expected_leg.event_id
            if match_index is None:
                result.legs.append(
                    RebuiltLegVerification(
                        expected_leg_id=expected_leg.id,
                        event=event,
                        expected_selection=expected_leg.selection.label,
                        expected_odds=expected_leg.odds,
                        status="missing",
                        reason="The rebuilt booking code does not contain this exact event/market/selection.",
                    )
                )
                continue

            actual = unmatched.pop(match_index)
            changed = actual.odds != expected_leg.odds
            result.legs.append(
                RebuiltLegVerification(
                    expected_leg_id=expected_leg.id,
                    event=event,
                    expected_selection=expected_leg.selection.label,
                    expected_odds=expected_leg.odds,
                    status="matched",
                    reason=(
                        "Exact event/market/selection verified; the bookmaker price changed while rebuilding."
                        if changed
                        else "Exact event/market/selection and decimal price verified."
                    ),
                    restored_selection=actual.selection.label,
                    restored_odds=actual.odds,
                    price_changed=changed,
                )
            )

        result.extra_restored_legs = [
            f"{leg.event_label or leg.event_id} — {leg.selection.label}"
            for leg in unmatched
        ]
        return result

    def _same_structure(self, expected: TicketLeg, actual: TicketLeg) -> bool:
        if not self._same_event(expected, actual):
            return False
        if expected.market.kind != actual.market.kind:
            return False
        if (expected.market.metric or None) != (actual.market.metric or None):
            return False
        if expected.market.line != actual.market.line:
            return False
        if expected.market.period != actual.market.period:
            return False
        if expected.selection.side and expected.selection.side != actual.selection.side:
            return False
        # Labels remain a final safety check for named participants/player props where a
        # structural side such as 'over' alone would be insufficient.
        expected_label = normalize_name(expected.selection.label)
        actual_label = normalize_name(actual.selection.label)
        if expected_label == actual_label:
            return True
        expected_participant = normalize_name(expected.market.participant_id or "")
        actual_participant = normalize_name(actual.market.participant_id or "")
        if expected_participant or actual_participant:
            return bool(expected_participant and expected_participant == actual_participant)
        return False

    @staticmethod
    def _same_event(expected: TicketLeg, actual: TicketLeg) -> bool:
        left = normalize_name(expected.event_label or expected.event_id)
        right = normalize_name(actual.event_label or actual.event_id)
        if left != right:
            return False
        if expected.sport and actual.sport and normalize_name(expected.sport) != normalize_name(actual.sport):
            return False
        return True
