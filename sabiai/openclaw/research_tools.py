from __future__ import annotations

from sabiai.research import (
    Evidence,
    EvidencePacketService,
    EvidenceStore,
    ResearchCaseService,
    ResearchSynthesizer,
    ResearchTaskPlanner,
    SkepticReviewPlanner,
)

from .serializers import json_value


class ResearchTools:
    def __init__(self, app):
        self.app = app
        self.case_service = ResearchCaseService(app.sports, app.research_planner)
        self.task_planner = ResearchTaskPlanner()
        self.synthesizer = ResearchSynthesizer()
        self.skeptic = SkepticReviewPlanner()

    def handlers(self) -> dict:
        return {
            "research.plan": self.plan,
            "research.evidence.save": self.evidence_save,
            "research.evidence.ingest": self.evidence_ingest,
            "research.evidence.list": self.evidence_list,
            "research.case.assess": self.case_assess,
            "research.case.next": self.case_next,
            "research.case.summary": self.case_summary,
            "research.review.plan": self.review_plan,
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

    def evidence_ingest(self, args: dict) -> dict:
        items = args.get("items")
        if not isinstance(items, list):
            raise ValueError("research.evidence.ingest needs an items list.")
        persist = bool(args.get("persist", False))
        store = EvidenceStore(self.app._db(initialize=True)) if persist else None
        result = EvidencePacketService(store).ingest(
            items,
            event_id=args.get("event_id"),
            sport_id=args.get("sport_id"),
            default_source_name=args.get("source_name"),
            default_source_url=args.get("source_url"),
            default_observed_at=args.get("observed_at"),
            default_reliability=str(args.get("reliability") or "unknown"),
            default_freshness_seconds=(
                int(args["freshness_seconds"])
                if args.get("freshness_seconds") is not None
                else None
            ),
            persist=persist,
        )
        evidence_rows = [item.as_dict() for item in result.items]
        response = {
            "usable": result.usable,
            "items": evidence_rows,
            "rejected": list(result.rejected),
            "persisted_ids": list(result.persisted_ids),
            "persisted": persist,
        }
        if args.get("sport") and args.get("event"):
            assessment = self.case_service.assess(
                sport=str(args.get("sport")),
                event=str(args.get("event")),
                market=args.get("market"),
                home=args.get("home"),
                away=args.get("away"),
                evidence=evidence_rows,
            )
            summary = self.synthesizer.summarize(assessment, evidence_rows)
            response["assessment"] = json_value(assessment)
            response["summary"] = {**json_value(summary), "plain_text": summary.plain_text()}
        return response

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
        assessment, _ = self._assessment(args)
        data = json_value(assessment)
        data["skeptic_required"] = assessment.skeptic_required
        return data

    def case_next(self, args: dict) -> dict:
        assessment, _ = self._assessment(args)
        tasks = self.task_planner.plan(assessment)
        return {
            "assessment": json_value(assessment),
            "tasks": [json_value(task) for task in tasks],
        }

    def case_summary(self, args: dict) -> dict:
        assessment, evidence = self._assessment(args)
        summary = self.synthesizer.summarize(
            assessment,
            evidence,
            max_points=int(args.get("max_points", 10)),
        )
        data = json_value(summary)
        data["plain_text"] = summary.plain_text()
        return data

    def review_plan(self, args: dict) -> dict:
        assessment, _ = self._assessment(args)
        plan = self.skeptic.plan(
            assessment,
            ticket_legs=int(args.get("ticket_legs", 0)),
            stake=args.get("stake"),
            bankroll=args.get("bankroll"),
            bookmaker_conversion=bool(args.get("bookmaker_conversion", False)),
            arbitrage=bool(args.get("arbitrage", False)),
            single_source_case=bool(args.get("single_source_case", False)),
            user_asked_strongest=bool(args.get("user_asked_strongest", False)),
        )
        return json_value(plan)

    def _assessment(self, args: dict):
        evidence = self._evidence(args)
        assessment = self.case_service.assess(
            sport=str(args.get("sport", "")),
            event=str(args.get("event", "")),
            market=args.get("market"),
            home=args.get("home"),
            away=args.get("away"),
            evidence=evidence,
        )
        return assessment, evidence

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
