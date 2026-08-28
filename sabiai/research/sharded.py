from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sabiai.storage import ResearchSliceStore, SabiDatabase

from .decision import CrossSportDecisionPass


@dataclass(frozen=True)
class ResearchSlice:
    scan_date: str
    sport: str
    country: str
    competition: str
    division: str
    events: tuple[dict[str, Any], ...]

    @property
    def scope(self) -> dict[str, str]:
        return {key: getattr(self, key) for key in ("sport", "country", "competition", "division")}


class ShardedDailyResearch:
    def __init__(self, settings, database: SabiDatabase):
        self.settings = settings
        self.database = database
        self.store = ResearchSliceStore(database)

    def run(self, *, day: str, events: list[dict[str, Any]], source_failures: list[str] | None = None) -> dict[str, Any]:
        run_id = datetime.now(timezone.utc).isoformat()
        slices = build_slices(day, events)
        all_rows: list[dict[str, Any]] = []
        failures = list(source_failures or [])
        slice_rows: list[dict[str, Any]] = []
        models: list[str] = []
        usage: dict[str, Any] = {"requests": 0, "cache_hits": 0, "input_tokens": 0, "output_tokens": 0}
        notes: list[str] = []
        if not slices:
            # Keep the scheduled job's provider-readiness failure visible even
            # on a no-fixture day. This is a tiny bounded probe, not a research
            # request, and lets the job retry rather than silently reporting a
            # healthy run when the configured model is unavailable.
            from sabiai.system.research_heartbeat import call_research_model
            try:
                _, probe_model, probe_usage = call_research_model(self.settings, day=day, events=[], scope={"status": "no fixtures"}, max_tokens=400)
                models.append(probe_model)
                usage["requests"] = 1
                _sum_usage(usage, probe_usage)
            except TypeError as exc:
                if "unexpected keyword" not in str(exc) and "got an unexpected" not in str(exc):
                    raise
                _, probe_model, probe_usage = call_research_model(self.settings, day=day, events=[])
                models.append(probe_model)
                usage["requests"] = 1
                _sum_usage(usage, probe_usage)
        uncached: list[tuple[ResearchSlice, str]] = []
        for item in slices:
            key = self.store.cache_key(day, item.scope, item.events)
            if not any(event.get("odds") for event in item.events):
                # The direct analyst is price-bound. Do not spend a model call
                # on a slice that cannot produce a validated recommendation.
                slice_rows.append(self.store.record_run(run_id=run_id, scan_date=day, scope=item.scope, event_count=len(item.events), status="skipped_no_price", cache_hit=False, events=list(item.events), recommendations=[], source_failures=["No usable decimal price in slice"]))
                continue
            cached = self.store.get_cached(key)
            if cached:
                recs = cached.get("recommendations") or []
                all_rows.extend(recs)
                usage["cache_hits"] += 1
                if cached.get("model"):
                    models.append(str(cached["model"]))
                slice_rows.append(self.store.record_run(run_id=run_id, scan_date=day, scope=item.scope, event_count=len(item.events), status="cached", cache_hit=True, events=list(item.events), recommendations=recs, model=cached.get("model"), usage=cached.get("usage") or {}))
            else:
                uncached.append((item, key))
        def research_one(pair):
            item, key = pair
            # Local import prevents the heartbeat module from importing this
            # orchestration module before its validation helpers exist.
            from sabiai.system.research_heartbeat import call_research_model, _validated_recommendations
            try:
                result, model, item_usage = call_research_model(self.settings, day=day, events=list(item.events), scope=item.scope, max_tokens=1600)
            except TypeError as exc:
                # Keep compatibility with test doubles and older local adapters
                # that expose the original three-argument callable.
                if "unexpected keyword" not in str(exc) and "got an unexpected" not in str(exc):
                    raise
                result, model, item_usage = call_research_model(self.settings, day=day, events=list(item.events))
            recs = _validated_recommendations(result, list(item.events))
            # SQLite writes stay on the coordinator thread. The model calls may
            # run concurrently, but concurrent cache writes would recreate the
            # database-lock condition this layer is meant to avoid.
            return item, key, recs, model, item_usage, result.get("notes") if isinstance(result, dict) else []
        with ThreadPoolExecutor(max_workers=max(1, int(self.settings.research_slice_workers))) as pool:
            futures = {pool.submit(research_one, pair): pair[0] for pair in uncached}
            for future in as_completed(futures):
                item = futures[future]
                try:
                    slice_item, key, recs, model, item_usage, item_notes = future.result()
                    self.store.put_cached(cache_key=key, scan_date=day, scope=slice_item.scope, events=list(slice_item.events), recommendations=recs, model=model, usage=item_usage, ttl_seconds=self.settings.research_slice_ttl_seconds)
                    if isinstance(item_notes, list):
                        notes.extend(str(note).strip()[:500] for note in item_notes if str(note).strip())
                    all_rows.extend(recs)
                    models.append(model)
                    usage["requests"] += 1
                    _sum_usage(usage, item_usage)
                    slice_rows.append(self.store.record_run(run_id=run_id, scan_date=day, scope=slice_item.scope, event_count=len(slice_item.events), status="completed", cache_hit=False, events=list(slice_item.events), recommendations=recs, model=model, usage=item_usage))
                except Exception as exc:
                    error = str(exc)[:500]
                    failures.append(f"{item.sport}/{item.country}/{item.competition}/{item.division}: {error}")
                    slice_rows.append(self.store.record_run(run_id=run_id, scan_date=day, scope=item.scope, event_count=len(item.events), status="failed", cache_hit=False, events=list(item.events), recommendations=[], source_failures=[error], error=error))
        selected = CrossSportDecisionPass(max_recommendations=self.settings.research_max_recommendations).select(all_rows)
        coverage = selected["coverage"]
        coverage["slice_count"] = len(slices)
        coverage["cache_hits"] = sum(1 for row in slice_rows if row.get("cache_hit"))
        coverage["failed_slices"] = sum(1 for row in slice_rows if row.get("status") == "failed")
        coverage["slices"] = [{key: row.get(key) for key in ("sport", "country", "competition", "division", "event_count", "status", "cache_hit", "error")} for row in sorted(slice_rows, key=lambda row: (row.get("sport", ""), row.get("country", ""), row.get("competition", ""), row.get("division", "")))]
        return {"run_id": run_id, "recommendations": selected["recommendations"], "all_recommendations": selected["all_recommendations"], "coverage": coverage, "slice_rows": slice_rows, "failures": failures, "model": ", ".join(dict.fromkeys(models)) or "none", "usage": usage, "notes": list(dict.fromkeys(notes))[:30]}


def build_slices(day: str, events: list[dict[str, Any]]) -> list[ResearchSlice]:
    grouped: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    for event in events:
        key = tuple(str(event.get(field) or "Unresolved") for field in ("sport", "country", "competition", "division"))
        grouped.setdefault(key, []).append(event)
    return [ResearchSlice(day, *key, tuple(rows)) for key, rows in sorted(grouped.items())]


def _sum_usage(total: dict[str, Any], usage: object) -> None:
    if not isinstance(usage, dict):
        return
    for key in ("prompt_tokens", "completion_tokens", "total_tokens", "input_tokens", "output_tokens"):
        try:
            total[key] = int(total.get(key, 0)) + int(usage.get(key) or 0)
        except (TypeError, ValueError):
            continue
