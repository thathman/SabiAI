from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import json
import math
from pathlib import Path
from typing import Any, Mapping

from sabiai.odds import ConsensusPricingEngine, SettlementRuleLibrary, assess_value
from sabiai.sports import engine_sport_profiles, sport_engine_profile
from sabiai.storage import CoverageStore, SabiDatabase

from .context import CandidateEvidenceBuilder
from .prefilter import ACTION_BOOKS, canonical_action_book


class EngineGapPlanner:
    """Turn missing engine inputs into a deterministic, ordered recovery plan."""

    def __init__(self, settings: Any | None = None):
        self.settings = settings

    def plan(self, event: Mapping[str, Any]) -> dict[str, Any]:
        row = dict(event or {})
        profile = sport_engine_profile(row.get("sport"))
        actions: list[dict[str, Any]] = []

        if not (row.get("coverage_event_id") or row.get("event_id") or row.get("canonical_event_id")):
            actions.append(self._action(
                "event_not_canonical", 10, "free structured discovery", "sports.event_search",
                "The event has no canonical coverage identity.",
            ))

        has_inventory = bool(row.get("market_inventory") or row.get("market_families") or row.get("odds"))
        if not has_inventory:
            actions.append(self._action(
                "missing_market_inventory", 20, "public market sensor", "research.discovery.refresh",
                "No market catalogue or offers are available for this event.",
            ))

        offers = row.get("odds") if isinstance(row.get("odds"), list) else []
        action_books = {
            canonical_action_book(offer.get("bookmaker") or offer.get("source"))
            for offer in offers if isinstance(offer, dict)
        }
        action_books.discard(None)
        if not action_books:
            actions.append(self._action(
                "missing_action_book_price", 30, "target-book verification", "research.action_price.gaps",
                "A fresh SportyBet or Bet9ja price is required before automatic promotion.",
            ))

        packet = row.get("evidence_packet") if isinstance(row.get("evidence_packet"), dict) else None
        if packet is None or packet.get("ready_for_decision") is not True:
            missing = packet.get("missing_topics") if packet else []
            reason = "Evidence is incomplete."
            if missing:
                reason += " Missing: " + ", ".join(str(item) for item in missing[:5]) + "."
            actions.extend([
                self._action("evidence_incomplete", 40, "automatic free-first evidence build", "engine.evidence.build", reason),
                self._action("research_scout", 50, "Research Scout", "research.case.create", "Close the listed evidence gaps with a bounded research case."),
                self._action("browser_evidence", 60, "OpenClaw Browser", "research.case.attach", "Use a current official/public page when structured sources cannot close the gap."),
                self._action("search_evidence", 70, "OpenClaw Search", "research.case.attach", "Search only after structured and browser evidence paths are exhausted."),
            ])

        if profile.settlement_concerns and row.get("settlement_verified") is not True:
            actions.append(self._action(
                "settlement_uncertain", 80, "target-book rules verification", "market.settlement.profile",
                "The sport/market has rule-sensitive settlement concerns that are not verified for this event.",
            ))

        exhausted = bool(row.get("free_sources_exhausted"))
        metered_enabled = bool(row.get("allow_metered") or getattr(self.settings, "coverage_metered_markets_enabled", False))
        if exhausted and metered_enabled:
            actions.append(self._action(
                "metered_sensor_optional", 90, "explicitly enabled metered sensor", "research.discovery.refresh",
                "Free sources are exhausted; a metered sensor is available only because it was explicitly enabled.",
            ))

        actions.sort(key=lambda item: (int(item["priority"]), item["code"]))
        return {
            "event": row.get("event") or row.get("event_name"),
            "sport": row.get("sport"),
            "actions": actions,
            "next_action": actions[0] if actions else None,
            "blocked": bool(actions),
            "ready_for_decision": not bool(actions),
            "note": "Degradation is actionable: complete the next listed step before promotion." if actions else "All supplied engine inputs are present.",
        }

    def plan_many(self, events: list[Mapping[str, Any]]) -> dict[str, Any]:
        rows = [self.plan(event) for event in events if isinstance(event, Mapping)]
        return {"count": len(rows), "plans": rows}

    @staticmethod
    def _action(code: str, priority: int, owner: str, tool: str, reason: str) -> dict[str, Any]:
        return {"code": code, "priority": priority, "owner": owner, "tool": tool, "reason": reason}


class EngineCompletenessService:
    """Report architecture completeness separately from today's source coverage."""

    def __init__(self, settings: Any, database: SabiDatabase | str | Path):
        self.settings = settings
        self.database = database if isinstance(database, SabiDatabase) else SabiDatabase(database)

    def inspect(self, *, now: datetime | None = None) -> dict[str, Any]:
        self.database.initialize()
        profiles = engine_sport_profiles()
        with self.database.connect() as conn:
            tables = {str(row[0]) for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        required_tables = {"coverage_events", "coverage_market_catalogue", "coverage_market_offers", "engine_pick_context"}
        table_ok = required_tables.issubset(tables)
        contracts = {
            "sport_profiles": len(profiles),
            "all_sports_first_class": len(profiles) == 31 and all(profile.slug for profile in profiles),
            "market_contracts": all(profile.minimum_market_families for profile in profiles),
            "evidence_contracts": all(profile.evidence_topics for profile in profiles),
            "settlement_contracts": all(
                SettlementRuleLibrary().profile(profile.slug, profile.minimum_market_families[0]).verification_required
                and SettlementRuleLibrary().profile(profile.slug, profile.minimum_market_families[0]).verification_topics
                for profile in profiles
            ),
            "action_book_registry": tuple(ACTION_BOOKS) == ("SportyBet", "Bet9ja"),
            "no_vig_pricing": callable(getattr(ConsensusPricingEngine, "lookup", None)) and callable(assess_value),
            "exact_offer_validator": callable(_load_validator()),
            "evidence_builder": callable(getattr(CandidateEvidenceBuilder, "build", None)),
            "coverage_storage": table_ok,
            "decision_context_storage": "engine_pick_context" in tables,
            "free_first_sources": True,
            "scheduled_research_contract": (Path(self.settings.repo_root) / "scripts" / "sabi_v2_research_heartbeat.py").exists(),
        }
        missing = [name for name, value in contracts.items() if value is False]
        funnel = CoverageStore(self.database).funnel()
        current = CoverageStore(self.database).current_counts(now=now, horizon_hours=int(getattr(self.settings, "discovery_horizon_hours", 72)))
        live = {
            "sports_discovered": len({str(row.get("sport") or "unknown") for row in CoverageStore(self.database).radar(now=now, horizon_hours=int(getattr(self.settings, "discovery_horizon_hours", 72)), limit=5000)}),
            "events_discovered": int(current.get("events") or 0),
            "sports_freshly_priced": 0,
            "fresh_prices": int(current.get("priced_events") or 0),
            "market_catalogue": int(current.get("market_catalogue") or 0),
            "market_offers": int(current.get("market_offers") or 0),
            "prefiltered": int(funnel.get("prefiltered") or 0),
            "researched": int(funnel.get("researched") or 0),
            "selected": int(funnel.get("selected") or 0),
            "last_run_id": funnel.get("run_id"),
        }
        live["sports_freshly_priced"] = self._priced_sports(now=now)
        engine_complete = not missing
        source_degraded = live["events_discovered"] == 0 or live["fresh_prices"] < live["events_discovered"]
        return {
            "engine_code_complete": engine_complete,
            "engine_complete": engine_complete,
            "label": (
                "ENGINE COMPLETE — source coverage DEGRADED"
                if engine_complete and source_degraded
                else "ENGINE COMPLETE — source coverage ACTIVE"
                if engine_complete
                else "ENGINE INCOMPLETE"
            ),
            "contracts": contracts,
            "missing_contracts": missing,
            "live_coverage": live,
            "checked_at": (now or datetime.now(timezone.utc)).isoformat(),
        }

    def _priced_sports(self, *, now: datetime | None) -> int:
        rows = CoverageStore(self.database).radar(
            now=now,
            horizon_hours=int(getattr(self.settings, "discovery_horizon_hours", 72)),
            limit=5000,
            priced_only=True,
        )
        return len({str(row.get("sport") or "unknown") for row in rows})


def _load_validator():
    from .model_contract import validate_engine_recommendations

    return validate_engine_recommendations


class EngineDecisionStore:
    """Persist exact V2.5 decision context and produce non-prescriptive calibration views."""

    MINIMUM_MATURE_SAMPLE = 8

    def __init__(self, database: SabiDatabase | str | Path):
        self.db = database if isinstance(database, SabiDatabase) else SabiDatabase(database)
        self.db.initialize()

    def save(self, pick_id: str, context: Mapping[str, Any]) -> dict[str, Any]:
        pick_key = str(pick_id or "").strip()
        offer_ref = str(context.get("offer_ref") or "").strip()
        if not pick_key or not offer_ref:
            raise ValueError("Engine decision context needs pick_id and exact offer_ref.")
        values = {
            "pick_id": pick_key,
            "offer_ref": offer_ref,
            "bookmaker": context.get("bookmaker"),
            "observed_at": context.get("observed_at"),
            "estimated_probability_pct": _number(context.get("estimated_probability_pct")),
            "consensus_probability_pct": _number(context.get("consensus_probability_pct"), allow_none=True),
            "fair_odds": _number(context.get("fair_odds"), allow_none=True),
            "expected_value_pct": _number(context.get("expected_value_pct"), allow_none=True),
            "decision_state": context.get("decision_state"),
            "evidence_quality": context.get("evidence_quality"),
            "evidence_ready": 1 if context.get("evidence_ready") is True else 0,
            "evidence_sources_json": json.dumps(context.get("evidence_sources") or [], ensure_ascii=False),
            "missing_evidence_json": json.dumps(context.get("missing_evidence") or context.get("missing_evidence_topics") or [], ensure_ascii=False),
        }
        if not str(values["decision_state"] or "").strip():
            raise ValueError("Engine decision context needs decision_state.")
        with self.db.transaction() as conn:
            exists = conn.execute("SELECT 1 FROM picks_v2 WHERE id=?", (pick_key,)).fetchone()
            if not exists:
                raise ValueError(f"Unknown pick: {pick_key}")
            conn.execute(
                """INSERT INTO engine_pick_context(
                       pick_id,offer_ref,bookmaker,observed_at,estimated_probability_pct,
                       consensus_probability_pct,fair_odds,expected_value_pct,decision_state,
                       evidence_quality,evidence_ready,evidence_sources_json,missing_evidence_json,
                       created_at,updated_at
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)
                   ON CONFLICT(pick_id) DO UPDATE SET
                       offer_ref=excluded.offer_ref,bookmaker=excluded.bookmaker,observed_at=excluded.observed_at,
                       estimated_probability_pct=excluded.estimated_probability_pct,
                       consensus_probability_pct=excluded.consensus_probability_pct,fair_odds=excluded.fair_odds,
                       expected_value_pct=excluded.expected_value_pct,decision_state=excluded.decision_state,
                       evidence_quality=excluded.evidence_quality,evidence_ready=excluded.evidence_ready,
                       evidence_sources_json=excluded.evidence_sources_json,missing_evidence_json=excluded.missing_evidence_json,
                       updated_at=CURRENT_TIMESTAMP""",
                tuple(values[key] for key in (
                    "pick_id", "offer_ref", "bookmaker", "observed_at", "estimated_probability_pct",
                    "consensus_probability_pct", "fair_odds", "expected_value_pct", "decision_state",
                    "evidence_quality", "evidence_ready", "evidence_sources_json", "missing_evidence_json",
                )),
            )
        return self.get(pick_key) or {}

    def get(self, pick_id: str) -> dict[str, Any] | None:
        with self.db.connect() as conn:
            row = conn.execute("SELECT * FROM engine_pick_context WHERE pick_id=?", (str(pick_id),)).fetchone()
        return self._row(row) if row else None

    def list(self, *, limit: int = 100) -> list[dict[str, Any]]:
        with self.db.connect() as conn:
            rows = conn.execute("SELECT * FROM engine_pick_context ORDER BY updated_at DESC, pick_id LIMIT ?", (max(1, min(int(limit), 500)),)).fetchall()
        return [self._row(row) for row in rows]

    def calibration(self, *, limit: int = 500) -> dict[str, Any]:
        with self.db.connect() as conn:
            rows = conn.execute(
                """SELECT c.*,p.outcome,s.name AS sport,m.label AS market
                   FROM engine_pick_context c
                   JOIN picks_v2 p ON p.id=c.pick_id
                   LEFT JOIN events e ON e.id=p.event_id
                   LEFT JOIN sports s ON s.id=e.sport_id
                   LEFT JOIN markets m ON m.id=p.market_id
                   WHERE p.outcome IN ('won','lost')
                   ORDER BY COALESCE(p.settled_at,p.created_at) DESC LIMIT ?""",
                (max(1, min(int(limit), 5000)),),
            ).fetchall()
        records = [dict(row) for row in rows]
        overall = self._aggregate(records)
        return {
            "overall": overall,
            "by_probability_band": self._group(records, lambda row: _probability_band(row.get("estimated_probability_pct"))),
            "by_ev_band": self._group(records, lambda row: _ev_band(row.get("expected_value_pct"))),
            "by_sport": self._group(records, lambda row: str(row.get("sport") or "Unresolved")),
            "by_market": self._group(records, lambda row: str(row.get("market") or "Unresolved")),
            "minimum_mature_sample": self.MINIMUM_MATURE_SAMPLE,
            "note": "Calibration is descriptive. Small samples are immature and never change policy automatically.",
        }

    def _group(self, rows: list[dict[str, Any]], key_fn) -> list[dict[str, Any]]:
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            groups[key_fn(row)].append(row)
        return [{"key": key, **self._aggregate(items)} for key, items in sorted(groups.items())]

    @classmethod
    def _aggregate(cls, rows: list[dict[str, Any]]) -> dict[str, Any]:
        settled = len(rows)
        wins = sum(1 for row in rows if row.get("outcome") == "won")
        losses = sum(1 for row in rows if row.get("outcome") == "lost")
        return {
            "settled": settled,
            "wins": wins,
            "losses": losses,
            "win_percentage": round(wins / settled * 100.0, 1) if settled else None,
            "maturity": "mature" if settled >= cls.MINIMUM_MATURE_SAMPLE else "immature",
        }

    @staticmethod
    def _row(row) -> dict[str, Any]:
        def load(name):
            try:
                value = json.loads(row[name] or "[]")
            except (TypeError, ValueError, json.JSONDecodeError):
                value = []
            return value if isinstance(value, list) else []

        return {
            "pick_id": row["pick_id"],
            "offer_ref": row["offer_ref"],
            "bookmaker": row["bookmaker"],
            "observed_at": row["observed_at"],
            "estimated_probability_pct": row["estimated_probability_pct"],
            "consensus_probability_pct": row["consensus_probability_pct"],
            "fair_odds": row["fair_odds"],
            "expected_value_pct": row["expected_value_pct"],
            "decision_state": row["decision_state"],
            "evidence_quality": row["evidence_quality"],
            "evidence_ready": bool(row["evidence_ready"]),
            "evidence_sources": load("evidence_sources_json"),
            "missing_evidence": load("missing_evidence_json"),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }


def _number(value: Any, *, allow_none: bool = False) -> float | None:
    if value is None or str(value).strip() == "":
        if allow_none:
            return None
        raise ValueError("A required engine number is missing.")
    try:
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("Engine numeric context must be finite.")
        return number
    except (TypeError, ValueError) as exc:
        if allow_none:
            return None
        raise ValueError("Engine numeric context must be a number.") from exc


def _probability_band(value: Any) -> str:
    try:
        number = max(0.0, min(100.0, float(value)))
    except (TypeError, ValueError):
        return "unknown"
    low = int(number // 10) * 10
    return f"{low}-{min(99, low + 9)}"


def _ev_band(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "unknown"
    if number < 0:
        return "negative"
    if number < 5:
        return "0-4.99"
    if number < 10:
        return "5-9.99"
    return "10+"


__all__ = ["EngineCompletenessService", "EngineDecisionStore", "EngineGapPlanner"]
