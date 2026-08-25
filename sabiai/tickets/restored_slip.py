from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from sabiai.domain.models import Ticket

from .normalize import TicketIssue, TicketNormalizer


@dataclass(slots=True)
class RestoredSlipNormalization:
    bookmaker: str
    booking_code: str
    ticket: Ticket
    issues: list[TicketIssue]
    reported_leg_count: int | None
    reported_combined_odds: Decimal | None
    computed_combined_odds: Decimal
    combined_odds_match: bool | None

    @property
    def usable(self) -> bool:
        return bool(self.ticket.legs) and not any(issue.level == "error" for issue in self.issues)


class RestoredSlipService:
    """Validate a booking slip extracted by a controlled browser before ticket work.

    Browser/vision code is allowed to extract visible fields, but this service decides whether
    that extraction is complete enough to trust as the source ticket.
    """

    def __init__(self, normalizer: TicketNormalizer):
        self.normalizer = normalizer

    def normalize(self, *, bookmaker: str, booking_code: str, payload: dict) -> RestoredSlipNormalization:
        if not isinstance(payload, dict):
            raise ValueError("Restored booking slip payload must be one object.")
        code = str(booking_code or "").strip()
        if not code:
            raise ValueError("Restored booking slip needs the original booking code.")
        legs = payload.get("legs")
        if not isinstance(legs, list):
            raise ValueError("Restored booking slip payload needs a legs list.")

        normalized = self.normalizer.normalize(
            legs,
            bookmaker=bookmaker,
            source_type="booking_code",
            source_reference=f"{bookmaker}:{code}",
        )
        issues = list(normalized.issues)

        reported_count = self._optional_int(
            payload.get("leg_count") if payload.get("leg_count") is not None else payload.get("legs_count")
        )
        if reported_count is not None and reported_count != len(legs):
            issues.append(
                TicketIssue(
                    leg_no=None,
                    level="error",
                    message=(
                        f"Restored slip says it has {reported_count} leg(s), but only {len(legs)} were extracted. "
                        "Re-read the bookmaker slip before editing or converting it."
                    ),
                )
            )

        reported_odds = self._optional_decimal(
            payload.get("combined_odds") if payload.get("combined_odds") is not None else payload.get("total_odds")
        )
        computed = normalized.ticket.combined_odds
        odds_match: bool | None = None
        if reported_odds is not None and normalized.ticket.legs:
            tolerance = max(Decimal("0.02"), reported_odds * Decimal("0.002"))
            odds_match = abs(reported_odds - computed) <= tolerance
            if not odds_match:
                issues.append(
                    TicketIssue(
                        leg_no=None,
                        level="warning",
                        message=(
                            f"Bookmaker displayed combined odds {reported_odds}, while the extracted leg prices multiply to {computed}. "
                            "Check for a boost, changed price or missed leg before rebuilding."
                        ),
                    )
                )

        return RestoredSlipNormalization(
            bookmaker=bookmaker,
            booking_code=code,
            ticket=normalized.ticket,
            issues=issues,
            reported_leg_count=reported_count,
            reported_combined_odds=reported_odds,
            computed_combined_odds=computed,
            combined_odds_match=odds_match,
        )

    @staticmethod
    def _optional_int(value) -> int | None:
        if value is None or value == "":
            return None
        try:
            result = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("Reported leg count must be an integer.") from exc
        if result < 0:
            raise ValueError("Reported leg count cannot be negative.")
        return result

    @staticmethod
    def _optional_decimal(value) -> Decimal | None:
        if value is None or value == "":
            return None
        try:
            result = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise ValueError("Reported combined odds must be decimal odds.") from exc
        if result < Decimal("1"):
            raise ValueError("Reported combined odds must be at least 1.00.")
        return result
