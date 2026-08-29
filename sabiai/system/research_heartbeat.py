from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import InvalidOperation
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from sabiai.config import Settings
from sabiai.notifications import PushDeliveryReport, WebPushService
from sabiai.sources import SourceRequest, SourceService, default_source_bundle
from sabiai.storage import BankrollLedger, DailyResearchLog, PickRecordService, SabiDatabase, StrategyPlanStore
from sabiai.research import ActionPriceEnricher, ShardedDailyResearch
from sabiai.strategy import StrategyChainStore, StrategyLearningService, StrategyPlanner, StrategyTicketService

from .jobs import JobService


_LEAGUES = {
    "football": ("eng.1", "soccer"),
    "soccer": ("eng.1", "soccer"),
    "basketball": ("nba", "basketball"),
    "baseball": ("mlb", "baseball"),
    "ice_hockey": ("nhl", "hockey"),
    "ice hockey": ("nhl", "hockey"),
}

_SCOPE_DEFAULTS = {
    "football": ("England", "1"),
    "soccer": ("England", "1"),
    "basketball": ("USA", "1"),
    "baseball": ("USA", "1"),
    "ice_hockey": ("USA", "1"),
    "ice hockey": ("USA", "1"),
}


def _local_date(settings: Settings, now: datetime | None = None) -> str:
    try:
        zone = ZoneInfo(settings.timezone)
    except Exception:
        zone = timezone.utc
    return (now or datetime.now(timezone.utc)).astimezone(zone).date().isoformat()


def _request_key(
    sport: str,
    day: str,
    source: str | None = None,
    capability: str = "fixtures",
) -> str:
    digest = hashlib.sha256(
        f"daily-fixtures|{capability}|{sport}|{day}|{source or 'fallback'}".encode()
    ).hexdigest()[:24]
    return f"daily-fixtures:{digest}"


def collect_fixtures(
    settings: Settings,
    *,
    now: datetime | None = None,
    max_events: int | None = None,
) -> tuple[str, list[dict[str, Any]], list[str]]:
    """Collect a small, normalized fixture packet using direct source adapters only."""

    max_events = max(1, int(max_events if max_events is not None else getattr(settings, "research_max_events", 60)))
    database = SabiDatabase(settings.v2_db)
    database.initialize()
    bundle = default_source_bundle(settings)
    service = SourceService(database, bundle.registry)
    day = _local_date(settings, now)
    events: list[dict[str, Any]] = []
    failures: list[str] = []
    seen: set[tuple[str, str]] = set()

    configured_sports = [str(raw).strip().casefold() for raw in settings.research_sports if str(raw).strip()]
    # Divide the daily event budget before collection starts. This gives every
    # configured sport a turn and prevents the first football response from
    # exhausting the global budget.
    sport_budget = max(1, max_events // max(1, len(configured_sports)))
    per_sport_limit = max(1, min(int(getattr(settings, "research_max_events_per_sport", 20)), sport_budget))
    sport_counts: dict[str, int] = {}
    for raw_sport in configured_sports:
        sport = str(raw_sport).strip().casefold()
        if not sport:
            continue
        league, espn_sport = _LEAGUES.get(sport, (None, None))
        metadata: dict[str, Any] = {"date": day}
        if league:
            metadata.update({"league": league, "league_slug": league, "espn_sport": espn_sport})
        # Use the Nigerian bookmaker feed first where configured, then use
        # Parse's odds-bearing Flashscore/ESPN feeds to fill non-football and
        # missing-price coverage.  The final generic request remains a
        # schedule-only fallback.  Each provider gets its own cache key so a
        # schedule response can never mask a later odds response.
        attempts: list[tuple[str, str | None, dict[str, Any], bool]] = []
        if (
            "Parse · SportyBet" in bundle.fetchers
            and sport in {"football", "soccer", "basketball", "ice_hockey"}
        ):
            attempts.append(("fixtures", "Parse · SportyBet", metadata, True))
        if "Parse · Flashscore" in bundle.fetchers:
            attempts.append(
                (
                    "fixtures_with_odds",
                    "Parse · Flashscore",
                    {"sport": sport, "day_offset": 0},
                    True,
                )
            )
        if "Parse · ESPN" in bundle.fetchers and league:
            attempts.append(
                (
                    "fixtures_with_odds",
                    "Parse · ESPN",
                    {
                        "league": league,
                        "dates": day.replace("-", ""),
                        "limit": per_sport_limit,
                    },
                    True,
                )
            )
        attempts.append(("fixtures", None, metadata, False))

        sport_events_added = False
        sport_price_source_succeeded = False
        for capability, source_name, request_metadata, price_capable in attempts:
            request = SourceRequest(
                request_key=_request_key(sport, day, source_name, capability),
                capability=capability,
                sport=sport,
                ttl_seconds=900,
                metadata=request_metadata,
                source_names=(source_name,) if source_name else (),
            )
            try:
                response = service.execute(request, bundle.fetchers, allow_paid=False)
                failures.extend(getattr(response, "failures", ()) or ())
                provider_sport = _provider_sport(response.payload)
                if provider_sport and not _same_sport(provider_sport, sport):
                    raise RuntimeError(
                        f"{response.source_name} returned {provider_sport} data for requested {sport}; ignored."
                    )
                default_country, default_division = _SCOPE_DEFAULTS.get(sport, ("Unresolved", "Unresolved"))
                for event in _normalize_events(response.payload, sport=sport, source=response.source_name):
                    event.setdefault("competition", league or "Unresolved")
                    event.setdefault("country", default_country)
                    event.setdefault("division", default_division)
                    # Providers may return a useful surrounding schedule even when
                    # a date was supplied. A daily run must never promote a future
                    # or past fixture; enforce the local calendar date here.
                    if _event_local_date(event.get("starts_at"), settings.timezone) != day:
                        continue
                    key = _event_merge_key(event, settings.timezone)
                    if not key[0]:
                        continue
                    existing_index = next(
                        (index for index, row in enumerate(events) if _event_merge_key(row, settings.timezone) == key),
                        None,
                    )
                    if existing_index is not None:
                        _merge_event(events[existing_index], event)
                        continue
                    if sport_counts.get(sport, 0) >= per_sport_limit or len(events) >= max_events:
                        continue
                    events.append(event)
                    seen.add(key)
                    sport_counts[sport] = sport_counts.get(sport, 0) + 1
                    sport_events_added = True
                    if len(events) >= max_events:
                        break
                if price_capable and any(
                    item.get("sport") == sport and item.get("odds") for item in events
                ):
                    sport_price_source_succeeded = True
            except Exception as exc:
                failures.append(f"{sport}{f' via {source_name}' if source_name else ''}: {_safe_error(exc)}")

            # A source that supplied a full per-sport budget with prices is
            # sufficient; avoid spending another provider credit. If prices
            # are still missing, continue through the odds-capable attempts so
            # one provider's sparse coverage can be enriched by another.
            sport_rows = [item for item in events if item.get("sport") == sport]
            has_full_priced_budget = (
                len(sport_rows) >= per_sport_limit
                and all(item.get("odds") for item in sport_rows)
            )
            if has_full_priced_budget and price_capable:
                break
            if len(events) >= max_events:
                break
            if source_name is None and (sport_events_added or sport_price_source_succeeded):
                break
        if len(events) >= max_events:
            break

    return day, events[:max_events], failures


def _event_local_date(value: object, timezone_name: str) -> str | None:
    """Return an event's local calendar date for strict daily-scan filtering."""

    if value is None or not str(value).strip():
        return None
    try:
        zone = ZoneInfo(timezone_name)
    except Exception:
        zone = timezone.utc
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            epoch = float(value)
            if epoch > 100_000_000_000:
                epoch /= 1000
            return datetime.fromtimestamp(epoch, timezone.utc).astimezone(zone).date().isoformat()
        except (OverflowError, OSError, ValueError):
            return None
    text = str(value).strip()
    if text.isdigit():
        try:
            epoch = float(text)
            if epoch > 100_000_000_000:
                epoch /= 1000
            return datetime.fromtimestamp(epoch, timezone.utc).astimezone(zone).date().isoformat()
        except (OverflowError, OSError, ValueError):
            return None
    try:
        if len(text) == 10:
            return date.fromisoformat(text).isoformat()
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(zone).date().isoformat()


def _event_merge_key(event: dict[str, Any], timezone_name: str) -> tuple[str, str]:
    """Build a provider-independent key for merging the same day's fixture."""

    name = _norm(str(event.get("event") or ""))
    local_day = _event_local_date(event.get("starts_at"), timezone_name)
    return name, local_day or str(event.get("starts_at") or "")


def _provider_sport(payload: object) -> str | None:
    """Read a source-declared sport when a provider exposes one at the envelope level."""

    if not isinstance(payload, dict):
        return None
    raw = payload.get("raw")
    data = raw.get("data") if isinstance(raw, dict) and isinstance(raw.get("data"), dict) else None
    for candidate in (data, raw, payload):
        if isinstance(candidate, dict):
            value = candidate.get("sport")
            if value is not None and str(value).strip():
                return str(value).strip()
    return None


def _same_sport(left: str, right: str) -> bool:
    aliases = {
        "soccer": "football",
        "ice_hockey": "hockey",
        "ice hockey": "hockey",
        "table tennis": "table_tennis",
        "beach volleyball": "beach_volleyball",
        "american football": "american_football",
    }
    left_key = aliases.get(left.casefold().replace("-", "_"), left.casefold().replace("-", "_"))
    right_key = aliases.get(right.casefold().replace("-", "_"), right.casefold().replace("-", "_"))
    return left_key == right_key


def _merge_event(target: dict[str, Any], incoming: dict[str, Any]) -> None:
    """Merge richer provider fields without replacing the original fixture identity."""

    for key in ("home", "away", "competition", "country", "division", "starts_at", "event_id"):
        if not target.get(key) and incoming.get(key):
            target[key] = incoming[key]
    incoming_odds = incoming.get("odds")
    if not isinstance(incoming_odds, list) or not incoming_odds:
        return
    merged: list[dict[str, Any]] = [item for item in target.get("odds", []) if isinstance(item, dict)]
    existing_keys = {
        (_norm(str(item.get("label") or "")), str(item.get("decimal_odds") or ""))
        for item in merged
    }
    for item in incoming_odds:
        if not isinstance(item, dict):
            continue
        key = (_norm(str(item.get("label") or "")), str(item.get("decimal_odds") or ""))
        if key not in existing_keys:
            merged.append(item)
            existing_keys.add(key)
    target["odds"] = merged
    sources = target.setdefault("odds_sources", [])
    incoming_source = str(incoming.get("source") or "").strip()
    if incoming_source and incoming_source not in sources:
        sources.append(incoming_source)
    target["price_source"] = incoming_source or target.get("price_source")


def _normalize_events(payload: object, *, sport: str, source: str) -> Iterable[dict[str, Any]]:
    for row in _event_rows(payload):
        name = _first(row, "strEvent", "event", "name", "shortName", "displayName")
        # Parse/Flashscore uses home_team/away_team objects while ESPN uses a
        # competitors array.  Keep both shapes in the same canonical event
        # packet so a price-bearing fixture source can feed every sport.
        home = _first(row, "strHomeTeam", "homeTeamName", "homeTeam", "home_team", "home", "home_name")
        away = _first(row, "strAwayTeam", "awayTeamName", "awayTeam", "away_team", "away", "away_name")
        competitions = row.get("competitions") if isinstance(row.get("competitions"), list) else []
        competitors = row.get("competitors") if isinstance(row.get("competitors"), list) else []
        if (not home or not away) and competitions and isinstance(competitions[0], dict):
            competitors = competitions[0].get("competitors") if isinstance(competitions[0].get("competitors"), list) else []
        if not home or not away:
            for competitor in competitors:
                if not isinstance(competitor, dict):
                    continue
                team = competitor.get("team") if isinstance(competitor.get("team"), dict) else competitor
                label = _first(team, "displayName", "name", "shortName")
                if competitor.get("homeAway") == "home":
                    home = home or label
                elif competitor.get("homeAway") == "away":
                    away = away or label
        if not name and home and away:
            name = f"{home} vs {away}"
        if not name:
            continue
        starts_at = _first(row, "strTimestamp", "date", "startTime", "start_time", "dateEvent", "starts_at", "kickoffTime")
        league = _first(row, "strLeague", "tournament", "league", "competition", "category")
        competition_row = competitions[0] if competitions and isinstance(competitions[0], dict) else {}
        competition_details = row.get("competition") if isinstance(row.get("competition"), dict) else {}
        country = _first(row, "strCountry", "country", "countryName", "country_name", "region", "nation")
        division = _first(row, "strDivision", "division", "divisionName", "division_name", "tier", "level", "leagueLevel")
        if isinstance(competition_row, dict):
            league_obj = competition_row.get("league") if isinstance(competition_row.get("league"), dict) else {}
            country = country or _first(competition_row, "country", "countryName", "region") or _first(league_obj, "country", "countryName")
            division = division or _first(competition_row, "division", "divisionName", "tier", "level") or _first(league_obj, "division", "divisionName", "tier", "level")
            league = league or _first(competition_row, "name", "displayName") or _first(league_obj, "name", "displayName")
        if competition_details:
            country = country or _first(competition_details, "country", "countryName", "region")
            division = division or _first(competition_details, "division", "divisionName", "tier", "level")
            league = league or _first(competition_details, "name", "displayName", "league")
        event_id = _first(row, "idEvent", "eventId", "match_id", "id", "uid")
        item: dict[str, Any] = {
            "sport": sport,
            "event": name,
            "home": home,
            "away": away,
            "competition": league,
            "country": country,
            "division": division,
            "starts_at": starts_at,
            "event_id": event_id,
            "source": source,
        }
        odds = _extract_odds(row)
        if odds:
            item["odds"] = odds
        yield {key: value for key, value in item.items() if value not in (None, "", [])}


def _event_rows(payload: object) -> Iterable[dict[str, Any]]:
    """Find event-like rows in adapter payloads without passing raw provider blobs to a model."""

    candidates: list[dict[str, Any]] = []
    if isinstance(payload, dict):
        raw = payload.get("raw")
        if isinstance(raw, dict):
            candidates.extend(_nested_event_rows(raw))
        candidates.extend(_nested_event_rows(payload))
    for item in candidates:
        yield item


def _extract_odds(row: dict[str, Any]) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []

    def visit(value: object, label: str = "") -> None:
        if len(values) >= 12:
            return
        if isinstance(value, dict):
            for key, child in value.items():
                key_text = str(key).casefold()
                if key_text in {"odds", "markets", "market", "prices", "selections", "outcomes"}:
                    visit(child, str(key))
                elif key_text in {
                    "decimalodds",
                    "decimal_odds",
                    "price",
                    "odd",
                    "homeodds",
                    "drawodds",
                    "awayodds",
                    "home_win",
                    "draw",
                    "away_win",
                }:
                    try:
                        numeric = float(child)
                    except (TypeError, ValueError):
                        continue
                    if numeric > 1:
                        values.append({"label": label or str(key), "decimal_odds": numeric})
                elif isinstance(child, (dict, list)):
                    visit(child, str(key))
        elif isinstance(value, list):
            for child in value:
                visit(child, label)

    visit(row)
    return values


def call_research_model(
    settings: Settings,
    *,
    day: str,
    events: list[dict[str, Any]],
    scope: dict[str, str] | None = None,
    max_tokens: int = 2200,
) -> tuple[dict[str, Any], str, dict[str, Any]]:
    if not settings.research_api_key:
        raise RuntimeError(
            "Direct research model key is not configured. Set SABIAI_RESEARCH_API_KEY "
            "or ALIYUN_TOKEN_PLAN_COMPATIBLE_KEY in the private runtime environment."
        )
    packet = {"date": day, "scope": scope or {}, "events": events}
    prompt = (
        "You are the compact Sabi Boy daily pick analyst. Use only the supplied fixture packet; "
        "never invent an event, price, injury, result or source. Return JSON only in this shape: "
        '{"recommendations":[{"sport":"...","event":"exact supplied event","market":"...",'
        '"pick":"...","decimal_odds":2.1,"confidence_pct":65,"estimated_probability_pct":67,"reason":"..."}],'
        '"notes":["..."]}. Recommend only when the packet includes a usable decimal price; '
        "otherwise return no recommendation and explain the missing price in notes. Use decimal odds "
        "and confidence percentages. Include estimated_probability_pct only when justified by the supplied packet. Never recommend Stake or 1xBet, never claim a bet was placed, "
        "and never write to a betting ledger. Keep reasons short and identify the supplied source.\n\n"
        + json.dumps(packet, ensure_ascii=False, separators=(",", ":"))
    )
    body = {
        "model": settings.research_model,
        "messages": [
            {"role": "system", "content": "Return valid JSON only. Do not use markdown fences."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0,
        "max_tokens": max(400, int(max_tokens)),
    }
    try:
        response = _post_chat(settings.research_api_base_url, settings.research_api_key, body)
        model = str(response.get("model") or settings.research_model)
        return _parse_model_result(response), model, response.get("usage") or {}
    except Exception as primary_exc:
        if not (
            settings.research_fallback_model
            and settings.research_fallback_api_key
            and settings.research_fallback_api_base_url
        ):
            raise RuntimeError(f"Primary research model failed: {_safe_error(primary_exc)}") from primary_exc
        # Keep fallback responses compact: this path is for availability, not
        # for expanding the research context or spending a second full budget.
        fallback_body = {
            **body,
            "model": settings.research_fallback_model,
            "max_tokens": min(int(body.get("max_tokens") or 2200), 1600),
        }
        try:
            response = _post_chat(
                settings.research_fallback_api_base_url,
                settings.research_fallback_api_key,
                fallback_body,
            )
            model = str(response.get("model") or settings.research_fallback_model)
            return _parse_model_result(response), model, response.get("usage") or {}
        except Exception as fallback_exc:
            raise RuntimeError(
                "Primary and fallback research models failed: "
                f"primary={_safe_error(primary_exc)}; fallback={_safe_error(fallback_exc)}"
            ) from fallback_exc


def run_research_heartbeat(settings: Settings, *, now: datetime | None = None) -> dict[str, Any]:
    """Run daily research without OpenClaw, agent memory, or tool schemas."""

    database = SabiDatabase(settings.v2_db)
    database.initialize()
    jobs = JobService(database)
    jobs.register(
        "daily-picks",
        description="Direct compact daily fixture research and recommendation report.",
        expected_interval_seconds=86400,
    )
    jobs.start("daily-picks")
    try:
        day, events, failures = collect_fixtures(settings, now=now)
        # The daily collector intentionally keeps the model packet bounded. Enrich the
        # persistent coverage inventory from the same cached SportyBet responses so the
        # complete returned action-book slate is retained without waking another model
        # or spending a second Parse request.
        action_price = ActionPriceEnricher(settings, database).refresh(
            now=now,
            scan_date=day,
        )
        failures.extend(action_price.source_failures)
        sharded = ShardedDailyResearch(settings, database).run(day=day, events=events, source_failures=failures)
        recommendations = sharded["recommendations"]
        all_recommendations = sharded["all_recommendations"]
        model = sharded["model"]
        usage = sharded["usage"]
        failures = sharded["failures"]
        generated_at = datetime.now(timezone.utc)
        # The slice audit rows and the consolidated daily log share one stable
        # run id so the coverage map can be opened by the same identifier.
        run_id = str(sharded.get("run_id") or generated_at.isoformat())
        # The current run plus six prior daily runs form the seven-day window for
        # the weekly long-shot strategy. The daily chain itself only sees `current`.
        recent_scans = DailyResearchLog(database).list(limit=6)
        chain_store = StrategyChainStore(database)
        legacy_chain_reconciliation = chain_store.reconcile_legacy_pending()
        chain_state = chain_store.ensure()
        strategy_plans = StrategyPlanner().build(
            recommendations,
            bankroll=BankrollLedger(database).current_balance(),
            source_run_id=run_id,
            generated_at=generated_at,
            recent_scans=recent_scans,
            chain_state=chain_state,
            scan_date=day,
        )
        recorded_picks = _record_strategy_picks(database, strategy_plans, model=model, source_run_id=run_id)
        recorded_tickets = StrategyTicketService(database).materialize(
            strategy_plans,
            model=model,
            source_run_id=run_id,
            chain_date=day,
        )
        strategy_learning = StrategyLearningService(database).summaries(owner="sabi_boy")
        report: dict[str, Any] = {
            "ok": True,
            "generated_at": run_id,
            "date": day,
            "model": model,
            "events_considered": len(events),
            "source_failures": failures,
            "recommendations": recommendations,
            "all_recommendations": all_recommendations,
            "coverage": sharded["coverage"],
            "slices": sharded["slice_rows"],
            "strategy_plans": strategy_plans,
            "recorded_picks": recorded_picks,
            "recorded_tickets": recorded_tickets,
            "strategy_learning": strategy_learning,
            "chain_legacy_reconciliation": legacy_chain_reconciliation,
            "notes": _notes(sharded.get("notes") or []),
            "usage": usage,
            "action_price": action_price.as_dict(),
        }
        push = WebPushService(database, settings).send(_push_payload(day, recommendations, failures))
        report["push"] = {
            "enabled": push.enabled,
            "attempted": push.attempted,
            "delivered": push.delivered,
            "expired": push.expired,
            "failed": push.failed,
        }
        report["run_id"] = run_id
        StrategyPlanStore(database).save_many(strategy_plans)
        DailyResearchLog(database).save(report)
        report_path = settings.data_dir / "reports" / "daily-picks-latest.json"
        _write_report(report_path, report)
        jobs.success("daily-picks")
        return report
    except Exception as exc:
        error = _safe_error(exc)
        jobs.failure("daily-picks", error)
        # A failed scheduled run must be visible even when no report was written.
        # Delivery is best-effort so a notification outage never masks the real
        # research failure or causes a retry loop.
        try:
            WebPushService(database, settings).send(
                {
                    "title": "Sabi Boy research issue",
                    "body": "Daily research did not complete. The system will retry automatically.",
                    "tag": "sabi-boy-daily-picks-error",
                    "url": "/system",
                    "renotify": True,
                    "error": error[:500],
                }
            )
        except Exception:
            pass
        raise


def _record_strategy_picks(
    database: SabiDatabase,
    plans: list[dict],
    *,
    model: str,
    source_run_id: str,
) -> list[dict]:
    """Promote only the precision plan's top candidate into Sabi Boy's record.

    Chain and long-shot plans are materialized separately as tickets so their combined
    stake and leg lineage cannot be mistaken for unrelated bankroll positions.
    """

    precision = next((plan for plan in plans if plan.get("strategy_code") == StrategyPlanner.PRECISION_CODE), None)
    if not precision or precision.get("status") != "ready" or not precision.get("candidates"):
        return []
    candidate = precision["candidates"][0]
    try:
        return [
            PickRecordService(database).record(
                {
                    "sport": candidate.get("sport"),
                    "competition": candidate.get("competition"),
                    "event": candidate.get("event"),
                    "starts_at": candidate.get("starts_at"),
                    "market": candidate.get("market") or "Match winner",
                    "pick": candidate.get("pick"),
                    "decimal_odds": candidate.get("decimal_odds"),
                    "confidence_pct": candidate.get("confidence_pct"),
                    "rationale": candidate.get("reason"),
                    "strategy": precision.get("name"),
                    "strategy_code": precision.get("strategy_code"),
                    "stake": precision.get("suggested_stake"),
                    "source_name": candidate.get("source"),
                    "source_event_id": candidate.get("source_event_id"),
                    "bookmaker": _bookmaker_for_source(candidate.get("source")),
                    "source_run_id": source_run_id,
                    "model_generation": model,
                    "owner": "sabi_boy",
                    "record_kind": "pick",
                    "selected": True,
                }
            )
        ]
    except (KeyError, TypeError, ValueError, InvalidOperation) as exc:
        # A malformed model row must never make the entire daily scan disappear. The
        # report still carries the strategy plan and the reason for the skipped record.
        return [{"skipped": True, "reason": _safe_error(exc)}]


def _bookmaker_for_source(source: object) -> str | None:
    text = str(source or "").casefold()
    if "sportybet" in text:
        return "sportybet"
    if "bet9ja" in text:
        return "bet9ja"
    return None


def _parse_model_result(response: dict[str, Any]) -> dict[str, Any]:
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RuntimeError("Research model returned no choices.")
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, list):
        content = "".join(str(item.get("text") or "") for item in content if isinstance(item, dict))
    text = str(content or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE | re.DOTALL).strip()
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Research model returned invalid JSON.") from exc
    if not isinstance(value, dict):
        raise RuntimeError("Research model returned a non-object JSON result.")
    return value


def _validated_recommendations(result: dict[str, Any], events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_name = {_norm(str(event.get("event") or "")): event for event in events}
    raw = result.get("recommendations")
    if not isinstance(raw, list):
        return []
    valid: list[dict[str, Any]] = []
    for item in raw[:12]:
        if not isinstance(item, dict):
            continue
        event_name = str(item.get("event") or "").strip()
        source_event = by_name.get(_norm(event_name))
        if source_event is None or not _allowed_odds(item.get("decimal_odds"), source_event.get("odds")):
            continue
        try:
            confidence = float(item.get("confidence_pct"))
            odds = float(item.get("decimal_odds"))
        except (TypeError, ValueError):
            continue
        if not 0 <= confidence <= 100 or odds <= 1:
            continue
        valid.append(
            {
                "sport": str(item.get("sport") or source_event.get("sport") or "").strip(),
                "event": event_name,
                "market": str(item.get("market") or "").strip(),
                "pick": str(item.get("pick") or "").strip(),
                "decimal_odds": round(odds, 3),
                "confidence_pct": round(confidence, 1),
                "reason": str(item.get("reason") or "").strip()[:500],
                "source": source_event.get("source"),
                "competition": source_event.get("competition"),
                "country": source_event.get("country") or "Unresolved",
                "division": source_event.get("division") or "Unresolved",
                "starts_at": source_event.get("starts_at"),
                "source_event_id": source_event.get("event_id"),
            }
        )
    return valid


def _allowed_odds(value: object, supplied: object) -> bool:
    if not isinstance(supplied, list):
        return False
    try:
        candidate = float(value)
    except (TypeError, ValueError):
        return False
    for row in supplied:
        if isinstance(row, dict):
            try:
                if abs(float(row.get("decimal_odds")) - candidate) < 0.001:
                    return True
            except (TypeError, ValueError):
                continue
    return False


def _push_payload(day: str, recommendations: list[dict[str, Any]], failures: list[str]) -> dict[str, Any]:
    if recommendations:
        lines = [
            f"{item['sport']}: {item['event']} · {item['pick']} @ {item['decimal_odds']:.2f} · {item['confidence_pct']:.0f}%"
            for item in recommendations[:3]
        ]
        body = "\n".join(lines)
        if len(recommendations) > 3:
            body += f"\n+{len(recommendations) - 3} more in Picks."
    else:
        body = "No qualifying picks survived the direct source and price checks today."
    if failures:
        body += " Some sources were unavailable; see System for details."
    return {
        "title": f"Sabi Boy picks · {day}",
        "body": body[:1200],
        "tag": "sabi-boy-daily-picks",
        "url": "/picks",
        "renotify": bool(recommendations),
    }


def _write_report(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.chmod(0o600)
    temporary.replace(path)
    path.chmod(0o600)


def _post_chat(base_url: str, api_key: str, body: dict[str, Any]) -> dict[str, Any]:
    url = base_url.rstrip("/") + "/chat/completions"
    request = Request(
        url,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "sabi-boy-direct-research/1",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=90) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read(300).decode("utf-8", errors="replace") if exc.fp else ""
        raise RuntimeError(f"HTTP {exc.code} from direct research model: {detail}") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"Direct research model request failed: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("Direct research model returned a non-object response.")
    return payload


def _first(row: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = row.get(key)
        if isinstance(value, dict):
            value = value.get("displayName") or value.get("name") or value.get("shortName")
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _nested_event_rows(value: object) -> list[dict[str, Any]]:
    if isinstance(value, list):
        rows: list[dict[str, Any]] = []
        for item in value:
            rows.extend(_nested_event_rows(item))
        return rows
    if not isinstance(value, dict):
        return []
    rows = []
    for key in ("events", "event", "fixtures", "games", "matches", "data"):
        if key in value:
            rows.extend(_nested_event_rows(value[key]))
    if any(
        key in value
        for key in (
            "strEvent",
            "eventId",
            "idEvent",
            "match_id",
            "homeTeamName",
            "strHomeTeam",
            "home_team",
            "competitors",
            "name",
        )
    ):
        rows.append(value)
    return rows


def _norm(value: str) -> str:
    return "".join(ch for ch in value.casefold() if ch.isalnum())


def _notes(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip()[:500] for item in value if str(item).strip()][:12]


def _safe_error(exc: Exception) -> str:
    text = re.sub(r"\s+", " ", str(exc or "")).strip()
    text = re.sub(r"(?i)(api[-_]?key|token|authorization|secret|password)(\s*[:=]\s*)[^\s,;]+", r"\1\2[redacted]", text)
    text = re.sub(r"(?i)\bbearer\s+[^\s,;]+", "Bearer [redacted]", text)
    text = re.sub(r"\b(?:pmx|sbma)_[A-Za-z0-9_-]+\b", "[redacted]", text)
    return text[:500]
