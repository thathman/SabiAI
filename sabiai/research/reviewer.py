from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from .case import ResearchAssessment


@dataclass(frozen=True, slots=True)
class ReviewQuestion:
    area: str
    question: str


@dataclass(frozen=True, slots=True)
class SkepticReviewPlan:
    required: bool
    triggers: tuple[str, ...]
    questions: tuple[ReviewQuestion, ...]


class SkepticReviewPlanner:
    """Decide when Sabi Boy should deliberately try to disprove his first conclusion."""

    def plan(
        self,
        assessment: ResearchAssessment,
        *,
        ticket_legs: int = 0,
        stake: object | None = None,
        bankroll: object | None = None,
        bookmaker_conversion: bool = False,
        arbitrage: bool = False,
        single_source_case: bool = False,
        user_asked_strongest: bool = False,
    ) -> SkepticReviewPlan:
        triggers: list[str] = []
        if assessment.skeptic_required:
            triggers.append("research case is incomplete, conflicted or unfamiliar")
        if ticket_legs >= 6:
            triggers.append(f"ticket has {ticket_legs} legs")
        if bookmaker_conversion:
            triggers.append("ticket is being converted between bookmakers")
        if arbitrage:
            triggers.append("all outcome prices and settlement rules must match exactly")
        if single_source_case:
            triggers.append("important conclusion depends on one source")
        if user_asked_strongest:
            triggers.append("user asked for strongest/lower-risk selections")

        stake_pct = self._stake_pct(stake, bankroll)
        if stake_pct is not None and stake_pct >= Decimal("5"):
            triggers.append(f"stake is {stake_pct:.1f}% of recorded bankroll")

        questions = [
            ReviewQuestion("identity", "Am I definitely looking at the correct event, teams/players and competition?"),
            ReviewQuestion("market", "Is the selection, line, period and settlement meaning exactly what I think it is?"),
            ReviewQuestion("freshness", "Could any injury, lineup, roster, price or schedule information have changed?"),
            ReviewQuestion("evidence", "What is the strongest evidence against my current view?"),
            ReviewQuestion("sample", "Am I leaning too heavily on a short streak or a weak head-to-head sample?"),
        ]

        if assessment.conflicts:
            questions.append(
                ReviewQuestion("conflict", "Which conflicting source is fresher or more authoritative, and why?")
            )
        if ticket_legs > 1:
            questions.extend(
                [
                    ReviewQuestion("ticket", "Are multiple legs depending on the same team, match story or correlated outcome?"),
                    ReviewQuestion("ticket", "Which single leg is most likely to kill this ticket, and should it be removed or changed?"),
                ]
            )
        if bookmaker_conversion:
            questions.append(
                ReviewQuestion("conversion", "Did every converted leg keep the exact event, market, line, period and side?")
            )
        if arbitrage:
            questions.extend(
                [
                    ReviewQuestion("price", "Are all quoted prices still available and fresh enough to act on?"),
                    ReviewQuestion("rules", "Do all books settle every leg under compatible rules, including overtime/void/dead-heat cases?"),
                ]
            )
        if stake_pct is not None:
            questions.append(
                ReviewQuestion("bankroll", f"Is this stake sensible relative to the recorded bankroll ({stake_pct:.1f}%)?")
            )

        questions.append(
            ReviewQuestion("abstention", "After trying to disprove it, is PASS or WAIT better than forcing an action?")
        )

        return SkepticReviewPlan(
            required=bool(triggers),
            triggers=tuple(dict.fromkeys(triggers)),
            questions=tuple(questions),
        )

    @staticmethod
    def _stake_pct(stake: object | None, bankroll: object | None) -> Decimal | None:
        if stake is None or bankroll is None:
            return None
        try:
            stake_value = Decimal(str(stake))
            bankroll_value = Decimal(str(bankroll))
        except (InvalidOperation, TypeError, ValueError):
            return None
        if stake_value < 0 or bankroll_value <= 0:
            return None
        return (stake_value / bankroll_value * Decimal("100")).quantize(Decimal("0.1"))
