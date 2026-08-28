from __future__ import annotations

from datetime import date, datetime, timezone
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
from sabiai.storage import DailyResearchLog, SabiDatabase

from .jobs import JobService


_LEAGUES = {
    "football": ("eng.1", "soccer"),
    "soccer": ("eng.1", "soccer"),
    "basketball": ("nba", "basketball"),
    "baseball": ("mlb", "baseball"),
    "ice_hockey": ("nhl", "hockey"),
    "ice hockey": ("nhl", "hockey"),
}


def _local_date(settings: Settings, now: datetime | None = None) -> str:
    try:
        zone = ZoneInfo(settings.timezone)
    except Exception:
        zone = timezone.utc
    return (now or datetime.now(timezone.utc)).astimezone(zone).date().isoformat()


def _request_key(sport: str, day: str, source: str | None = None) -> str:
    digest = hashlib.sha256(f"daily-fixtures|{sport}|{day}|{source or 'fallback'}".encode()).hexdigest()[:24]
    return f"daily-fixtures:{digest}"


def collect_fixtures(
    settings: Settings,
    *,
    now: datetime | None = None,
    max_events: int = 60,
) -> tuple[str, list[dict[str, Any]], list[str]]:
    """Collect a small, normalized fixture packet using direct source adapters only."""

    database = SabiDatabase(settings.v2_db)
    database.initialize()
    bundle = default_source_bundle(settings)
    service = SourceService(database, bundle.registry)
    day = _local_date(settings, now)
    events: list[dict[str, Any]] = []
    failures: list[str] = []
    seen: set[tuple[str, str]] = set()

    for raw_sport in settings.research_sports:
        sport = str(raw_sport).strip().casefold()
        if not sport:
            continue
        league, espn_sport = _LEAGUES.get(sport, (None, None))
        metadata: dict[str, Any] = {"date": day}
        if league:
            metadata.update({"league": league, "league_slug": league, "espn_sport": espn_sport})
        source_order: tuple[str | None, ...] = (
            ("Parse · SportyBet", None)
            if "Parse · SportyBet" in bundle.fetchers and sport in {"football", "soccer", "basketball", "ice_hockey"}
            else (None,)
        )
        for source_name in source_order:
            request = SourceRequest(
                request_key=_request_key(sport, day, source_name),
                capability="fixtures",
                sport=sport,
                ttl_seconds=900,
                metadata=metadata,
                source_names=(source_name,) if source_name else (),
            )
            try:
                response = service.execute(request, bundle.fetchers, allow_paid=False)
                for event in _normalize_events(response.payload, sport=sport, source=response.source_name):
                    key = (_norm(str(event.get("event") or "")), str(event.get("starts_at") or ""))
                    if not key[0] or key in seen:
                        continue
                    seen.add(key)
                    events.append(event)
                    if len(events) >= max_events:
                        break
            except Exception as exc:
                failures.append(f"{sport}{f' via {source_name}' if source_name else ''}: {_safe_error(exc)}")
            if events and source_name == "Parse · SportyBet":
                break
            if len(events) >= max_events:
                break
        if len(events) >= max_events:
            break

    return day, events[:max_events], failures


def _normalize_events(payload: object, *, sport: str, source: str) -> Iterable[dict[str, Any]]:
    for row in _event_rows(payload):
        name = _first(row, "strEvent", "event", "name", "shortName", "displayName")
        home = _first(row, "strHomeTeam", "homeTeamName", "homeTeam", "home", "home_name")
        away = _first(row, "strAwayTeam", "awayTeamName", "awayTeam", "away", "away_name")
        competitions = row.get("competitions") if isinstance(row.get("competitions"), list) else []
        if (not home or not away) and competitions and isinstance(competitions[0], dict):
            competitors = competitions[0].get("competitors")
            if isinstance(competitors, list):
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
        starts_at = _first(row, "strTimestamp", "date", "startTime", "dateEvent", "starts_at", "kickoffTime")
        league = _first(row, "strLeague", "tournament", "league", "competition", "category")
        event_id = _first(row, "idEvent", "eventId", "id", "uid")
        item: dict[str, Any] = {
            "sport": sport,
            "event": name,
            "home": home,
            "away": away,
            "competition": league,
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
) -> tuple[dict[str, Any], str, dict[str, Any]]:
    if not settings.research_api_key:
        raise RuntimeError(
            "Direct research model key is not configured. Set SABIAI_RESEARCH_API_KEY "
            "or ALIYUN_TOKEN_PLAN_COMPATIBLE_KEY in the private runtime environment."
        )
    packet = {"date": day, "events": events}
    prompt = (
        "You are the compact Sabi Boy daily pick analyst. Use only the supplied fixture packet; "
        "never invent an event, price, injury, result or source. Return JSON only in this shape: "
        '{"recommendations":[{"sport":"...","event":"exact supplied event","market":"...",'
        '"pick":"...","decimal_odds":2.1,"confidence_pct":65,"reason":"..."}],'
        '"notes":["..."]}. Recommend only when the packet includes a usable decimal price; '
        "otherwise return no recommendation and explain the missing price in notes. Use decimal odds "
        "and confidence percentages. Never recommend Stake or 1xBet, never claim a bet was placed, "
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
        "max_tokens": 2200,
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
        fallback_body = {**body, "model": settings.research_fallback_model}
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
        result, model, usage = call_research_model(settings, day=day, events=events)
        recommendations = _validated_recommendations(result, events)
        report: dict[str, Any] = {
            "ok": True,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "date": day,
            "model": model,
            "events_considered": len(events),
            "source_failures": failures,
            "recommendations": recommendations,
            "notes": _notes(result),
            "usage": usage,
        }
        push = WebPushService(database, settings).send(_push_payload(day, recommendations, failures))
        report["push"] = {
            "enabled": push.enabled,
            "attempted": push.attempted,
            "delivered": push.delivered,
            "expired": push.expired,
            "failed": push.failed,
        }
        report["run_id"] = report["generated_at"]
        DailyResearchLog(database).save(report)
        report_path = settings.data_dir / "reports" / "daily-picks-latest.json"
        _write_report(report_path, report)
        jobs.success("daily-picks")
        return report
    except Exception as exc:
        jobs.failure("daily-picks", _safe_error(exc))
        raise


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
    if any(key in value for key in ("strEvent", "eventId", "idEvent", "homeTeamName", "strHomeTeam", "name")):
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
