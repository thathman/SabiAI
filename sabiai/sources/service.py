from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable, Mapping

from sabiai.storage.sqlite import SabiDatabase

from .registry import Source, SourceCost, SourceRegistry

Fetcher = Callable[["SourceRequest"], object]


@dataclass(slots=True)
class SourceRequest:
    request_key: str
    capability: str
    sport: str | None = None
    ttl_seconds: int = 900
    metadata: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.request_key.strip():
            raise ValueError("Source request needs a stable request_key.")
        if not self.capability.strip():
            raise ValueError("Source request needs a capability.")
        if self.ttl_seconds < 0:
            raise ValueError("ttl_seconds cannot be negative.")


@dataclass(slots=True)
class SourceResponse:
    payload: object
    source_name: str
    cache_hit: bool
    paid: bool
    fetched_at: datetime
    failures: tuple[str, ...] = ()


class SourceService:
    """Execute source requests with cache-first, free-first behavior.

    Network details live in source adapters/fetchers. This service owns selection,
    cache reuse, paid escalation and usage logging so those rules cannot be bypassed
    accidentally by every caller.

    A caller may set metadata.require_complete=true. In that mode a source can be healthy
    and useful yet still be too partial for the request; Sabi Boy records that fetch and
    continues to the next free source instead of treating partial coverage as complete.
    """

    def __init__(self, database: SabiDatabase, registry: SourceRegistry):
        self.database = database
        self.registry = registry

    def execute(
        self,
        request: SourceRequest,
        fetchers: Mapping[str, Fetcher],
        *,
        allow_paid: bool = False,
        paid_reason: str | None = None,
        now: datetime | None = None,
    ) -> SourceResponse:
        now = now or datetime.now(timezone.utc)
        require_complete = bool((request.metadata or {}).get("require_complete", False))
        cached = self.database.get_cache(request.request_key, now=now)
        if cached is not None and not (require_complete and self._is_partial(cached.get("payload"))):
            source = self._source_by_name(cached["source_name"])
            paid = bool(source and source.cost is SourceCost.PAID)
            self.database.log_source_fetch(
                source_name=cached["source_name"],
                sport=request.sport,
                capability=request.capability,
                request_key=request.request_key,
                cache_hit=True,
                success=True,
                paid=paid,
                reason="Fresh cached result reused.",
            )
            return SourceResponse(
                payload=cached["payload"],
                source_name=cached["source_name"],
                cache_hit=True,
                paid=paid,
                fetched_at=datetime.fromisoformat(cached["fetched_at"]),
            )

        failures: list[str] = []
        candidates = self.registry.candidates(
            sport=request.sport,
            capability=request.capability,
            include_paid=True,
        )
        for source in candidates:
            self.database.upsert_source(source)
            fetcher = fetchers.get(source.name)
            if fetcher is None:
                failures.append(f"{source.name}: no adapter")
                continue
            if source.cost is SourceCost.PAID:
                if not allow_paid:
                    failures.append(f"{source.name}: paid access not approved")
                    continue
                if not paid_reason or not paid_reason.strip():
                    failures.append(f"{source.name}: paid access needs a reason")
                    continue
            try:
                payload = fetcher(request)
                if payload is None:
                    raise RuntimeError("source returned no data")
            except Exception as exc:
                failures.append(f"{source.name}: {exc}")
                self.database.log_source_fetch(
                    source_name=source.name,
                    sport=request.sport,
                    capability=request.capability,
                    request_key=request.request_key,
                    cache_hit=False,
                    success=False,
                    paid=source.cost is SourceCost.PAID,
                    reason=paid_reason if source.cost is SourceCost.PAID else "Free source attempt.",
                    error=str(exc),
                )
                continue

            if require_complete and self._is_partial(payload):
                reason = f"{source.name}: response is useful but partial; complete coverage requested"
                failures.append(reason)
                self.database.log_source_fetch(
                    source_name=source.name,
                    sport=request.sport,
                    capability=request.capability,
                    request_key=request.request_key,
                    cache_hit=False,
                    success=True,
                    paid=source.cost is SourceCost.PAID,
                    reason="Source responded successfully, but partial coverage was insufficient for this complete-coverage request.",
                )
                continue

            expires_at = now + timedelta(seconds=request.ttl_seconds)
            self.database.put_cache(
                cache_key=request.request_key,
                source_name=source.name,
                sport=request.sport,
                capability=request.capability,
                payload=payload,
                fetched_at=now,
                expires_at=expires_at,
                metadata=request.metadata,
            )
            self.database.log_source_fetch(
                source_name=source.name,
                sport=request.sport,
                capability=request.capability,
                request_key=request.request_key,
                cache_hit=False,
                success=True,
                paid=source.cost is SourceCost.PAID,
                reason=paid_reason if source.cost is SourceCost.PAID else "Free source succeeded.",
            )
            return SourceResponse(
                payload=payload,
                source_name=source.name,
                cache_hit=False,
                paid=source.cost is SourceCost.PAID,
                fetched_at=now,
                failures=tuple(failures),
            )

        raise RuntimeError(
            "No source could satisfy the request. " + ("; ".join(failures) if failures else "No matching sources registered.")
        )

    @staticmethod
    def _is_partial(payload: object) -> bool:
        if not isinstance(payload, dict):
            return False
        if payload.get("partial") is True:
            return True
        raw = payload.get("raw")
        return bool(isinstance(raw, dict) and raw.get("partial") is True)

    def _source_by_name(self, name: str) -> Source | None:
        target = name.casefold()
        return next((source for source in self.registry.all() if source.name.casefold() == target), None)
