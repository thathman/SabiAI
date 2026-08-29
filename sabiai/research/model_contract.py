from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
from typing import Any

from sabiai.odds import ConsensusPricingEngine, assess_value, implied_probability, market_group_identity, selection_identity
from sabiai.sports import sport_engine_profile


def _norm(value: object) -> str:
    return "".join(ch for ch in str(value or "").casefold() if ch.isalnum())


def _offer_ref(event: dict[str, Any], offer: dict[str, Any]) -> str:
    pieces = (
        event.get("coverage_event_id") or event.get("event_id") or event.get("event"),
        offer.get("bookmaker"),
        offer.get("market"),
        offer.get("line"),
        offer.get("period"),
        offer.get("participant"),
        offer.get("label"),
        offer.get("decimal_odds"),
        offer.get("observed_at"),
    )
    digest = hashlib.sha256("|".join(str(value or "") for value in pieces).encode()).hexdigest()[:24]
    return f"offer:{digest}"


def _pricing_rows(event: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[tuple, Any]]:
    rows: list[dict[str, Any]] = []
    for raw in event.get("odds") or []:
        if not isinstance(raw, dict):
            continue
        row = {
            "family": raw.get("market") or "other",
            "metric": raw.get("metric"),
            "period": raw.get("period"),
            "participant": raw.get("participant"),
            "side": raw.get("side"),
            "line": raw.get("line"),
            "selection_label": raw.get("label"),
            "decimal_odds": raw.get("decimal_odds"),
            "bookmaker": raw.get("bookmaker") or event.get("action_book") or event.get("source"),
        }
        rows.append(row)
    fair = ConsensusPricingEngine().lookup(rows)
    return rows, fair


def prepare_events_for_model(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return a compact copy with exact action-offer references and deterministic pricing facts."""
    prepared: list[dict[str, Any]] = []
    for source in events:
        event = dict(source)
        profile = sport_engine_profile(event.get("sport"))
        _rows, fair_lookup = _pricing_rows(event)
        offers: list[dict[str, Any]] = []
        for raw in event.get("odds") or []:
            if not isinstance(raw, dict):
                continue
            offer = dict(raw)
            try:
                odds = float(offer.get("decimal_odds"))
            except (TypeError, ValueError):
                continue
            if odds <= 1:
                continue
            offer["offer_ref"] = _offer_ref(event, offer)
            offer["raw_implied_probability_pct"] = round(implied_probability(odds) * 100.0, 2)
            pricing_row = {
                "family": offer.get("market") or "other",
                "metric": offer.get("metric"),
                "period": offer.get("period"),
                "participant": offer.get("participant"),
                "side": offer.get("side"),
                "line": offer.get("line"),
                "selection_label": offer.get("label"),
            }
            fair = fair_lookup.get((market_group_identity(pricing_row), selection_identity(pricing_row)))
            if fair:
                offer["action_book_fair_probability_pct"] = round(fair.fair_probability * 100.0, 2)
                offer["action_book_fair_odds"] = round(fair.fair_decimal_odds, 3)
                offer["action_book_margin_pct"] = round(fair.median_book_margin_pct, 2)
            offers.append(offer)
        event["odds"] = offers
        event["engine_profile"] = {
            "event_shape": profile.event_shape,
            "minimum_market_families": list(profile.minimum_market_families),
            "evidence_topics": list(profile.evidence_topics),
            "settlement_concerns": list(profile.settlement_concerns),
            "needs_discovery": profile.needs_discovery,
        }
        prepared.append(event)
    return prepared


def call_engine_research_model(
    settings,
    *,
    day: str,
    events: list[dict[str, Any]],
    scope: dict[str, str] | None = None,
    max_tokens: int = 2200,
):
    """V2.5 model contract: the model may choose only an exact supplied action offer."""
    from sabiai.system import research_heartbeat as legacy

    if not settings.research_api_key:
        raise RuntimeError(
            "Direct research model key is not configured. Set SABIAI_RESEARCH_API_KEY "
            "or ALIYUN_TOKEN_PLAN_COMPATIBLE_KEY in the private runtime environment."
        )
    prepared = prepare_events_for_model(events)
    packet = {"date": day, "scope": scope or {}, "events": prepared}
    prompt = (
        "You are Sabi Boy's bounded decision analyst. Use only the supplied packet. "
        "Never invent an event, price, market, bookmaker, injury, statistic or source. "
        "Every recommendation MUST echo one exact supplied odds[].offer_ref and MUST use that offer's exact bookmaker, market, label/pick, line, period and decimal_odds. "
        "The action_book_fair_probability_pct field, when present, is a no-vig price baseline from the supplied action-book market; it is not your prediction. "
        "Estimate probability only from supplied research/evidence. If the packet is too thin, return no recommendation. "
        "Return JSON only in this shape: "
        '{"recommendations":[{"sport":"...","event":"exact supplied event","offer_ref":"offer:...",'
        '"bookmaker":"SportyBet or Bet9ja","market":"exact supplied family","pick":"exact supplied label",'
        '"decimal_odds":2.1,"confidence_pct":65,"estimated_probability_pct":67,"reason":"..."}],'
        '"notes":["..."]}. Never recommend Stake or 1xBet, never claim a wager was placed, and never write to a betting ledger.\n\n'
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
        response = legacy._post_chat(settings.research_api_base_url, settings.research_api_key, body)
        model = str(response.get("model") or settings.research_model)
        return legacy._parse_model_result(response), model, response.get("usage") or {}
    except Exception as primary_exc:
        if not (
            settings.research_fallback_model
            and settings.research_fallback_api_key
            and settings.research_fallback_api_base_url
        ):
            raise RuntimeError(f"Primary research model failed: {legacy._safe_error(primary_exc)}") from primary_exc
        fallback_body = {
            **body,
            "model": settings.research_fallback_model,
            "max_tokens": min(int(body.get("max_tokens") or 2200), 1600),
        }
        try:
            response = legacy._post_chat(
                settings.research_fallback_api_base_url,
                settings.research_fallback_api_key,
                fallback_body,
            )
            model = str(response.get("model") or settings.research_fallback_model)
            return legacy._parse_model_result(response), model, response.get("usage") or {}
        except Exception as fallback_exc:
            raise RuntimeError(
                "Primary and fallback research models failed: "
                f"primary={legacy._safe_error(primary_exc)}; fallback={legacy._safe_error(fallback_exc)}"
            ) from fallback_exc


def validate_engine_recommendations(result: dict[str, Any], events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    prepared = prepare_events_for_model(events)
    by_name = {_norm(event.get("event")): event for event in prepared}
    raw = result.get("recommendations")
    if not isinstance(raw, list):
        return []
    valid: list[dict[str, Any]] = []
    for item in raw[:12]:
        if not isinstance(item, dict):
            continue
        event_name = str(item.get("event") or "").strip()
        event = by_name.get(_norm(event_name))
        if event is None:
            continue
        ref = str(item.get("offer_ref") or "").strip()
        if not ref:
            continue
        offer = next((row for row in event.get("odds") or [] if isinstance(row, dict) and row.get("offer_ref") == ref), None)
        if not offer:
            continue
        try:
            returned_odds = float(item.get("decimal_odds"))
            supplied_odds = float(offer.get("decimal_odds"))
            confidence = float(item.get("confidence_pct"))
            estimated = float(item.get("estimated_probability_pct", confidence))
        except (TypeError, ValueError):
            continue
        if abs(returned_odds - supplied_odds) >= 0.001 or not 0 <= confidence <= 100 or not 0 <= estimated <= 100:
            continue
        if _norm(item.get("bookmaker")) != _norm(offer.get("bookmaker")):
            continue
        if _norm(item.get("market")) != _norm(offer.get("market")):
            continue
        if _norm(item.get("pick")) != _norm(offer.get("label")):
            continue
        fair_probability = offer.get("action_book_fair_probability_pct")
        assessment = assess_value(
            estimated,
            supplied_odds,
            consensus_probability_pct=(float(fair_probability) if fair_probability is not None else None),
        )
        row = {
            "sport": str(item.get("sport") or event.get("sport") or "").strip(),
            "event": event_name,
            "offer_ref": ref,
            "bookmaker": str(offer.get("bookmaker") or "").strip(),
            "market": str(offer.get("market") or "").strip(),
            "pick": str(offer.get("label") or "").strip(),
            "line": offer.get("line"),
            "period": offer.get("period"),
            "participant": offer.get("participant"),
            "decimal_odds": round(supplied_odds, 3),
            "confidence_pct": round(confidence, 1),
            "estimated_probability_pct": round(estimated, 2),
            "reason": str(item.get("reason") or "").strip()[:500],
            "source": str(offer.get("bookmaker") or event.get("source") or "").strip(),
            "competition": event.get("competition"),
            "country": event.get("country") or "Unresolved",
            "division": event.get("division") or "Unresolved",
            "starts_at": event.get("starts_at"),
            "source_event_id": event.get("event_id"),
            "observed_at": offer.get("observed_at"),
            **assessment.as_dict(),
        }
        valid.append(row)
    return valid


@contextmanager
def _patched_legacy_contract():
    """Patch only for the duration of one system-owned heartbeat run.

    V2.4 remains import-compatible while the scheduled V2.5 path gets the stricter contract.
    The research service is a single-shot systemd process, so there is no concurrent request
    surface sharing these module globals.
    """
    from sabiai.system import research_heartbeat as legacy

    original_call = legacy.call_research_model
    original_validate = legacy._validated_recommendations
    legacy.call_research_model = call_engine_research_model
    legacy._validated_recommendations = validate_engine_recommendations
    try:
        yield legacy
    finally:
        legacy.call_research_model = original_call
        legacy._validated_recommendations = original_validate


def run_engine_research_heartbeat(settings, *, now=None) -> dict[str, Any]:
    with _patched_legacy_contract() as legacy:
        report = legacy.run_research_heartbeat(settings, now=now)
    report["engine_contract"] = "v2.5-exact-offer"
    return report


__all__ = [
    "call_engine_research_model",
    "prepare_events_for_model",
    "run_engine_research_heartbeat",
    "validate_engine_recommendations",
]
