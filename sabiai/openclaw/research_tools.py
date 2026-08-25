from __future__ import annotations

from sabiai.research import Evidence, EvidenceStore, ResearchCaseService, ResearchTaskPlanner

from .serializers import json_value


class ResearchTools:
    def __init__(self, app):
        self.app = app
        self.case_service = ResearchCaseService(app.sports, app.research_planner)
        self.task_planner = ResearchTaskPlanner()

    def handlers(self) -> dict:
        return {
            "research.plan": self.plan,
            "research.evidence.save": self.evidence_save,
            "research.evidence.list": self.evidence_list,
            "research.case.assess": self.case_assess,
            "research.case.next": self.case_next,
        }

    def plan(self, args: dict) -> dict:
        plan = self.app.research_planner.plan(
            str(args.get("sport", "")),
            market_text=args.get("market"),
            home=args.get("home"),
            away=args.get("away"),
        )
        return {
            "sport": plan.sport.name,
            "sport_slug": plan.sport.slug,
            "market": plan.market_text,
            "checklist": list(plan.checklist),
            "market_focus": list(plan.market_focus),
            "needs_source_discovery": plan.needs_source_discovery,
        }

    def evidence_save(self, args: dict) -> dict:
        store = EvidenceStore(self.app._db(initialize=True))
        evidence = Evidence(
            evidence_type=str(args["evidence_type"]),
            summary=str(args["summary"]),
            event_id=args.get("event_id"),
            sport_id=args.get("sport_id"),
            subject=args.get("subject"),
            source_name=args.get("source_name"),
            source_url=args.get("source_url"),
            observed_at=args.get("observed_at"),
            freshness_seconds=int(args["freshness_seconds"])
            if args.get("freshness_seconds") is not None
            else None,
            reliability=args.get("reliability"),
            raw=args.get("raw"),
            id=args.get("id"),
        )
        return {"id": store.save(evidence)}

    def evidence_list(self, args: dict) -> dict:
        event_id = str(args["event_id"])
        store = EvidenceStore(self.app._db(initialize=True))
        return {
            "event_id": event_id,
            "evidence": store.for_event(
                event_id, evidence_type=args.get("evidence_type")
            ),
        }

    def case_assess(self, args: dict) -> dict:
        evidence = self._evidence(args)
        assessment = self.case_service.assess(
            sport=str(args.get("sport", "")),
            event=str(args.get("event", "")),
            market=args.get("market"),
            home=args.get("home"),
            away=args.get("away"),
            evidence=evidence,
        )
        data = json_value(assessment)
        data["skeptic_required"] = assessment.skeptic_required
        return data

    def case_next(self, args: dict) -> dict:
        evidence = self._evidence(args)
        assessment = self.case_service.assess(
            sport=str(args.get("sport", "")),
            event=str(args.get("event", "")),
            market=args.get("market"),
            home=args.get("home"),
            away=args.get("away"),
            evidence=evidence,
        )
        tasks = self.task_planner.plan(assessment)
        return {
            "assessment": json_value(assessment),
            "tasks": [json_value(task) for task in tasks],
        }

    def _evidence(self, args: dict) -> list[dict]:
        supplied = args.get("evidence")
        if supplied is not None:
            if not isinstance(supplied, list):
                raise ValueError("evidence must be a list of evidence objects.")
            return [dict(item) for item in supplied]
        event_id = args.get("event_id")
        if event_id:
            return EvidenceStore(self.app._db(initialize=True)).for_event(str(event_id))
        return []
