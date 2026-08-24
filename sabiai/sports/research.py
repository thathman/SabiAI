from __future__ import annotations

from dataclasses import dataclass

from sabiai.markets import MarketInterpreter
from .registry import SportProfile, SportRegistry, default_sports


@dataclass(frozen=True, slots=True)
class ResearchPlan:
    sport: SportProfile
    market_text: str | None
    checklist: tuple[str, ...]
    market_focus: tuple[str, ...]
    needs_source_discovery: bool


class ResearchPlanner:
    """Build a plain-language research checklist before sources are queried."""

    def __init__(self, registry: SportRegistry | None = None):
        self.registry = registry or default_sports()
        self.interpreter = MarketInterpreter()

    def plan(
        self,
        sport_name: str,
        *,
        market_text: str | None = None,
        home: str | None = None,
        away: str | None = None,
    ) -> ResearchPlan:
        sport = self.registry.resolve(sport_name)
        base = [
            "recent form",
            "injuries, suspensions or availability",
            "schedule, rest and travel when relevant",
            "competition and match context",
        ]
        base.extend(sport.research_topics)
        focus: list[str] = []

        if market_text:
            parsed = self.interpreter.interpret(market_text, home=home, away=away)
            metric = parsed.metric or ""
            low = market_text.casefold()
            if metric == "corners" or "corner" in low:
                focus.extend(("corners won and conceded", "wide play, pressure and likely game state"))
            elif metric == "cards" or "card" in low:
                focus.extend(("cards and fouls for both teams", "referee discipline record when available", "match intensity and rivalry context"))
            elif metric in {"shots", "shots_on_target"} or "shot" in low:
                focus.extend(("shot volume and shots on target", "expected minutes and player role when player-specific", "opponent shot suppression"))
            elif metric in {"sets", "games", "maps", "frames"} or any(word in low for word in ("set", "map", "frame")):
                focus.extend(("recent performance by set/frame/map", "match format and number of sets/frames/maps required"))
            elif metric in {"rebounds", "assists"}:
                focus.extend((f"recent {metric}", "expected minutes and role", "opponent matchup for this statistic"))
            elif metric in {"goals", "points", "runs"} or any(word in low for word in ("goal", "points", "runs")):
                focus.extend(("recent scoring and conceding pattern", "important attacking/defensive absences"))
            elif parsed.participant:
                focus.extend((f"recent performance of {parsed.participant}", "opponent strength and matchup"))
            elif not parsed.understood:
                focus.append("confirm exactly what the bookmaker market means before evaluating it")

        checklist = tuple(dict.fromkeys(item for item in [*base, *focus] if item))
        return ResearchPlan(
            sport=sport,
            market_text=market_text,
            checklist=checklist,
            market_focus=tuple(dict.fromkeys(focus)),
            needs_source_discovery=sport.needs_discovery,
        )
