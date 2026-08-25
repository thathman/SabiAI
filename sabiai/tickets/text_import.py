from __future__ import annotations

from dataclasses import dataclass, field
import re


@dataclass(frozen=True, slots=True)
class ExtractedTextLeg:
    event: str
    market: str
    odds: str
    home: str | None = None
    away: str | None = None

    def as_dict(self) -> dict:
        data = {"event": self.event, "market": self.market, "odds": self.odds}
        if self.home:
            data["home"] = self.home
        if self.away:
            data["away"] = self.away
        return data


@dataclass(slots=True)
class TextTicketExtraction:
    legs: list[ExtractedTextLeg] = field(default_factory=list)
    unparsed_lines: list[str] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        return bool(self.legs) and not self.unparsed_lines


class TicketTextImporter:
    """Deterministic importer for common copied/share/post ticket text.

    OpenClaw can still use vision/browser reasoning for messy screenshots or posts, but
    clean extracted text should not require an LLM to be interpreted again.
    """

    _number_prefix = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s*")
    _odds_tail = re.compile(
        r"(?:\s*(?:@|odds?\s*[:=])\s*)?(?P<odds>\d+(?:\.\d{1,3})?)\s*$",
        re.I,
    )
    _event = re.compile(
        r"^(?P<home>.+?)\s+(?:vs\.?|v\.?)\s+(?P<away>.+?)$",
        re.I,
    )
    _inline_event = re.compile(
        r"^(?P<home>.+?)\s+(?:vs\.?|v\.?)\s+(?P<away>.+?)\s*(?:\||—|–|;|:)\s*(?P<rest>.+)$",
        re.I,
    )

    def extract(self, text: str) -> TextTicketExtraction:
        result = TextTicketExtraction()
        current_event: tuple[str, str, str] | None = None

        for original in (text or "").splitlines():
            line = self._clean_line(original)
            if not line or self._is_noise(line):
                continue

            standalone_event = self._event.match(line)
            if standalone_event and not self._odds_tail.search(line):
                home = standalone_event.group("home").strip()
                away = standalone_event.group("away").strip()
                current_event = (f"{home} vs {away}", home, away)
                continue

            inline = self._inline_event.match(line)
            if inline:
                home = inline.group("home").strip()
                away = inline.group("away").strip()
                event = f"{home} vs {away}"
                parsed = self._selection_and_odds(inline.group("rest"))
                if parsed:
                    market, odds = parsed
                    result.legs.append(ExtractedTextLeg(event, market, odds, home, away))
                    current_event = None
                    continue

            parts = self._split_columns(line)
            if len(parts) >= 3:
                event = parts[0]
                teams = self._parse_event(event)
                odds = self._odds_value(parts[-1])
                market = " | ".join(parts[1:-1]).strip()
                if odds and market:
                    home, away = teams
                    explicit_event = f"{home} vs {away}" if home and away else event
                    result.legs.append(
                        ExtractedTextLeg(explicit_event, market, odds, home, away)
                    )
                    current_event = None
                    continue

            parsed = self._selection_and_odds(line)
            if parsed and current_event:
                market, odds = parsed
                event, home, away = current_event
                result.legs.append(ExtractedTextLeg(event, market, odds, home, away))
                current_event = None
                continue

            result.unparsed_lines.append(line)

        if current_event:
            result.unparsed_lines.append(current_event[0])
        return result

    def _selection_and_odds(self, text: str) -> tuple[str, str] | None:
        match = self._odds_tail.search(text)
        if not match:
            return None
        market = text[: match.start()].strip(" |—–;:-")
        if not market:
            return None
        odds = match.group("odds")
        try:
            if float(odds) <= 1:
                return None
        except ValueError:
            return None
        return market, odds

    def _odds_value(self, text: str) -> str | None:
        match = self._odds_tail.search(text.strip())
        if not match:
            return None
        odds = match.group("odds")
        try:
            return odds if float(odds) > 1 else None
        except ValueError:
            return None

    def _parse_event(self, text: str) -> tuple[str | None, str | None]:
        match = self._event.match(text.strip())
        if not match:
            return None, None
        return match.group("home").strip(), match.group("away").strip()

    @staticmethod
    def _split_columns(line: str) -> list[str]:
        if "|" in line:
            return [part.strip() for part in line.split("|") if part.strip()]
        if "\t" in line:
            return [part.strip() for part in line.split("\t") if part.strip()]
        return []

    def _clean_line(self, line: str) -> str:
        return self._number_prefix.sub("", line.strip()).strip()

    @staticmethod
    def _is_noise(line: str) -> bool:
        low = line.casefold()
        return low.startswith(("booking code", "combined odds", "total odds", "stake:", "potential win"))
