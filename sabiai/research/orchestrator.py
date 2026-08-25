from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from typing import Mapping

from sabiai.sources import SourceRegistry, SourceRequest, SourceService
from sabiai.sources.service import Fetcher
from sabiai.storage import SabiDatabase

from .evidence import Evidence, EvidenceStore
from .tasks import ResearchTask


@dataclass(frozen=True, slots=True)
class ResearchFinding:
    summary: str
    subject: str | None = None
    observed_at: str | None = None
    reliability: str | None = None
    raw: dict | list | None = None

    @classmethod
    def from_payload(cls, payload: object) -> "ResearchFinding":
        if isinstance(payload, str):
            text = payload.strip()
            if not text:
                raise ValueError("Research source returned an empty summary.")
            return cls(summary=text)
        if not isinstance(payload, dict):
            raise ValueError("Research source must return a plain summary string or structured finding object.")
        summary = str(payload.get("summary") or "").strip()
        if not summary:
            raise ValueError("Structured research finding needs a plain-language 'summary'.")
        raw = payload.get("raw")
        if raw is None:
            # Preserve useful structured fields without duplicating the human summary.
            raw = {
                key: value
                for key, value in payload.items()
                if key not in {"summary", "subject", "observed_at", "reliability"}
            } or None
        return cls(
            summary=summary,
            subject=str(payload["subject"]).strip() if payload.get("subject") else None,
            observed_at=str(payload["observed_at"]).strip() if payload.get("observed_at") else None,
            reliability=str(payload["reliability"]).strip() if payload.get("reliability") else None,
            raw=raw if isinstance(raw, (dict, list)) else {"value": raw},
        )


@dataclass(frozen=True, slots=True)
class ResearchRunItem:
    topic: str
    capability: str
    success: bool
    source_name: str | None
    cache_hit: bool
    paid: bool
    evidence_id: str | None
    summary: str | None
    error: str | None = None


@dataclass(slots=True)
class ResearchRun:
    sport: str
    event: str
    event_id: str | None
    items: list[ResearchRunItem] = field(default_factory=list)

    @property
    def success_count(self) -> int:
        return sum(1 for item in self.items if item.success)

    @property
    def failure_count(self) -> int:
        return sum(1 for item in self.items if not item.success)

    @property
    def paid_calls(self) -> int:
        return sum(1 for item in self.items if item.success and item.paid and not item.cache_hit)

    @property
    def cache_hits(self) -> int:
        return sum(1 for item in self.items if item.success and item.cache_hit)


class ResearchOrchestrator:
    """Run a research plan through Sabi Boy's cache/free-first source policy.

    Source/browser adapters remain separate. They return a small structured finding;
    this orchestrator handles request identity, cache reuse, paid escalation rules and
    evidence persistence so every workflow follows the same discipline.
    """

    def __init__(self, database: SabiDatabase, registry: SourceRegistry):
        self.database = database
        self.registry = registry
        self.source_service = SourceService(database, registry)
        self.evidence_store = EvidenceStore(database)

    def execute(
        self,
        tasks: list[ResearchTask],
        *,
        sport: str,
        event: str,
        fetchers: Mapping[str, Fetcher],
        event_id: str | None = None,
        sport_id: str | None = None,
        market: str | None = None,
        allow_paid: bool = False,
        paid_reason: str | None = None,
    ) -> ResearchRun:
        if not sport.strip():
            raise ValueError("Research run needs a sport.")
        if not event.strip():
            raise ValueError("Research run needs an event.")

        run = ResearchRun(sport=sport.strip(), event=event.strip(), event_id=event_id)
        for task in sorted(tasks, key=lambda item: item.priority):
            request_key = self._request_key(
                sport=sport,
                event=event,
                market=market,
                topic=task.topic,
                capability=task.capability,
            )
            request = SourceRequest(
                request_key=request_key,
                capability=task.capability,
                sport=sport,
                ttl_seconds=task.freshness_seconds,
                metadata={
                    "event": event,
                    "market": market,
                    "topic": task.topic,
                    "instruction": task.instruction,
                },
            )
            try:
                response = self.source_service.execute(
                    request,
                    fetchers,
                    allow_paid=bool(allow_paid and task.paid_fallback_allowed),
                    paid_reason=paid_reason if task.paid_fallback_allowed else None,
                )
                finding = ResearchFinding.from_payload(response.payload)
                evidence_id = self.evidence_store.save(
                    Evidence(
                        event_id=event_id,
                        sport_id=sport_id,
                        evidence_type=task.topic,
                        subject=finding.subject,
                        summary=finding.summary,
                        source_name=response.source_name,
                        observed_at=finding.observed_at,
                        freshness_seconds=task.freshness_seconds,
                        reliability=finding.reliability,
                        raw=finding.raw,
                    )
                )
                run.items.append(
                    ResearchRunItem(
                        topic=task.topic,
                        capability=task.capability,
                        success=True,
                        source_name=response.source_name,
                        cache_hit=response.cache_hit,
                        paid=response.paid,
                        evidence_id=evidence_id,
                        summary=finding.summary,
                    )
                )
            except Exception as exc:
                run.items.append(
                    ResearchRunItem(
                        topic=task.topic,
                        capability=task.capability,
                        success=False,
                        source_name=None,
                        cache_hit=False,
                        paid=False,
                        evidence_id=None,
                        summary=None,
                        error=str(exc),
                    )
                )
        return run

    @staticmethod
    def _request_key(
        *,
        sport: str,
        event: str,
        market: str | None,
        topic: str,
        capability: str,
    ) -> str:
        raw = "|".join(
            part.strip().casefold()
            for part in (sport, event, market or "", topic, capability)
        )
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
        return f"research:{digest}"
