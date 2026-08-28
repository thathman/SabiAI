from __future__ import annotations

from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sabiai.storage import CoverageStore, ResearchSliceStore, SabiDatabase

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
        self.coverage_store = CoverageStore(database)

    def run(self, *, day: str, events: list[dict[str, Any]], source_failures: list[str] | None = None) -> dict[str, Any]:
        run_id = datetime.now(timezone.utc).isoformat()
        # V2.4 deliberately decouples discovery from model analysis. The 30-minute
        # deterministic radar may contain thousands of events; only a bounded, sport-balanced
        # priced shortlist enters the model layer. The legacy same-day collector remains a
        # fallback and its richer rows are merged rather than discarded.
        events = merge_research_universe(
            self.settings,
            self.coverage_store,
            day=day,
            supplied=events,
        )
        slices = build_slices(day, events)
        all_rows: list[dict[str, Any]] = []
        failures = list(source_failures or [])
        slice_rows: list[dict[str, Any]] = []
        models: list[str] = []
        usage: dict[str, Any] = {"requests": 0, "cache_hits": 0, "input_tokens": 0, "output_tokens": 0}
        notes: list[str] = []
        if not slices:
            # Keep the scheduled job's provider-readiness failure visible even on a
            # no-fixture day. This is a tiny bounded probe, not a research request.
            from sabiai.system.research_heartbeat import call_research_model
            try:
                _, probe_model, probe_usage = call_research_model(
                    self.settings,
                    day=day,
                    events=[],
                    scope={"status": "no fixtures"},
                    max_tokens=400,
                )
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
                slice_rows.append(
                    self.store.record_run(
                        run_id=run_id,
                        scan_date=day,
                        scope=item.scope,
                        event_count=len(item.events),
                        status="skipped_no_price",
                        cache_hit=False,
                        events=list(item.events),
                        recommendations=[],
                        error="No usable decimal price in slice",
                    )
                )
                continue
            cached = self.store.get_cached(key)
            if cached:
                recs = cached.get("recommendations") or []
                all_rows.extend(recs)
                usage["cache_hits"] += 1
                if cached.get("model"):
                    models.append(str(cached["model"]))
                slice_rows.append(
                    self.store.record_run(
                        run_id=run_id,
                        scan_date=day,
                        scope=item.scope,
                        event_count=len(item.events),
                        status="cached",
                        cache_hit=True,
                        events=list(item.events),
                        recommendations=recs,
                        model=cached.get("model"),
                        usage=cached.get("usage") or {},
                    )
                )
            else:
                uncached.append((item, key))

        def research_one(pair):
            item, key = pair
            from sabiai.system.research_heartbeat import call_research_model, _validated_recommendations
            try:
                result, model, item_usage = call_research_model(
                    self.settings,
                    day=day,
                    events=list(item.events),
                    scope=item.scope,
                    max_tokens=1600,
                )
            except TypeError as exc:
                if "unexpected keyword" not in str(exc) and "got an unexpected" not in str(exc):
                    raise
                result, model, item_usage = call_research_model(self.settings, day=day, events=list(item.events))
            recs = _validated_recommendations(result, list(item.events))
            return item, key, recs, model, item_usage, result.get("notes") if isinstance(result, dict) else []

        with ThreadPoolExecutor(max_workers=max(1, int(self.settings.research_slice_workers))) as pool:
            futures = {pool.submit(research_one, pair): pair[0] for pair in uncached}
            for future in as_completed(futures):
                item = futures[future]
                try:
                    slice_item, key, recs, model, item_usage, item_notes = future.result()
                    # SQLite writes stay on the coordinator thread; concurrent cache writes
                    # recreate the lock contention this layer is designed to avoid.
                    self.store.put_cached(
                        cache_key=key,
                        scan_date=day,
                        scope=slice_item.scope,
                        events=list(slice_item.events),
                        recommendations=recs,
                        model=model,
                        usage=item_usage,
                        ttl_seconds=self.settings.research_slice_ttl_seconds,
                    )
                    if isinstance(item_notes, list):
                        notes.extend(str(note).strip()[:500] for note in item_notes if str(note).strip())
                    all_rows.extend(recs)
                    models.append(model)
                    usage["requests"] += 1
                    _sum_usage(usage, item_usage)
                    slice_rows.append(
                        self.store.record_run(
                            run_id=run_id,
                            scan_date=day,
                            scope=slice_item.scope,
                            event_count=len(slice_item.events),
                            status="completed",
                            cache_hit=False,
                            events=list(slice_item.events),
                            recommendations=recs,
                            model=model,
                            usage=item_usage,
                        )
                    )
                except Exception as exc:
                    error = str(exc)[:500]
                    failures.append(f"{item.sport}/{item.country}/{item.competition}/{item.division}: {error}")
                    slice_rows.append(
                        self.store.record_run(
                            run_id=run_id,
                            scan_date=day,
                            scope=item.scope,
                            event_count=len(item.events),
                            status="failed",
                            cache_hit=False,
                            events=list(item.events),
                            recommendations=[],
                            source_failures=[error],
                            error=error,
                        )
                    )

        selected = CrossSportDecisionPass(max_recommendations=self.settings.research_max_recommendations).select(all_rows)
        coverage = selected["coverage"]
        coverage["slice_count"] = len(slices)
        coverage["cache_hits"] = sum(1 for row in slice_rows if row.get("cache_hit"))
        coverage["failed_slices"] = sum(1 for row in slice_rows if row.get("status") == "failed")
        coverage["research_universe_events"] = len(events)
        coverage["slices"] = [
            {key: row.get(key) for key in ("sport", "country", "competition", "division", "event_count", "status", "cache_hit", "error")}
            for row in sorted(
                slice_rows,
                key=lambda row: (
                    row.get("sport", ""),
                    row.get("country", ""),
                    row.get("competition", ""),
                    row.get("division", ""),
                ),
            )
        ]

        discovery_run_id = self.coverage_store.latest_run_id()
        if discovery_run_id:
            researched_count = len({(item.sport, str(event.get("event") or "")) for item in slices for event in item.events})
            self.coverage_store.update_run(
                discovery_run_id,
                prefiltered_events=len(events),
                researched_events=researched_count,
                selected_recommendations=len(selected["recommendations"]),
            )
            coverage["discovery_funnel"] = self.coverage_store.funnel(discovery_run_id)

        return {
            "run_id": run_id,
            "recommendations": selected["recommendations"],
            "all_recommendations": selected["all_recommendations"],
            "coverage": coverage,
            "slice_rows": slice_rows,
            "failures": failures,
            "model": ", ".join(dict.fromkeys(models)) or "none",
            "usage": usage,
            "notes": list(dict.fromkeys(notes))[:30],
        }


def merge_research_universe(settings, coverage_store: CoverageStore, *, day: str, supplied: list[dict[str, Any]]) -> list[dict[str, Any]]:
    limit = max(1, int(getattr(settings, "research_max_events", 120)))
    prefilter_limit = max(limit, int(getattr(settings, "prefilter_max_events", 300)))
    try:
        radar = coverage_store.research_candidates(
            day,
            timezone_name=getattr(settings, "timezone", "Africa/Lagos"),
            limit=prefilter_limit,
        )
    except Exception:
        radar = []

    merged: dict[tuple[str, str, str], dict[str, Any]] = {}
    for item in [*radar, *supplied]:
        if not isinstance(item, dict):
            continue
        event = str(item.get("event") or "").strip()
        if not event:
            continue
        key = (
            str(item.get("sport") or "unknown").casefold(),
            _norm_event(event),
            str(item.get("starts_at") or "")[:16],
        )
        existing = merged.get(key)
        merged[key] = _prefer_richer(existing, item) if existing else dict(item)

    # Research breadth should not be determined by iteration order. Round-robin through
    # sports after each sport's events are ranked by market/source richness.
    buckets: dict[str, deque[dict[str, Any]]] = defaultdict(deque)
    by_sport: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in merged.values():
        by_sport[str(item.get("sport") or "unknown")].append(item)
    for sport, rows in by_sport.items():
        rows.sort(key=lambda item: (-_event_richness(item), str(item.get("starts_at") or ""), str(item.get("event") or "")))
        buckets[sport] = deque(rows)

    result: list[dict[str, Any]] = []
    while buckets and len(result) < limit:
        progressed = False
        for sport in sorted(list(buckets)):
            bucket = buckets[sport]
            if bucket:
                result.append(bucket.popleft())
                progressed = True
            if not bucket:
                buckets.pop(sport, None)
            if len(result) >= limit:
                break
        if not progressed:
            break
    return result


def build_slices(day: str, events: list[dict[str, Any]]) -> list[ResearchSlice]:
    grouped: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    for event in events:
        key = tuple(str(event.get(field) or "Unresolved") for field in ("sport", "country", "competition", "division"))
        grouped.setdefault(key, []).append(event)
    return [ResearchSlice(day, *key, tuple(rows)) for key, rows in sorted(grouped.items())]


def _prefer_richer(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    winner, other = (right, left) if _event_richness(right) >= _event_richness(left) else (left, right)
    merged = dict(other)
    merged.update({key: value for key, value in winner.items() if value not in (None, "", [])})
    left_odds = left.get("odds") if isinstance(left.get("odds"), list) else []
    right_odds = right.get("odds") if isinstance(right.get("odds"), list) else []
    seen: set[tuple] = set()
    combined = []
    for row in [*left_odds, *right_odds]:
        if not isinstance(row, dict):
            continue
        key = (
            str(row.get("market") or ""),
            str(row.get("label") or ""),
            str(row.get("line") or ""),
            str(row.get("period") or ""),
            str(row.get("bookmaker") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        combined.append(row)
    if combined:
        merged["odds"] = combined[:80]
    return merged


def _event_richness(item: dict[str, Any]) -> float:
    odds = item.get("odds") if isinstance(item.get("odds"), list) else []
    families = {
        str(row.get("market") or "")
        for row in odds
        if isinstance(row, dict) and str(row.get("market") or "")
    }
    books = {
        str(row.get("bookmaker") or "")
        for row in odds
        if isinstance(row, dict) and str(row.get("bookmaker") or "")
    }
    return float(len(odds)) + (len(families) * 4.0) + (len(books) * 2.0) + float(item.get("source_count") or 0)


def _norm_event(value: str) -> str:
    return "".join(ch for ch in value.casefold() if ch.isalnum())


def _sum_usage(total: dict[str, Any], usage: object) -> None:
    if not isinstance(usage, dict):
        return
    for key in ("prompt_tokens", "completion_tokens", "total_tokens", "input_tokens", "output_tokens"):
        try:
            total[key] = int(total.get(key, 0)) + int(usage.get(key) or 0)
        except (TypeError, ValueError):
            continue
