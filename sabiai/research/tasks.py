from __future__ import annotations

from dataclasses import dataclass

from sabiai.sources.registry import SourceKind

from .case import ResearchAssessment


@dataclass(frozen=True, slots=True)
class ResearchTask:
    topic: str
    capability: str
    instruction: str
    priority: int
    freshness_seconds: int
    preferred_source_kinds: tuple[SourceKind, ...]
    paid_fallback_allowed: bool = True


class ResearchTaskPlanner:
    """Translate research gaps into precise free-first work for OpenClaw/source adapters."""

    _topic_config = {
        "availability": ("availability", 600, 10),
        "market_stats": ("stats", 3600, 20),
        "form": ("form", 21600, 30),
        "home_away": ("form", 21600, 35),
        "schedule": ("schedule", 21600, 40),
        "context": ("context", 21600, 45),
        "h2h": ("h2h", 86400, 60),
        "rules": ("rules", 604800, 5),
    }

    _free_path = (
        SourceKind.CACHE,
        SourceKind.OPEN_DATA,
        SourceKind.OFFICIAL,
        SourceKind.PUBLIC_ENDPOINT,
        SourceKind.PUBLIC_WEB,
        SourceKind.BROWSER,
        SourceKind.SEARCH,
    )

    def plan(self, assessment: ResearchAssessment) -> list[ResearchTask]:
        tasks: list[ResearchTask] = []

        if assessment.needs_source_discovery:
            tasks.append(
                ResearchTask(
                    topic="source_discovery",
                    capability="source_discovery",
                    instruction=(
                        f"Find reliable public/official sources for {assessment.sport} and confirm the competition, "
                        f"event format and market meaning for {assessment.event}."
                    ),
                    priority=0,
                    freshness_seconds=604800,
                    preferred_source_kinds=(
                        SourceKind.OFFICIAL,
                        SourceKind.PUBLIC_WEB,
                        SourceKind.SEARCH,
                        SourceKind.BROWSER,
                    ),
                    paid_fallback_allowed=False,
                )
            )

        for topic in assessment.missing_topics:
            capability, freshness, priority = self._topic_config.get(
                topic, (topic, 21600, 50)
            )
            instruction = self._instruction(topic, assessment)
            tasks.append(
                ResearchTask(
                    topic=topic,
                    capability=capability,
                    instruction=instruction,
                    priority=priority,
                    freshness_seconds=freshness,
                    preferred_source_kinds=self._free_path,
                )
            )

        if assessment.conflicts:
            tasks.append(
                ResearchTask(
                    topic="conflict_resolution",
                    capability="verification",
                    instruction=(
                        f"Resolve {len(assessment.conflicts)} conflicting evidence item(s) for {assessment.event}. "
                        "Prefer the freshest primary/official source and record why one source should be trusted over another."
                    ),
                    priority=1,
                    freshness_seconds=600,
                    preferred_source_kinds=(
                        SourceKind.OFFICIAL,
                        SourceKind.PUBLIC_ENDPOINT,
                        SourceKind.PUBLIC_WEB,
                        SourceKind.BROWSER,
                        SourceKind.SEARCH,
                    ),
                )
            )

        # Deduplicate by topic/capability while preserving the highest priority task.
        unique: dict[tuple[str, str], ResearchTask] = {}
        for task in sorted(tasks, key=lambda item: item.priority):
            unique.setdefault((task.topic, task.capability), task)
        return sorted(unique.values(), key=lambda item: item.priority)

    @staticmethod
    def _instruction(topic: str, assessment: ResearchAssessment) -> str:
        event = assessment.event
        market = assessment.market
        instructions = {
            "availability": f"Check current injuries, suspensions, expected starters/lineups/rosters and availability for {event}.",
            "market_stats": f"Collect current statistics specifically relevant to {market or 'the requested market'} for {event}.",
            "form": f"Check the most relevant recent form for both sides/participants in {event}.",
            "home_away": f"Compare home/away or venue-specific form for {event}.",
            "schedule": f"Check rest days, travel and schedule congestion for {event}.",
            "context": f"Check competition importance, rotation incentives and situational context for {event}.",
            "h2h": f"Check head-to-head history for {event}, using it only if the matchup context is genuinely comparable.",
            "rules": f"Confirm event format and exact settlement meaning of {market or 'the requested market'} for {event}.",
        }
        return instructions.get(topic, f"Research the missing '{topic}' evidence for {event}.")
