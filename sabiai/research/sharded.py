from __future__ import annotations

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sabiai.storage import CoverageStore, ResearchSliceStore, SabiDatabase

from .decision import CrossSportDecisionPass
from .market_inventory import MarketInventoryNormalizer
from .prefilter import CoveragePrefilter, canonical_action_book


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
                        error="No verified SportyBet/Bet9ja decimal price in slice",
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
            self.coverage_store.update_run(
                discovery_run_id,
                prefiltered_events=len(events),
                researched_events=len(events),
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


def merge_research_universe(
    settings,
    coverage_store: CoverageStore,
    *,
    day: str,
    supplied: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Merge today's verified action-book packet into the large deterministic radar.

    The legacy/direct collector is still useful because it can carry fresh SportyBet prices.
    Persist those prices into the market inventory first. The prefilter can then compare them
    against broad sensor consensus while exposing only action-book prices to the model.
    """

    _persist_supplied_action_prices(coverage_store, supplied)
    research_limit = max(1, int(getattr(settings, "research_max_events", 120)))
    prefilter_limit = max(research_limit, int(getattr(settings, "prefilter_max_events", 300)))
    try:
        radar = CoveragePrefilter(settings, coverage_store).select(
            day,
            limit=prefilter_limit,
            actionable_only=True,
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
        if item in supplied and not canonical_action_book(item.get("source")):
            # Automatic research is price-bound to the two action books. Sensor-only supplied
            # rows remain in CoverageStore/radar and can still be researched on demand.
            continue
        key = (
            str(item.get("sport") or "unknown").casefold(),
            _norm_event(event),
            str(item.get("starts_at") or "")[:16],
        )
        existing = merged.get(key)
        merged[key] = _prefer_richer(existing, item) if existing else dict(item)

    return _breadth_then_quality(settings, list(merged.values()), research_limit)


def _persist_supplied_action_prices(store: CoverageStore, supplied: list[dict[str, Any]]) -> None:
    now = datetime.now(timezone.utc)
    for item in supplied:
        if not isinstance(item, dict):
            continue
        source = canonical_action_book(item.get("source"))
        if not source or not isinstance(item.get("odds"), list) or not item.get("odds"):
            continue
        event = _semantic_action_odds(dict(item), source)
        try:
            event_id = store.upsert_event(
                event,
                source_name=source,
                source_payload=event,
                now=now,
            )
            catalogue, offers = MarketInventoryNormalizer(source).embedded(event, event_id=event_id)
            for market in catalogue:
                store.upsert_market(event_id, market)
            for offer in offers:
                store.record_offer(event_id, offer)
        except (TypeError, ValueError):
            # A malformed direct-source row should not break the rest of the daily universe.
            continue


def _semantic_action_odds(event: dict[str, Any], source: str) -> dict[str, Any]:
    home = str(event.get("home") or "").strip()
    away = str(event.get("away") or "").strip()
    normalized = []
    for row in event.get("odds") or []:
        if not isinstance(row, dict):
            continue
        item = dict(row)
        raw_label = str(item.get("label") or "").strip()
        key = _norm_event(raw_label)
        if key in {"home", "homeodds"} and home:
            item["label"] = home
            item.setdefault("market", "winner")
        elif key in {"away", "awayodds"} and away:
            item["label"] = away
            item.setdefault("market", "winner")
        elif key in {"draw", "drawodds", "tie"}:
            item["label"] = "Draw"
            item.setdefault("market", "winner")
        item["bookmaker"] = source
        normalized.append(item)
    event["odds"] = normalized
    event["source"] = source
    return event


def _breadth_then_quality(settings, rows: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    rows.sort(
        key=lambda item: (
            -_event_richness(item),
            str(item.get("starts_at") or ""),
            str(item.get("event") or ""),
        )
    )
    min_per_sport = max(1, int(getattr(settings, "research_min_events_per_active_sport", 2)))
    max_per_sport = max(min_per_sport, int(getattr(settings, "research_max_events_per_sport", 40)))
    by_sport: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in rows:
        by_sport[str(item.get("sport") or "unknown")].append(item)

    selected: list[dict[str, Any]] = []
    selected_ids: set[tuple[str, str, str]] = set()
    counts: dict[str, int] = defaultdict(int)

    def identifier(item: dict[str, Any]) -> tuple[str, str, str]:
        return (
            str(item.get("sport") or "unknown"),
            _norm_event(str(item.get("event") or "")),
            str(item.get("starts_at") or "")[:16],
        )

    for round_index in range(min_per_sport):
        for sport in sorted(by_sport):
            if len(selected) >= limit:
                break
            sport_rows = by_sport[sport]
            if round_index >= len(sport_rows):
                continue
            item = sport_rows[round_index]
            selected.append(item)
            selected_ids.add(identifier(item))
            counts[sport] += 1

    for item in rows:
        if len(selected) >= limit:
            break
        sport = str(item.get("sport") or "unknown")
        key = identifier(item)
        if key in selected_ids or counts[sport] >= max_per_sport:
            continue
        selected.append(item)
        selected_ids.add(key)
        counts[sport] += 1
    return selected


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
    consensus = item.get("market_consensus") if isinstance(item.get("market_consensus"), list) else []
    disagreement = max(
        (float(row.get("price_disagreement_pct") or 0) for row in consensus if isinstance(row, dict)),
        default=0.0,
    )
    return (
        float(len(odds))
        + (len(families) * 4.0)
        + (len(books) * 2.0)
        + float(item.get("source_count") or 0)
        + min(disagreement, 12.0)
    )


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
