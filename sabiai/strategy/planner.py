from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_DOWN
import hashlib
from itertools import combinations
from typing import Iterable


class StrategyPlanner:
    """Build deterministic strategy recommendations from a validated scan.

    This layer is deliberately local and bounded: it does not call a model, place an
    external wager, or mutate the pick ledger. It turns fresh recommendations into
    inspectable strategy plans that a later pick/position step can promote.
    """

    DAILY_CHAIN_CODE = "daily_chain_1_30"
    WEEKLY_LONG_SHOT_CODE = "weekly_long_shot_1000"
    PRECISION_CODE = "precision_picks"

    def build(
        self,
        recommendations: Iterable[dict],
        *,
        bankroll: Decimal | int | float | str = Decimal("0"),
        source_run_id: str | None = None,
        generated_at: datetime | None = None,
        recent_scans: Iterable[dict] = (),
        chain_state: dict | None = None,
    ) -> list[dict]:
        stamp = generated_at or datetime.now(timezone.utc)
        stamp_text = stamp.isoformat()
        bankroll_amount = _decimal(bankroll)
        current = _candidates(recommendations)
        historical: list[dict] = []
        for scan in recent_scans:
            if isinstance(scan, dict):
                historical.extend(_candidates(scan.get("recommendations") or []))
        all_candidates = _dedupe(current + historical)

        plans = [
            self._precision_plan(current, bankroll_amount, source_run_id, stamp_text),
            self._daily_chain_plan(current, bankroll_amount, source_run_id, stamp_text, chain_state),
            self._weekly_long_shot_plan(all_candidates, bankroll_amount, source_run_id, stamp_text),
        ]
        return plans

    def _precision_plan(self, candidates, bankroll, source_run_id, stamp):
        eligible = [row for row in candidates if row["confidence_pct"] >= 60]
        selected = max(eligible, key=lambda row: (row["confidence_pct"], -row["decimal_odds"])) if eligible else None
        if selected is None:
            return _plan(
                self.PRECISION_CODE,
                "Precision Picks",
                status="watch",
                target_odds=None,
                combined_odds=None,
                stake=Decimal("0"),
                confidence=None,
                rationale="No fresh candidate reached the 60% confidence floor.",
                candidates=candidates,
                source_run_id=source_run_id,
                generated_at=stamp,
            )
        return _plan(
            self.PRECISION_CODE,
            "Precision Picks",
            status="ready",
            target_odds=None,
            combined_odds=selected["decimal_odds"],
            stake=_stake(bankroll, Decimal("0.02")),
            confidence=selected["confidence_pct"],
            rationale="Highest-confidence fresh candidate after source and price validation.",
            candidates=[selected],
            source_run_id=source_run_id,
            generated_at=stamp,
        )

    def _daily_chain_plan(self, candidates, bankroll, source_run_id, stamp, chain_state=None):
        chain = _chain_context(chain_state, bankroll)
        if chain and chain["status"] == "pending":
            return _plan(
                self.DAILY_CHAIN_CODE,
                "Daily 1.30 Chain",
                status="pending",
                target_odds=chain["target_odds"],
                combined_odds=None,
                stake=_decimal(chain["current_stake"]),
                confidence=None,
                rationale=(
                    f"Day {chain['current_day']}/{chain['target_days']} is awaiting settlement; "
                    "the chain will not open another position."
                ),
                candidates=[],
                source_run_id=source_run_id,
                generated_at=stamp,
                chain=chain,
            )
        if chain and chain["status"] == "completed":
            return _plan(
                self.DAILY_CHAIN_CODE,
                "Daily 1.30 Chain",
                status="completed",
                target_odds=chain["target_odds"],
                combined_odds=None,
                stake=chain["current_stake"],
                confidence=None,
                rationale=f"The {chain['target_days']}-day chain is complete; the next cycle starts at the base stake.",
                candidates=[],
                source_run_id=source_run_id,
                generated_at=stamp,
                chain=chain,
            )
        chosen = _best_combo(candidates, Decimal("1.30"), max_legs=6)
        if not chosen:
            return _plan(
                self.DAILY_CHAIN_CODE,
                "Daily 1.30 Chain",
                status="not_qualified",
                target_odds=Decimal("1.30"),
                combined_odds=None,
                stake=Decimal("0"),
                confidence=None,
                rationale="No fresh, non-duplicated combination reached the 1.30 target.",
                candidates=candidates,
                source_run_id=source_run_id,
                generated_at=stamp,
                chain=chain,
            )
        combined = _combined(chosen)
        stake = _decimal(chain["current_stake"]) if chain else _stake(bankroll, Decimal("0.01"))
        return _plan(
            self.DAILY_CHAIN_CODE,
            "Daily 1.30 Chain",
            status="ready",
            target_odds=Decimal("1.30"),
            combined_odds=combined,
            stake=stake,
            confidence=_average_confidence(chosen),
            rationale=f"{len(chosen)} fresh leg{'s' if len(chosen) != 1 else ''} reach the daily combined target.",
            candidates=chosen,
            source_run_id=source_run_id,
            generated_at=stamp,
            chain=chain,
        )

    def _weekly_long_shot_plan(self, candidates, bankroll, source_run_id, stamp):
        selected: list[dict] = []
        combined = Decimal("1")
        seen_events: set[str] = set()
        for row in sorted(candidates, key=lambda item: (-item["confidence_pct"], item["decimal_odds"])):
            if row["confidence_pct"] < 50 or row["event_key"] in seen_events:
                continue
            selected.append(row)
            seen_events.add(row["event_key"])
            combined *= row["decimal_odds"]
            if combined >= Decimal("1000") or len(selected) >= 35:
                break
        if combined < Decimal("1000"):
            return _plan(
                self.WEEKLY_LONG_SHOT_CODE,
                "Weekly 1000+ Long Shot",
                status="watch",
                target_odds=Decimal("1000"),
                combined_odds=combined if selected else None,
                stake=Decimal("0"),
                confidence=_average_confidence(selected),
                rationale="Broad scan is still gathering enough independent, fresh legs to reach 1,000.",
                candidates=selected,
                source_run_id=source_run_id,
                generated_at=stamp,
            )
        return _plan(
            self.WEEKLY_LONG_SHOT_CODE,
            "Weekly 1000+ Long Shot",
            status="ready",
            target_odds=Decimal("1000"),
            combined_odds=combined,
            stake=_stake(bankroll, Decimal("0.0025")),
            confidence=_average_confidence(selected),
            rationale=f"{len(selected)} independent legs across the recent multi-sport scan window.",
            candidates=selected,
            source_run_id=source_run_id,
            generated_at=stamp,
        )


def _candidates(rows: object) -> list[dict]:
    if not isinstance(rows, list):
        return []
    result: list[dict] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        try:
            odds = _decimal(item.get("decimal_odds"))
            confidence = float(item.get("confidence_pct"))
        except (InvalidOperation, TypeError, ValueError):
            continue
        event = str(item.get("event") or "").strip()
        pick = str(item.get("pick") or item.get("selection") or "").strip()
        if not event or not pick or odds <= 1 or not 0 <= confidence <= 100:
            continue
        event_key = _norm(event)
        result.append(
            {
                "sport": str(item.get("sport") or "").strip(),
                "competition": str(item.get("competition") or "").strip(),
                "event": event,
                "event_key": event_key,
                "market": str(item.get("market") or "").strip(),
                "pick": pick,
                "decimal_odds": odds,
                "confidence_pct": round(confidence, 1),
                "reason": str(item.get("reason") or "").strip()[:500],
                "source": str(item.get("source") or "").strip(),
                "starts_at": item.get("starts_at"),
                "source_event_id": item.get("source_event_id") or item.get("event_id"),
            }
        )
    return result


def _dedupe(rows: Iterable[dict]) -> list[dict]:
    seen: set[tuple[str, str]] = set()
    result: list[dict] = []
    for row in rows:
        key = (row["event_key"], _norm(row["pick"]))
        if key in seen:
            continue
        seen.add(key)
        result.append(row)
    return result


def _best_combo(rows: list[dict], target: Decimal, *, max_legs: int) -> list[dict]:
    rows = _dedupe(rows)
    for size in range(1, min(max_legs, len(rows)) + 1):
        candidates: list[tuple[Decimal, float, list[dict]]] = []
        for combo in combinations(rows, size):
            events = [row["event_key"] for row in combo]
            if len(set(events)) != len(events):
                continue
            combined = _combined(combo)
            if combined >= target:
                candidates.append((combined, _average_confidence(combo), list(combo)))
        if candidates:
            candidates.sort(key=lambda item: (item[0] - target, -item[1]))
            return candidates[0][2]
    return []


def _combined(rows: Iterable[dict]) -> Decimal:
    total = Decimal("1")
    for row in rows:
        total *= row["decimal_odds"]
    return total.quantize(Decimal("0.01"))


def _average_confidence(rows: Iterable[dict]) -> float | None:
    values = [float(row["confidence_pct"]) for row in rows]
    return round(sum(values) / len(values), 1) if values else None


def _stake(bankroll: Decimal, fraction: Decimal) -> Decimal:
    if bankroll <= 0:
        return Decimal("0.00")
    return (bankroll * fraction).quantize(Decimal("0.01"), rounding=ROUND_DOWN)


def _plan(code, name, *, status, target_odds, combined_odds, stake, confidence, rationale, candidates, source_run_id, generated_at, chain=None):
    target = _decimal_text(target_odds)
    combined = _decimal_text(combined_odds)
    digest = hashlib.sha256(f"{code}|{source_run_id or generated_at}".encode()).hexdigest()[:24]
    generated = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
    expires = (generated + timedelta(days=7 if code == StrategyPlanner.WEEKLY_LONG_SHOT_CODE else 1)).isoformat()
    plan = {
        "id": f"strategy_plan_{code}_{digest}",
        "strategy_code": code,
        "name": name,
        "status": status,
        "target_odds": target,
        "combined_odds": combined,
        "suggested_stake": _decimal_text(stake),
        "confidence_pct": confidence,
        "rationale": rationale,
        "candidate_count": len(candidates),
        "candidates": [_json_candidate(row) for row in candidates],
        "source_run_id": source_run_id,
        "generated_at": generated_at,
        "expires_at": expires,
    }
    if chain is not None:
        plan["chain"] = chain
    return plan


def _json_candidate(row: dict) -> dict:
    return {
        key: (_decimal_text(value) if key == "decimal_odds" else value)
        for key, value in row.items()
        if key != "event_key"
    }


def _decimal(value) -> Decimal:
    return Decimal(str(value or "0")).quantize(Decimal("0.01"))


def _decimal_text(value) -> str | None:
    if value is None:
        return None
    return str(_decimal(value))


def _chain_context(state: dict | None, bankroll: Decimal) -> dict | None:
    if not isinstance(state, dict):
        return None
    target_days = int(state.get("target_days") or 30)
    completed_days = max(0, int(state.get("completed_days") or 0))
    current_day = min(completed_days + 1, target_days)
    return {
        "status": str(state.get("status") or "ready"),
        "current_day": current_day,
        "completed_days": completed_days,
        "target_days": target_days,
        "target_odds": _decimal_text(state.get("target_odds") or "1.30"),
        "starting_stake": _decimal_text(state.get("starting_stake") or "1000"),
        "current_stake": _decimal_text(state.get("current_stake") or "0"),
        "active_ticket_id": state.get("active_ticket_id"),
        "last_outcome": state.get("last_outcome"),
        "cycle_count": int(state.get("cycle_count") or 0),
    }


def _norm(value: str) -> str:
    return "".join(ch for ch in value.casefold() if ch.isalnum())
