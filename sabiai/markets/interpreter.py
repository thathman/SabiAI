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

        double_chance = re.sub(
            r"\s*(?:—|-|:)?\s*double\s+chance\s*$",
            "",
            low,
        ).strip(" -—:")
        home_name = home.casefold() if home else None
        away_name = away.casefold() if away else None
        if home and double_chance in {
            "1x",
            "home or draw",
            f"{home_name} or draw",
            f"draw or {home_name}",
        }:
            return InterpretedMarket(
                MarketKind.DOUBLE_CHANCE,
                self._with_period(f"{home} or Draw — Double Chance", period),
                side="home_or_draw",
                participant=home,
                period=period,
            )
        if away and double_chance in {
            "x2",
            "draw or away",
            f"{away_name} or draw",
            f"draw or {away_name}",
        }:
            return InterpretedMarket(
                MarketKind.DOUBLE_CHANCE,
                self._with_period(f"{away} or Draw — Double Chance", period),
                side="away_or_draw",
                participant=away,
                period=period,
            )
        if double_chance in {"12", "home or away", "either team to win"}:
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

        dnb = self._draw_no_bet(raw, low, home, away, period)
        if dnb is not None:
            return dnb

        race_field = self._race_field(raw, low, period)
        if race_field is not None:
            return race_field

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

        if "handicap" in low or "spread" in low or self._signed_line.search(low):
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
        if participant and any(word in low for word in {"win", "winner", "to win", "moneyline"}):
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

    def _draw_no_bet(
        self,
        raw: str,
        low: str,
        home: str | None,
        away: str | None,
        period: str,
    ) -> InterpretedMarket | None:
        if not any(token in low for token in ("draw no bet", "no draw bet", " dnb", "dnb ", "dnb")):
            return None
        participant, participant_side = self._participant_from_text(raw, home, away)
        if participant is None:
            cleaned = re.sub(r"\b(draw\s+no\s+bet|no\s+draw\s+bet|dnb)\b", "", raw, flags=re.I).strip(" :-—")
            participant = cleaned or None
        if participant is None:
            return InterpretedMarket(
                MarketKind.HANDICAP,
                self._with_period("Draw No Bet", period),
                metric="draw_no_bet",
                line=Decimal("0"),
                period=period,
                understood=False,
                reason="Draw No Bet is clear, but the team or participant is not.",
            )
        return InterpretedMarket(
            MarketKind.HANDICAP,
            self._with_period(f"{participant} — Draw No Bet", period),
            metric="draw_no_bet",
            line=Decimal("0"),
            side=participant_side or "participant",
            participant=participant,
            period=period,
        )

    def _race_field(self, raw: str, low: str, period: str) -> InterpretedMarket | None:
        # These labels appear in golf, motorsport, cycling and other multi-participant fields.
        # They are only recognized when a field-specific cue is present so ordinary team
        # winner labels are not accidentally converted into race/field markets.
        winner_patterns = (
            r"^(?P<participant>.+?)\s*(?:—|-|:)??\s*(?:race|tournament|event|outright)\s+winner$",
            r"^(?P<participant>.+?)\s+to\s+win\s+(?:the\s+)?(?:race|tournament|event|outright)$",
            r"^(?:race|tournament|event|outright)\s+winner\s*(?:—|-|:)?\s*(?P<participant>.+)$",
        )
        for pattern in winner_patterns:
            match = re.match(pattern, raw, re.I)
            if match:
                participant = match.group("participant").strip(" :-—")
                return InterpretedMarket(
                    MarketKind.RACE_FIELD,
                    self._with_period(f"{participant} to win", period),
                    metric="outright_winner",
                    side="winner",
                    participant=participant,
                    period=period,
                )

        top_patterns = (
            r"^(?P<participant>.+?)\s*(?:—|-|:)?\s*(?:to\s+)?(?:finish\s+)?top\s*(?P<n>\d+)(?:\s+finish)?$",
            r"^top\s*(?P<n>\d+)(?:\s+finish)?\s*(?:—|-|:)?\s*(?P<participant>.+)$",
        )
        for pattern in top_patterns:
            match = re.match(pattern, raw, re.I)
            if match:
                participant = match.group("participant").strip(" :-—")
                n = int(match.group("n"))
                if n < 1:
                    return None
                return InterpretedMarket(
                    MarketKind.RACE_FIELD,
                    self._with_period(f"{participant} — Top {n} finish", period),
                    metric="finish_position",
                    line=Decimal(n),
                    side="top",
                    participant=participant,
                    period=period,
                )

        podium_patterns = (
            r"^(?P<participant>.+?)\s*(?:—|-|:)?\s*(?:to\s+)?(?:finish\s+on\s+the\s+)?podium(?:\s+finish)?$",
            r"^podium(?:\s+finish)?\s*(?:—|-|:)?\s*(?P<participant>.+)$",
        )
        for pattern in podium_patterns:
            match = re.match(pattern, raw, re.I)
            if match:
                participant = match.group("participant").strip(" :-—")
                return InterpretedMarket(
                    MarketKind.RACE_FIELD,
                    self._with_period(f"{participant} — Podium finish", period),
                    metric="finish_position",
                    line=Decimal("3"),
                    side="top",
                    participant=participant,
                    period=period,
                )

        make_cut = re.match(
            r"^(?P<participant>.+?)\s*(?:—|-|:)?\s*(?:to\s+)?(?P<verb>make|miss)(?:\s+the)?\s+cut(?:\s*(?:—|-|:)?\s*(?P<yn>yes|no))?$",
            raw,
            re.I,
        )
        if make_cut:
            participant = make_cut.group("participant").strip(" :-—")
            verb = make_cut.group("verb").casefold()
            explicit = (make_cut.group("yn") or "").casefold()
            makes_cut = verb == "make"
            if explicit == "no":
                makes_cut = not makes_cut
            return InterpretedMarket(
                MarketKind.RACE_FIELD,
                self._with_period(
                    f"{participant} — {'Make' if makes_cut else 'Miss'} the cut",
                    period,
                ),
                metric="make_cut",
                side="yes" if makes_cut else "no",
                participant=participant,
                period=period,
            )

        group_winner = re.match(
            r"^(?P<participant>.+?)\s*(?:—|-|:)?\s*(?:group|matchup)\s+winner$",
            raw,
            re.I,
        )
        if group_winner:
            participant = group_winner.group("participant").strip(" :-—")
            return InterpretedMarket(
                MarketKind.RACE_FIELD,
                self._with_period(f"{participant} — Group winner", period),
                metric="group_winner",
                side="winner",
                participant=participant,
                period=period,
            )

        return None

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
        return re.search(r"(?:handicap|spread)(?:\s+[12])?\s*(?P<number>-?\d+(?:\.\d+)?)", low)

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
