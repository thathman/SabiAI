from __future__ import annotations

from dataclasses import asdict
from typing import Any

from sabiai.odds import assess_value
from sabiai.research import (
    CandidateEvidenceBuilder,
    EngineCompletenessService,
    EngineDecisionStore,
    EngineGapPlanner,
)
from sabiai.sports import sport_engine_profile

from .serializers import json_value


class EngineTools:
    """OpenClaw's deterministic V2.5 engine-control surface.

    These tools expose inspection and bounded recovery actions. They do not call a model,
    place a wager, or silently enable metered sources.
    """

    def __init__(self, app):
        self.app = app

    def handlers(self) -> dict[str, Any]:
        return {
            "engine.completeness": self.completeness,
            "engine.sport_profile": self.sport_profile,
            "engine.next_actions": self.next_actions,
            "engine.price.assess": self.price_assess,
            "engine.evidence.build": self.evidence_build,
            "engine.calibration": self.calibration,
        }

    def completeness(self, args: dict) -> dict:
        return EngineCompletenessService(self.app.settings, self.app._db(initialize=True)).inspect()

    def sport_profile(self, args: dict) -> dict:
        value = str(args.get("sport") or "").strip()
        if not value:
            raise ValueError("engine.sport_profile needs sport.")
        profile = sport_engine_profile(value)
        return json_value(asdict(profile)) | {"all_market_families": list(profile.all_market_families)}

    def next_actions(self, args: dict) -> dict:
        planner = EngineGapPlanner(self.app.settings)
        events = args.get("events")
        if isinstance(events, list):
            return planner.plan_many(events)
        event = args.get("event") if isinstance(args.get("event"), dict) else dict(args)
        return planner.plan(event)

    def price_assess(self, args: dict) -> dict:
        probability = args.get("estimated_probability_pct")
        if probability is None:
            probability = args.get("confidence_pct")
        odds = args.get("action_decimal_odds", args.get("decimal_odds", args.get("odds")))
        if probability is None or odds is None:
            raise ValueError("engine.price.assess needs estimated_probability_pct and decimal_odds.")
        consensus = args.get("consensus_probability_pct")
        assessment = assess_value(float(probability), float(odds), consensus_probability_pct=(float(consensus) if consensus is not None else None))
        confidence = float(args.get("confidence_pct", probability))
        minimum_confidence = float(args.get("minimum_confidence_pct", 55.0))
        minimum_edge = float(args.get("minimum_edge_pct", 1.0))
        minimum_ev = float(args.get("minimum_expected_value_pct", 1.0))
        edge = float(assessment.estimated_probability_pct - assessment.raw_implied_probability_pct)
        ev = float(assessment.expected_value_pct)
        if confidence >= minimum_confidence and edge >= minimum_edge and ev >= minimum_ev:
            state = "BET"
        elif confidence >= minimum_confidence and (edge >= minimum_edge or ev < minimum_ev):
            state = "BET IF PRICE"
        elif confidence >= max(0.0, minimum_confidence - 5.0) and ev >= -3.0:
            state = "WATCH"
        else:
            state = "PASS"
        return {
            **assessment.as_dict(),
            "value_edge_pct": round(edge, 2),
            "decision_state": state,
            "value_qualified": state == "BET",
            "thresholds": {
                "minimum_confidence_pct": minimum_confidence,
                "minimum_edge_pct": minimum_edge,
                "minimum_expected_value_pct": minimum_ev,
            },
        }

    def evidence_build(self, args: dict) -> dict:
        if isinstance(args.get("event"), dict):
            event = dict(args["event"])
        elif args.get("event"):
            event = {"event": args["event"]}
        else:
            event = {
                key: value for key, value in args.items()
                if key not in {"event", "sport", "home", "away", "competition", "starts_at", "event_id", "coverage_event_id"}
            }
        for key in ("sport", "home", "away", "competition", "starts_at", "event_id", "coverage_event_id"):
            if key in args and key not in event:
                event[key] = args[key]
        if not str(event.get("sport") or "").strip() or not str(event.get("event") or event.get("event_name") or "").strip():
            raise ValueError("engine.evidence.build needs sport and event.")
        event["event"] = event.get("event") or event.get("event_name")
        return CandidateEvidenceBuilder(self.app.settings, self.app._db(initialize=True)).build(event)

    def calibration(self, args: dict) -> dict:
        return EngineDecisionStore(self.app._db(initialize=True)).calibration(limit=int(args.get("limit", 500)))


__all__ = ["EngineTools"]
