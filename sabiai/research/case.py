from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable

from sabiai.sports import ResearchPlanner, SportRegistry, default_sports


@dataclass(frozen=True, slots=True)
class EvidenceConflict:
    evidence_type: str
    subject: str | None
    evidence_ids: tuple[str, ...]
    reason: str


@dataclass(slots=True)
class ResearchAssessment:
    sport: str
    event: str
    market: str | None
    checklist: tuple[str, ...]
    evidence_count: int
    coverage_pct: int
    evidence_quality: str
    missing_topics: tuple[str, ...] = ()
    stale_evidence_ids: tuple[str, ...] = ()
    low_reliability_ids: tuple[str, ...] = ()
    conflicts: tuple[EvidenceConflict, ...] = ()
    needs_source_discovery: bool = False
    skeptic_required: bool = False
    next_questions: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()


class ResearchCaseService:
    """Assess whether a Sabi Boy research case is complete enough to reason from.

    This layer deliberately does not decide the bet. It answers a different question:
    do we have enough fresh, relevant, internally-consistent evidence to trust the next
    decision step, and what still needs researching?
    """

    _topic_aliases = {
        "form": ("form", "recent_form", "recent form"),
        "home_away": ("home_away", "home away", "home/away", "venue form"),
        "availability": (
            "injury",
            "injuries",
            "availability",
            "suspension",
            "suspensions",
            "lineup",
            "lineups",
            "roster",
            "starters",
        ),
        "schedule": ("schedule", "rest", "travel", "congestion"),
        "context": ("context", "competition context", "motivation", "importance"),
        "h2h": ("h2h", "head to head", "head-to-head"),
        "market_stats": (
            "market_stats",
            "market stats",
            "corners",
            "cards",
            "shots",
            "goals",
            "points",
            "rebounds",
            "assists",
            "sets",
            "maps",
            "frames",
            "runs",
            "wickets",
            "kills",
            "aces",
            "blocks",
            "saves",
        ),
        "rules": ("rules", "market rules", "settlement", "format"),
    }

    _structured_conflict_keys = (
        "status",
        "state",
        "available",
        "availability",
        "out",
        "value",
        "starter",
        "lineup_status",
    )

    def __init__(
        self,
        registry: SportRegistry | None = None,
        planner: ResearchPlanner | None = None,
    ):
        self.registry = registry or default_sports()
        self.planner = planner or ResearchPlanner(self.registry)

    def assess(
        self,
        *,
        sport: str,
        event: str,
        evidence: Iterable[dict],
        market: str | None = None,
        home: str | None = None,
        away: str | None = None,
        now: datetime | None = None,
    ) -> ResearchAssessment:
        if not event.strip():
            raise ValueError("Research case needs an explicit event name.")
        now = now or datetime.now(timezone.utc)
        plan = self.planner.plan(sport, market_text=market, home=home, away=away)
        rows = [dict(item) for item in evidence]

        required = self._required_topics(plan.checklist, plan.market_focus)
        covered: set[str] = set()
        stale_ids: list[str] = []
        low_ids: list[str] = []
        usable_rows: list[dict] = []

        for row in rows:
            evidence_id = str(row.get("id") or "unknown")
            if self._is_stale(row, now):
                stale_ids.append(evidence_id)
                continue
            reliability = str(row.get("reliability") or "unknown").casefold().strip()
            if reliability in {"low", "weak", "poor", "unverified"}:
                low_ids.append(evidence_id)
            usable_rows.append(row)
            covered.update(self._topics_for_evidence(row))

        relevant_covered = required & covered
        coverage = int(round((len(relevant_covered) / len(required)) * 100)) if required else 100
        missing = sorted(required - relevant_covered)
        conflicts = self._find_conflicts(usable_rows)

        strong_count = sum(
            1
            for row in usable_rows
            if str(row.get("reliability") or "").casefold().strip()
            in {"high", "strong", "official", "primary"}
        )
        usable_count = len(usable_rows)
        if coverage >= 80 and not conflicts and usable_count >= 3 and strong_count >= 1:
            quality = "strong"
        elif coverage >= 50 and usable_count >= 2 and len(conflicts) <= 1:
            quality = "fair"
        else:
            quality = "weak"

        skeptic_required = bool(
            conflicts
            or plan.sport.needs_discovery
            or coverage < 70
            or (market and not plan.market_focus)
            or (usable_count > 0 and len(low_ids) == usable_count)
        )

        next_questions: list[str] = []
        for topic in missing[:6]:
            next_questions.append(self._question_for_topic(topic, event, market))
        if conflicts:
            next_questions.append("Resolve the conflicting evidence with a fresher or more authoritative source.")
        if plan.sport.needs_discovery:
            next_questions.append(f"Confirm {plan.sport.name} rules, competition format and market settlement before relying on the case.")

        notes: list[str] = []
        if stale_ids:
            notes.append(f"{len(stale_ids)} evidence item(s) are too old for their stated freshness window.")
        if low_ids:
            notes.append(f"{len(low_ids)} usable evidence item(s) are marked low/unverified reliability.")
        if not rows:
            notes.append("No evidence has been attached to this research case yet.")

        return ResearchAssessment(
            sport=plan.sport.name,
            event=event.strip(),
            market=market,
            checklist=plan.checklist,
            evidence_count=len(rows),
            coverage_pct=coverage,
            evidence_quality=quality,
            missing_topics=tuple(missing),
            stale_evidence_ids=tuple(stale_ids),
            low_reliability_ids=tuple(low_ids),
            conflicts=tuple(conflicts),
            needs_source_discovery=plan.sport.needs_discovery,
            skeptic_required=skeptic_required,
            next_questions=tuple(dict.fromkeys(next_questions)),
            notes=tuple(notes),
        )

    def _required_topics(self, checklist: tuple[str, ...], market_focus: tuple[str, ...]) -> set[str]:
        topics = {"form", "availability", "context"}
        joined = " ".join([*checklist, *market_focus]).casefold()
        if any(term in joined for term in ("home", "away", "venue")):
            topics.add("home_away")
        if any(term in joined for term in ("schedule", "rest", "travel", "congestion")):
            topics.add("schedule")
        if any(term in joined for term in ("head-to-head", "head to head", "h2h")):
            topics.add("h2h")
        if market_focus:
            topics.add("market_stats")
        if any(term in joined for term in ("format", "settlement", "rules")):
            topics.add("rules")
        return topics

    def _topics_for_evidence(self, row: dict) -> set[str]:
        text = " ".join(
            str(row.get(key) or "")
            for key in ("evidence_type", "subject", "summary")
        ).casefold()
        found: set[str] = set()
        for topic, aliases in self._topic_aliases.items():
            if any(alias in text for alias in aliases):
                found.add(topic)
        return found

    @staticmethod
    def _is_stale(row: dict, now: datetime) -> bool:
        freshness = row.get("freshness_seconds")
        if freshness is None:
            return False
        try:
            freshness = int(freshness)
        except (TypeError, ValueError):
            return False
        if freshness < 0:
            return True
        stamp = row.get("observed_at") or row.get("fetched_at")
        if not stamp:
            return False
        try:
            observed = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
        except ValueError:
            return False
        if observed.tzinfo is None:
            observed = observed.replace(tzinfo=timezone.utc)
        return (now - observed).total_seconds() > freshness

    def _find_conflicts(self, rows: list[dict]) -> list[EvidenceConflict]:
        groups: dict[tuple[str, str | None], list[dict]] = {}
        for row in rows:
            key = (
                str(row.get("evidence_type") or "").casefold().strip(),
                str(row.get("subject")).casefold().strip() if row.get("subject") else None,
            )
            groups.setdefault(key, []).append(row)

        conflicts: list[EvidenceConflict] = []
        for (evidence_type, subject), items in groups.items():
            if len(items) < 2:
                continue
            for key in self._structured_conflict_keys:
                values: dict[str, list[str]] = {}
                for item in items:
                    raw = item.get("raw")
                    if not isinstance(raw, dict) or key not in raw:
                        continue
                    value = str(raw[key]).casefold().strip()
                    values.setdefault(value, []).append(str(item.get("id") or "unknown"))
                if len(values) > 1:
                    evidence_ids = tuple(dict.fromkeys(i for ids in values.values() for i in ids))
                    conflicts.append(
                        EvidenceConflict(
                            evidence_type=evidence_type or "unknown",
                            subject=subject,
                            evidence_ids=evidence_ids,
                            reason=f"Sources disagree on structured field '{key}'.",
                        )
                    )
                    break
        return conflicts

    @staticmethod
    def _question_for_topic(topic: str, event: str, market: str | None) -> str:
        questions = {
            "form": f"Check the most relevant recent form for {event}.",
            "home_away": f"Compare the home/away or venue-specific form for {event}.",
            "availability": f"Check injuries, suspensions, expected lineup/roster and availability for {event}.",
            "schedule": f"Check rest, travel and schedule context for {event}.",
            "context": f"Check the competition importance and situational context for {event}.",
            "h2h": f"Check head-to-head history for {event} if it is genuinely relevant.",
            "market_stats": f"Collect statistics directly relevant to {market or 'the requested market'} for {event}.",
            "rules": f"Confirm the event format and settlement meaning of {market or 'the market'} for {event}.",
        }
        return questions.get(topic, f"Research missing topic '{topic}' for {event}.")
