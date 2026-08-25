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
    """Translate bookmaker labels into one plain Sabi vocabulary.

    User-facing output is explicit, uses decimal-style lines and avoids American
    betting terminology.
    """

    _space = re.compile(r"\s+")
    _signed_line = re.compile(r"(?P<number>[+-]\d+(?:\.\d+)?)")
    _number = re.compile(r"(?P<number>\d+(?:\.\d+)?)")
    _ou = re.compile(r"\b(over|under|o|u)\s*([0-9]+(?:\.[0-9]+)?)\b", re.I)

    def interpret(
        self,
        text: str,
        *,
        home: str | None = None,
        away: str | None = None,
    ) -> InterpretedMarket:
        raw = self._clean(text)
        low = raw.casefold()
        period = self._period(low)

        if low in {"1", "home", "home win", "home to win"} and home:
            return InterpretedMarket(
                MarketKind.WINNER,
                self._with_period(f"{home} to win", period),
                side="home",
                participant=home,
                period=period,
            )
        if low in {"2", "away", "away win", "away to win"} and away:
            return InterpretedMarket(
                MarketKind.WINNER,
                self._with_period(f"{away} to win", period),
                side="away",
                participant=away,
                period=period,
            )
        if low in {"x", "draw"}:
            return InterpretedMarket(
                MarketKind.WIN_DRAW_LOSE,
                self._with_period("Draw", period),
                side="draw",
                period=period,
            )

        if low in {"1x", "home or draw"} and home:
            return InterpretedMarket(
                MarketKind.DOUBLE_CHANCE,
                self._with_period(f"{home} or Draw — Double Chance", period),
                side="home_or_draw",
                participant=home,
                period=period,
            )
        if low in {"x2", "draw or away"} and away:
            return InterpretedMarket(
                MarketKind.DOUBLE_CHANCE,
                self._with_period(f"{away} or Draw — Double Chance", period),
                side="away_or_draw",
                participant=away,
                period=period,
            )
        if low in {"12", "home or away", "either team to win"}:
            return InterpretedMarket(
                MarketKind.DOUBLE_CHANCE,
                self._with_period("Either team to win — Double Chance", period),
                side="home_or_away",
                period=period,
            )

        if "both teams to score" in low or low.startswith("btts"):
            yes = not any(token in low for token in (" no", "- no", ": no", "btts no"))
            return InterpretedMarket(
                MarketKind.COUNT,
                self._with_period(f"Both teams to score — {'Yes' if yes else 'No'}", period),
                metric="teams_scoring",
                side="yes" if yes else "no",
                period=period,
            )

        participant, participant_side = self._participant_from_text(raw, home, away)

        ou = self._ou.search(low)
        if ou:
            direction = "Over" if ou.group(1).casefold() in {"over", "o"} else "Under"
            line = Decimal(ou.group(2))
            metric = self._metric(low)
            metric_label = self._metric_label(metric)
            generic_subject = self._subject_before_ou(raw, ou.start(), home, away)
            if participant:
                label = f"{participant} — {direction} {self._line(line)} {metric_label}"
                return InterpretedMarket(
                    MarketKind.TEAM_TOTAL,
                    self._with_period(label, period),
                    metric=metric,
                    line=line,
                    side=direction.casefold(),
                    participant=participant,
                    period=period,
                )
            if generic_subject:
                label = f"{generic_subject} — {direction} {self._line(line)} {metric_label}"
                return InterpretedMarket(
                    MarketKind.PLAYER,
                    self._with_period(label, period),
                    metric=metric,
                    line=line,
                    side=direction.casefold(),
                    participant=generic_subject,
                    period=period,
                )
            kind = MarketKind.SET_FRAME_MAP if metric in {"sets", "maps", "frames"} else MarketKind.TOTAL
            return InterpretedMarket(
                kind,
                self._with_period(f"{direction} {self._line(line)} {metric_label}", period),
                metric=metric,
                line=line,
                side=direction.casefold(),
                period=period,
            )

        if "handicap" in low or self._signed_line.search(low):
            signed = self._signed_line.search(low)
            number = signed or self._number_after_handicap(low)
            if number:
                line = Decimal(number.group("number"))
                participant, participant_side = self._participant_from_text(raw, home, away)
                metric = self._metric(low)
                metric_suffix = ""
                if metric in {"sets", "maps", "frames", "points", "goals"}:
                    metric_suffix = f" {self._metric_label(metric)}"
                if participant:
                    return InterpretedMarket(
                        MarketKind.HANDICAP,
                        self._with_period(f"{participant} {self._signed(line)}{metric_suffix} handicap", period),
                        metric=metric if metric != "total" else None,
                        line=line,
                        side=participant_side,
                        participant=participant,
                        period=period,
                    )
                return InterpretedMarket(
                    MarketKind.HANDICAP,
                    self._with_period(f"Handicap {self._signed(line)}", period),
                    line=line,
                    period=period,
                    understood=False,
                    reason="The handicap line is clear, but the team or player is not.",
                )

        participant, participant_side = self._participant_from_text(raw, home, away)
        if participant and any(word in low for word in {"win", "winner", "to win"}):
            return InterpretedMarket(
                MarketKind.WINNER,
                self._with_period(f"{participant} to win", period),
                side=participant_side,
                participant=participant,
                period=period,
            )

        if any(word in low for word in ("set winner", "map winner", "frame winner")):
            return InterpretedMarket(
                MarketKind.SET_FRAME_MAP,
                self._with_period(raw, period),
                period=period,
                understood=False,
                reason="The set, map or frame market is clear, but the participant needs to be identified.",
            )

        return InterpretedMarket(
            MarketKind.OTHER,
            raw,
            period=period,
            understood=False,
            reason="This market needs a bookmaker-specific mapping or more context.",
        )

    def _clean(self, text: str) -> str:
        return self._space.sub(" ", (text or "").strip())

    def _metric(self, low: str) -> str:
        aliases = (
            ("shots on target", "shots_on_target"),
            ("three pointers", "three_pointers"),
            ("3 pointers", "three_pointers"),
            ("3-pointers", "three_pointers"),
            ("double faults", "double_faults"),
            ("break points", "break_points"),
            ("home runs", "home_runs"),
            ("significant strikes", "significant_strikes"),
            ("corners", "corners"),
            ("cards", "cards"),
            ("shots", "shots"),
            ("goals", "goals"),
            ("points", "points"),
            ("sets", "sets"),
            ("games", "games"),
            ("aces", "aces"),
            ("rebounds", "rebounds"),
            ("assists", "assists"),
            ("maps", "maps"),
            ("frames", "frames"),
            ("runs", "runs"),
            ("wickets", "wickets"),
            ("kills", "kills"),
            ("blocks", "blocks"),
            ("steals", "steals"),
            ("fouls", "fouls"),
            ("offsides", "offsides"),
            ("tries", "tries"),
            ("touchdowns", "touchdowns"),
            ("strikeouts", "strikeouts"),
            ("saves", "saves"),
        )
        for phrase, key in aliases:
            if phrase in low:
                return key
        return "total"

    @staticmethod
    def _metric_label(metric: str) -> str:
        return metric.replace("_", " ")

    def _participant_from_text(self, raw: str, home: str | None, away: str | None) -> tuple[str | None, str | None]:
        low = raw.casefold()
        if home and home.casefold() in low:
            return home, "home"
        if away and away.casefold() in low:
            return away, "away"
        if home and re.search(r"(^home\b|\bhandicap\s*1\b|\bteam\s*1\b|\bhome team\b)", low):
            return home, "home"
        if away and re.search(r"(^away\b|\bhandicap\s*2\b|\bteam\s*2\b|\baway team\b)", low):
            return away, "away"
        return None, None

    def _subject_before_ou(self, raw: str, ou_start: int, home: str | None, away: str | None) -> str | None:
        prefix = raw[:ou_start].strip(" :-—")
        if not prefix:
            return None
        low = prefix.casefold()
        discard = {
            "total", "match total", "game total", "team total",
            "first half", "second half", "1st half", "2nd half",
            "first quarter", "second quarter", "third quarter", "fourth quarter",
            "1st quarter", "2nd quarter", "3rd quarter", "4th quarter",
        }
        if low in discard:
            return None
        if home and home.casefold() == low:
            return None
        if away and away.casefold() == low:
            return None
        if re.fullmatch(r"(set|map|frame|quarter|period)\s*\d+", low):
            return None
        return prefix

    @staticmethod
    def _number_after_handicap(low: str):
        return re.search(r"handicap(?:\s+[12])?\s*(?P<number>-?\d+(?:\.\d+)?)", low)

    @staticmethod
    def _line(line: Decimal) -> str:
        return str(line.normalize())

    @staticmethod
    def _signed(line: Decimal) -> str:
        value = f"{line:+}"
        return value.rstrip("0").rstrip(".") if "." in value else value

    def _period(self, low: str) -> str:
        patterns = (
            (r"\b(first|1st)\s+half\b|\b1h\b", "first_half"),
            (r"\b(second|2nd)\s+half\b|\b2h\b", "second_half"),
            (r"\b(first|1st)\s+quarter\b|\bq1\b", "first_quarter"),
            (r"\b(second|2nd)\s+quarter\b|\bq2\b", "second_quarter"),
            (r"\b(third|3rd)\s+quarter\b|\bq3\b", "third_quarter"),
            (r"\b(fourth|4th)\s+quarter\b|\bq4\b", "fourth_quarter"),
            (r"\b(first|1st)\s+set\b|\bset\s*1\b", "set_1"),
            (r"\b(second|2nd)\s+set\b|\bset\s*2\b", "set_2"),
            (r"\b(third|3rd)\s+set\b|\bset\s*3\b", "set_3"),
            (r"\b(first|1st)\s+map\b|\bmap\s*1\b", "map_1"),
            (r"\b(second|2nd)\s+map\b|\bmap\s*2\b", "map_2"),
            (r"\b(first|1st)\s+period\b|\bperiod\s*1\b", "period_1"),
            (r"\b(second|2nd)\s+period\b|\bperiod\s*2\b", "period_2"),
            (r"\b(third|3rd)\s+period\b|\bperiod\s*3\b", "period_3"),
        )
        for pattern, key in patterns:
            if re.search(pattern, low):
                return key
        return "full_event"

    @staticmethod
    def _period_label(period: str) -> str:
        labels = {
            "first_half": "First half", "second_half": "Second half",
            "first_quarter": "First quarter", "second_quarter": "Second quarter",
            "third_quarter": "Third quarter", "fourth_quarter": "Fourth quarter",
            "set_1": "Set 1", "set_2": "Set 2", "set_3": "Set 3",
            "map_1": "Map 1", "map_2": "Map 2",
            "period_1": "Period 1", "period_2": "Period 2", "period_3": "Period 3",
        }
        return labels.get(period, "")

    def _with_period(self, label: str, period: str) -> str:
        if period == "full_event":
            return label
        prefix = self._period_label(period)
        if label.casefold().startswith(prefix.casefold()):
            return label
        return f"{prefix} — {label}"
