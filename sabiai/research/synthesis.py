from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .case import ResearchAssessment


@dataclass(frozen=True, slots=True)
class ResearchSummary:
    sport: str
    event: str
    market: str | None
    evidence_quality: str
    coverage_pct: int
    what_we_know: tuple[str, ...]
    what_worries_me: tuple[str, ...]
    still_to_check: tuple[str, ...]
    sources_used: tuple[str, ...]
    skeptic_required: bool

    def plain_text(self) -> str:
        lines = [
            f"{self.event}",
            f"Research coverage: {self.coverage_pct}% — {self.evidence_quality}",
        ]
        if self.what_we_know:
            lines.append("What I know:")
            lines.extend(f"- {item}" for item in self.what_we_know)
        if self.what_worries_me:
            lines.append("What worries me:")
            lines.extend(f"- {item}" for item in self.what_worries_me)
        if self.still_to_check:
            lines.append("Still to check:")
            lines.extend(f"- {item}" for item in self.still_to_check)
        return "\n".join(lines)


class ResearchSynthesizer:
    """Turn stored evidence into a short, human-readable research brief.

    This does not invent a probability or selection. It summarizes what Sabi Boy actually
    has, highlights evidence problems, and keeps unanswered questions visible.
    """

    _reliability_rank = {
        "official": 0,
        "primary": 0,
        "high": 1,
        "strong": 1,
        "medium": 2,
        "fair": 2,
        "unknown": 3,
        "low": 4,
        "weak": 4,
        "poor": 4,
        "unverified": 5,
    }

    def summarize(
        self,
        assessment: ResearchAssessment,
        evidence: Iterable[dict],
        *,
        max_points: int = 10,
    ) -> ResearchSummary:
        stale = set(assessment.stale_evidence_ids)
        rows = [dict(item) for item in evidence]
        usable = [row for row in rows if str(row.get("id") or "unknown") not in stale]
        usable.sort(key=self._sort_key)

        known: list[str] = []
        sources: list[str] = []
        for row in usable:
            summary = str(row.get("summary") or "").strip()
            if summary and summary not in known:
                known.append(summary)
            source = str(row.get("source_name") or "").strip()
            if source and source not in sources:
                sources.append(source)
            if len(known) >= max(1, int(max_points)):
                break

        worries: list[str] = []
        if assessment.conflicts:
            for conflict in assessment.conflicts:
                subject = f" for {conflict.subject}" if conflict.subject else ""
                worries.append(
                    f"Sources conflict on {conflict.evidence_type}{subject}: {conflict.reason}"
                )
        if assessment.stale_evidence_ids:
            worries.append(
                f"{len(assessment.stale_evidence_ids)} research item(s) are stale and should not be relied on until refreshed."
            )
        if assessment.low_reliability_ids:
            worries.append(
                f"{len(assessment.low_reliability_ids)} research item(s) are low or unverified reliability."
            )
        worries.extend(note for note in assessment.notes if note not in worries)

        still = list(assessment.next_questions)
        if not still and assessment.missing_topics:
            still.extend(f"Check {topic.replace('_', ' ')}." for topic in assessment.missing_topics)

        return ResearchSummary(
            sport=assessment.sport,
            event=assessment.event,
            market=assessment.market,
            evidence_quality=assessment.evidence_quality,
            coverage_pct=assessment.coverage_pct,
            what_we_know=tuple(known),
            what_worries_me=tuple(dict.fromkeys(worries)),
            still_to_check=tuple(dict.fromkeys(still)),
            sources_used=tuple(sources),
            skeptic_required=assessment.skeptic_required,
        )

    def _sort_key(self, row: dict) -> tuple[int, str]:
        reliability = str(row.get("reliability") or "unknown").casefold().strip()
        rank = self._reliability_rank.get(reliability, 3)
        observed = str(row.get("observed_at") or row.get("fetched_at") or "")
        # More authoritative first. Timestamp is retained as a stable secondary key;
        # freshness eligibility is already handled by ResearchCaseService.
        return rank, observed
