from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Iterable

from sabiai.bookmakers import BookmakerRegistry, default_bookmakers
from sabiai.domain.models import Market, Selection, Ticket, TicketLeg
from sabiai.markets import MarketInterpreter


@dataclass(frozen=True, slots=True)
class TicketIssue:
    leg_no: int | None
    level: str
    message: str
    event: str | None = None


@dataclass(slots=True)
class TicketNormalization:
    ticket: Ticket
    issues: list[TicketIssue] = field(default_factory=list)

    @property
    def usable(self) -> bool:
        return bool(self.ticket.legs) and not any(issue.level == "error" for issue in self.issues)


class TicketNormalizer:
    """Turn extracted slip data into one canonical, explicit V2 ticket.

    Screenshot/X/browser work should extract visible information first, then hand the
    structured legs here. This keeps bookmaker/browser quirks outside ticket rules.
    """

    def __init__(
        self,
        bookmakers: BookmakerRegistry | None = None,
        interpreter: MarketInterpreter | None = None,
    ):
        self.bookmakers = bookmakers or default_bookmakers()
        self.interpreter = interpreter or MarketInterpreter()

    def normalize(
        self,
        legs: Iterable[dict],
        *,
        bookmaker: str | None = None,
        source_type: str = "instruction",
        source_reference: str | None = None,
    ) -> TicketNormalization:
        issues: list[TicketIssue] = []
        bookmaker_id = None
        if bookmaker:
            resolved = self.bookmakers.resolve(bookmaker)
            if resolved:
                bookmaker_id = resolved.id
            else:
                issues.append(
                    TicketIssue(
                        leg_no=None,
                        level="warning",
                        message=f"Bookmaker '{bookmaker}' is not in the canonical registry yet.",
                    )
                )

        ticket = Ticket(
            bookmaker_id=bookmaker_id,
            source_type=source_type,
            source_reference=source_reference,
        )
        seen: set[tuple[str, str]] = set()

        for index, raw in enumerate(legs, start=1):
            home = self._text(raw.get("home"))
            away = self._text(raw.get("away"))
            event_label = self._text(raw.get("event") or raw.get("match"))
            if not event_label and home and away:
                event_label = f"{home} vs {away}"
            if not event_label:
                issues.append(
                    TicketIssue(
                        leg_no=index,
                        level="error",
                        message="The match or event name is missing.",
                    )
                )
                continue

            market_text = self._text(raw.get("market") or raw.get("pick"))
            if not market_text:
                issues.append(
                    TicketIssue(
                        leg_no=index,
                        level="error",
                        event=event_label,
                        message="The selection/market is missing.",
                    )
                )
                continue

            parsed = self.interpreter.interpret(market_text, home=home, away=away)
            if not parsed.understood:
                issues.append(
                    TicketIssue(
                        leg_no=index,
                        level="warning",
                        event=event_label,
                        message=parsed.reason or "The market needs more context.",
                    )
                )

            try:
                odds = Decimal(str(raw["odds"]))
            except Exception:
                issues.append(
                    TicketIssue(
                        leg_no=index,
                        level="error",
                        event=event_label,
                        message="Decimal odds are missing or invalid.",
                    )
                )
                continue

            market = Market(
                kind=parsed.kind,
                label=parsed.plain_label,
                metric=parsed.metric,
                line=parsed.line,
                period=parsed.period,
            )
            selection = Selection(
                market_id=market.id,
                label=parsed.plain_label,
                side=parsed.side,
            )
            leg = TicketLeg(
                event_id=str(raw.get("event_id") or f"draft_event_{index}"),
                event_label=event_label,
                market=market,
                selection=selection,
                odds=odds,
                bookmaker_id=bookmaker_id,
                locked=bool(raw.get("locked", False)),
                note=self._text(raw.get("note")),
                **({"id": str(raw["id"])} if raw.get("id") else {}),
            )

            duplicate_key = (
                event_label.casefold().strip(),
                parsed.plain_label.casefold().strip(),
            )
            if duplicate_key in seen:
                issues.append(
                    TicketIssue(
                        leg_no=index,
                        level="warning",
                        event=event_label,
                        message=f"Duplicate selection detected: {parsed.plain_label}.",
                    )
                )
            else:
                seen.add(duplicate_key)

            ticket.add_leg(leg)

        if not ticket.legs:
            issues.append(
                TicketIssue(
                    leg_no=None,
                    level="error",
                    message="No usable ticket legs were found.",
                )
            )

        return TicketNormalization(ticket=ticket, issues=issues)

    @staticmethod
    def _text(value) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None
