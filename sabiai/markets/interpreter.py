from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import re

from sabiai.domain.types import MarketKind


@dataclass(slots=True)
class InterpretedMarket:
    kind: MarketKind
    plain_label: str
    metric: str | None = None
    line: Decimal | None = None
    side: str | None = None
    participant: str | None = None
    period: str = "full_event"
    understood: bool = True
    reason: str | None = None


class MarketInterpreter:
    """Translate common bookmaker labels into one plain Sabi vocabulary.

    It deliberately avoids American-facing output terms such as "moneyline".
    """

    _space = re.compile(r"\s+")
    _number = re.compile(r"(?P<number>[+-]?\d+(?:\.\d+)?)")

    def interpret(
        self,
        text: str,
        *,
        home: str | None = None,
        away: str | None = None,
    ) -> InterpretedMarket:
        raw = self._clean(text)
        low = raw.casefold()

        if low in {"1", "home", "home win", "home to win"} and home:
            return InterpretedMarket(MarketKind.WINNER, f"{home} to win", side="home", participant=home)
        if low in {"2", "away", "away win", "away to win"} and away:
            return InterpretedMarket(MarketKind.WINNER, f"{away} to win", side="away", participant=away)
        if low in {"x", "draw"}:
            return InterpretedMarket(MarketKind.WIN_DRAW_LOSE, "Draw", side="draw")

        if low in {"1x", "home or draw"} and home:
            return InterpretedMarket(MarketKind.DOUBLE_CHANCE, f"{home} or Draw — Double Chance", side="home_or_draw", participant=home)
        if low in {"x2", "draw or away"} and away:
            return InterpretedMarket(MarketKind.DOUBLE_CHANCE, f"{away} or Draw — Double Chance", side="away_or_draw", participant=away)
        if low in {"12", "home or away", "either team to win"}:
            return InterpretedMarket(MarketKind.DOUBLE_CHANCE, "Either team to win — Double Chance", side="home_or_away")

        if "both teams to score" in low or low.startswith("btts"):
            yes = not any(word in low for word in {" no", "- no", ": no"})
            return InterpretedMarket(MarketKind.COUNT, f"Both teams to score — {'Yes' if yes else 'No'}", metric="teams_scoring", side="yes" if yes else "no")

        ou = re.search(r"\b(over|under|o|u)\s*([0-9]+(?:\.[0-9]+)?)", low)
        if ou:
            direction = "Over" if ou.group(1) in {"over", "o"} else "Under"
            line = Decimal(ou.group(2))
            metric = self._metric(low)
            return InterpretedMarket(MarketKind.TOTAL, f"{direction} {line.normalize()} {self._metric_label(metric)}".strip(), metric=metric, line=line, side=direction.casefold())

        if "handicap" in low or re.search(r"[+-]\d+(?:\.\d+)?", low):
            number = self._number.search(low)
            if number:
                line = Decimal(number.group("number"))
                participant, side = self._participant_from_text(raw, home, away)
                if participant:
                    return InterpretedMarket(MarketKind.HANDICAP, f"{participant} {line:+} handicap", line=line, side=side, participant=participant)
                return InterpretedMarket(MarketKind.HANDICAP, f"Handicap {line:+}", line=line, understood=False, reason="The handicap line is clear, but the team or player is not.")

        participant, side = self._participant_from_text(raw, home, away)
        if participant and any(word in low for word in {"win", "winner", "to win"}):
            return InterpretedMarket(MarketKind.WINNER, f"{participant} to win", side=side, participant=participant)

        return InterpretedMarket(MarketKind.OTHER, raw, understood=False, reason="This market needs a bookmaker-specific mapping or more context.")

    def _clean(self, text: str) -> str:
        return self._space.sub(" ", (text or "").strip())

    def _metric(self, low: str) -> str:
        for key in ("corners", "cards", "shots on target", "shots", "goals", "points", "sets", "games", "aces", "rebounds", "assists", "maps", "frames", "runs", "wickets"):
            if key in low:
                return key.replace(" ", "_")
        return "total"

    def _metric_label(self, metric: str) -> str:
        return metric.replace("_", " ")

    def _participant_from_text(self, raw: str, home: str | None, away: str | None) -> tuple[str | None, str | None]:
        low = raw.casefold()
        if home and home.casefold() in low:
            return home, "home"
        if away and away.casefold() in low:
            return away, "away"
        return None, None
