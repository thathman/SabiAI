from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from threading import Event, Lock
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
    source_names: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.request_key.strip():
            raise ValueError("Source request needs a stable request_key.")
        if not self.capability.strip():
            raise ValueError("Source request needs a capability.")
        if self.ttl_seconds < 0:
            raise ValueError("ttl_seconds cannot be negative.")
        self.source_names = tuple(str(name).strip() for name in self.source_names if str(name).strip())


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
    cache reuse, paid escalation, usage logging and duplicate in-flight request coalescing.

    A caller may set metadata.require_complete=true. In that mode a source can be healthy
    and useful yet still be too partial for the request; Sabi Boy records that fetch and
    continues to the next free source instead of treating partial coverage as complete.

    `source_names` is an explicit allow-list for cases where request metadata contains a
    provider-specific ID. This prevents a TheSportsDB team ID, for example, from being handed
    to ESPN simply because the first provider returned partial data.
    """

    _inflight_lock = Lock()
    _inflight: dict[tuple, Event] = {}

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
        allowed_names = {name.casefold() for name in request.source_names}
        cached = self._cached_response(request, now=now, require_complete=require_complete, allowed_names=allowed_names)
        if cached is not None:
            return cached

        # Multiple OpenClaw workers may ask for the same item at the same time. Only one
        # caller should spend the network/API request; waiters reuse the cache it writes.
        key = self._inflight_key(request, allow_paid=allow_paid, require_complete=require_complete)
        wait_seconds = max(1, int((request.metadata or {}).get("coalesce_wait_seconds", 30)))
        owner_event: Event | None = None
        while True:
            with self._inflight_lock:
                existing = self._inflight.get(key)
                if existing is None:
                    owner_event = Event()
                    self._inflight[key] = owner_event
                    break
            # Another worker owns this exact request. If it completes, prefer its cache.
            if not existing.wait(timeout=wait_seconds):
                # Do not deadlock behind a hung external request. A timed-out waiter may
                # proceed independently, but it never clears the original owner's marker.
                return self._execute_candidates(
                    request,
                    fetchers,
                    allow_paid=allow_paid,
                    paid_reason=paid_reason,
                    now=now,
                    require_complete=require_complete,
                    allowed_names=allowed_names,
                )
            cached = self._cached_response(
                request,
                now=datetime.now(timezone.utc),
                require_complete=require_complete,
                allowed_names=allowed_names,
            )
            if cached is not None:
                return cached
            # The owner failed without caching. Loop and one waiter becomes the next owner.

        try:
            return self._execute_candidates(
                request,
                fetchers,
                allow_paid=allow_paid,
                paid_reason=paid_reason,
                now=now,
                require_complete=require_complete,
                allowed_names=allowed_names,
            )
        finally:
            if owner_event is not None:
                with self._inflight_lock:
                    current = self._inflight.get(key)
                    if current is owner_event:
                        self._inflight.pop(key, None)
                        owner_event.set()

    def _cached_response(
        self,
        request: SourceRequest,
        *,
        now: datetime,
        require_complete: bool,
        allowed_names: set[str],
    ) -> SourceResponse | None:
        cached = self.database.get_cache(request.request_key, now=now)
        if cached is None:
            return None
        cached_allowed = not allowed_names or str(cached.get("source_name") or "").casefold() in allowed_names
        cached_complete = not (require_complete and self._is_partial(cached.get("payload")))
        if not cached_allowed or not cached_complete:
            return None
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

    def _execute_candidates(
        self,
        request: SourceRequest,
        fetchers: Mapping[str, Fetcher],
        *,
        allow_paid: bool,
        paid_reason: str | None,
        now: datetime,
        require_complete: bool,
        allowed_names: set[str],
    ) -> SourceResponse:
        failures: list[str] = []
        candidates = self.registry.candidates(
            sport=request.sport,
            capability=request.capability,
            include_paid=True,
        )
        if allowed_names:
            candidates = [source for source in candidates if source.name.casefold() in allowed_names]
        if request.source_names and not candidates:
            raise RuntimeError(
                "No registered source matched the explicit source selection: " + ", ".join(request.source_names)
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

            fetched_at = datetime.now(timezone.utc)
            expires_at = fetched_at + timedelta(seconds=request.ttl_seconds)
            self.database.put_cache(
                cache_key=request.request_key,
                source_name=source.name,
                sport=request.sport,
                capability=request.capability,
                payload=payload,
                fetched_at=fetched_at,
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
                fetched_at=fetched_at,
                failures=tuple(failures),
            )

        raise RuntimeError(
            "No source could satisfy the request. " + ("; ".join(failures) if failures else "No matching sources registered.")
        )

    def _inflight_key(self, request: SourceRequest, *, allow_paid: bool, require_complete: bool) -> tuple:
        return (
            str(self.database.path.expanduser().resolve()),
            request.request_key,
            request.capability.casefold(),
            (request.sport or "").casefold(),
            tuple(name.casefold() for name in request.source_names),
            require_complete,
            bool(allow_paid),
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
