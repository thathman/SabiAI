from __future__ import annotations

from sabiai.research import (
    Evidence,
    EvidencePacketService,
    EvidenceStore,
    ResearchCaseService,
    ResearchCaseStore,
    ResearchSynthesizer,
    ResearchTaskPlanner,
    SkepticReviewPlanner,
)
from sabiai.storage import DailyResearchLog, ResearchSliceStore

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
            "research.case.create": self.case_create,
            "research.case.get": self.case_get,
            "research.case.list": self.case_list,
            "research.case.update": self.case_update,
            "research.case.attach": self.case_attach,
            "research.case.assess": self.case_assess,
            "research.case.next": self.case_next,
            "research.case.summary": self.case_summary,
            "research.review.plan": self.review_plan,
            "research.scan.latest": self.scan_latest,
            "research.scan.history": self.scan_history,
            "research.scan.context": self.scan_context,
            "research.coverage": self.coverage,
            "research.cache.lookup": self.cache_lookup,
        }

    def _case_store(self) -> ResearchCaseStore:
        return ResearchCaseStore(self.app._db(initialize=True))

    @staticmethod
    def _notes(value) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            note = value.strip()
            return [note] if note else []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        raise ValueError("Research case notes must be text or a list of text notes.")

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
        evidence_id = store.save(evidence)
        case_id = str(args.get("case_id") or "").strip()
        case = None
        if case_id:
            case = self._case_store().attach_evidence(case_id, [evidence_id])
        return {"id": evidence_id, "case": json_value(case) if case else None}

    def evidence_ingest(self, args: dict) -> dict:
        items = args.get("items")
        if not isinstance(items, list):
            raise ValueError("research.evidence.ingest needs an items list.")
        case_id = str(args.get("case_id") or "").strip() or None
        context = self._case_context(args, allow_missing=True)
        # Evidence attached to a durable case must itself be durable.
        persist = bool(args.get("persist", False) or case_id)
        store = EvidenceStore(self.app._db(initialize=True)) if persist else None
        result = EvidencePacketService(store).ingest(
            items,
            event_id=args.get("event_id") or (context or {}).get("event_id"),
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
            case_scoped=bool(case_id),
        )
        evidence_rows = [item.as_dict() for item in result.items]
        case = None
        if case_id and result.persisted_ids:
            case = self._case_store().attach_evidence(case_id, list(result.persisted_ids))
            evidence_rows = self._case_store().evidence(case_id)
        response = {
            "usable": result.usable,
            "items": evidence_rows,
            "rejected": list(result.rejected),
            "persisted_ids": list(result.persisted_ids),
            "persisted": persist,
            "case": json_value(case) if case else None,
        }
        if context is not None:
            assessment = self.case_service.assess(
                sport=context["sport"],
                event=context["event"],
                market=context.get("market"),
                home=context.get("home"),
                away=context.get("away"),
                evidence=evidence_rows,
            )
            summary = self.synthesizer.summarize(assessment, evidence_rows)
            response["assessment"] = json_value(assessment)
            response["summary"] = {**json_value(summary), "plain_text": summary.plain_text()}
            if case_id:
                response["case"] = json_value(
                    self._case_store().update(case_id, assessment=json_value(assessment))
                )
        return response

    def evidence_list(self, args: dict) -> dict:
        case_id = str(args.get("case_id") or "").strip()
        if case_id:
            return {"case_id": case_id, "evidence": self._case_store().evidence(case_id)}
        event_id = str(args["event_id"])
        store = EvidenceStore(self.app._db(initialize=True))
        return {
            "event_id": event_id,
            "evidence": store.for_event(
                event_id, evidence_type=args.get("evidence_type")
            ),
        }

    def case_create(self, args: dict) -> dict:
        case = self._case_store().create(
            sport=str(args.get("sport") or ""),
            event=str(args.get("event") or ""),
            market=args.get("market"),
            home=args.get("home"),
            away=args.get("away"),
            event_id=args.get("event_id"),
            title=args.get("title"),
            objective=args.get("objective"),
            notes=self._notes(args.get("notes")),
            case_id=args.get("case_id"),
        )
        return json_value(case)

    def case_get(self, args: dict) -> dict:
        case_id = str(args.get("case_id") or "").strip()
        if not case_id:
            raise ValueError("research.case.get needs case_id.")
        case = self._case_store().get(case_id)
        return {
            "found": case is not None,
            "case": json_value(case) if case else None,
            "evidence": self._case_store().evidence(case_id) if case else [],
        }

    def case_list(self, args: dict) -> dict:
        cases = self._case_store().list(
            status=args.get("status"),
            limit=int(args.get("limit", 50)),
        )
        return {"cases": [json_value(case) for case in cases]}

    def case_update(self, args: dict) -> dict:
        case_id = str(args.get("case_id") or "").strip()
        if not case_id:
            raise ValueError("research.case.update needs case_id.")
        case = self._case_store().update(
            case_id,
            status=args.get("status"),
            title=args.get("title"),
            objective=args.get("objective"),
            notes=self._notes(args.get("notes")) if "notes" in args else None,
            append_note=args.get("append_note"),
        )
        return json_value(case)

    def case_attach(self, args: dict) -> dict:
        case_id = str(args.get("case_id") or "").strip()
        evidence_ids = args.get("evidence_ids")
        if not case_id or not isinstance(evidence_ids, list):
            raise ValueError("research.case.attach needs case_id and evidence_ids list.")
        return json_value(self._case_store().attach_evidence(case_id, evidence_ids))

    def case_assess(self, args: dict) -> dict:
        assessment, _, case_id = self._assessment(args)
        data = json_value(assessment)
        data["skeptic_required"] = assessment.skeptic_required
        if case_id:
            data["case"] = json_value(
                self._case_store().update(case_id, assessment=json_value(assessment))
            )
        return data

    def case_next(self, args: dict) -> dict:
        assessment, _, case_id = self._assessment(args)
        tasks = self.task_planner.plan(assessment)
        if case_id:
            self._case_store().update(case_id, assessment=json_value(assessment))
        return {
            "case_id": case_id,
            "assessment": json_value(assessment),
            "tasks": [json_value(task) for task in tasks],
        }

    def case_summary(self, args: dict) -> dict:
        assessment, evidence, case_id = self._assessment(args)
        summary = self.synthesizer.summarize(
            assessment,
            evidence,
            max_points=int(args.get("max_points", 10)),
        )
        if case_id:
            self._case_store().update(case_id, assessment=json_value(assessment))
        data = json_value(summary)
        data["plain_text"] = summary.plain_text()
        data["case_id"] = case_id
        return data

    def review_plan(self, args: dict) -> dict:
        assessment, _, case_id = self._assessment(args)
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
        data = json_value(plan)
        data["case_id"] = case_id
        return data

    def scan_latest(self, args: dict) -> dict:
        return {"scan": DailyResearchLog(self.app._db(initialize=True)).latest()}

    def scan_history(self, args: dict) -> dict:
        return {
            "scans": DailyResearchLog(self.app._db(initialize=True)).list(
                limit=int(args.get("limit", 20))
            )
        }

    def scan_context(self, args: dict) -> dict:
        return DailyResearchLog(self.app._db(initialize=True)).context(
            limit=int(args.get("limit", 5))
        )

    def coverage(self, args: dict) -> dict:
        database = self.app._db(initialize=True)
        return ResearchSliceStore(database).coverage(args.get("run_id"))

    def cache_lookup(self, args: dict) -> dict:
        event = str(args.get("event") or "").strip()
        if not event:
            raise ValueError("research.cache.lookup needs event.")
        database = self.app._db(initialize=True)
        result = ResearchSliceStore(database).find_event(
            event,
            scan_date=args.get("scan_date"),
            max_age_seconds=int(args.get("max_age_seconds", 86400)),
        )
        return result or {"cache_hit": False, "event": event, "recommendations": []}

    def _assessment(self, args: dict):
        context = self._case_context(args)
        evidence = self._evidence(args)
        assessment = self.case_service.assess(
            sport=context["sport"],
            event=context["event"],
            market=context.get("market"),
            home=context.get("home"),
            away=context.get("away"),
            evidence=evidence,
        )
        return assessment, evidence, context.get("case_id")

    def _case_context(self, args: dict, *, allow_missing: bool = False) -> dict | None:
        case_id = str(args.get("case_id") or "").strip()
        if case_id:
            case = self._case_store().get(case_id)
            if case is None:
                raise ValueError(f"Unknown persistent research case: {case_id}")
            return {
                "case_id": case.id,
                "sport": case.sport,
                "event": case.event,
                "market": case.market,
                "home": case.home,
                "away": case.away,
                "event_id": case.event_id,
            }
        sport = str(args.get("sport") or "").strip()
        event = str(args.get("event") or "").strip()
        if not sport or not event:
            if allow_missing:
                return None
            raise ValueError("Research case needs sport/event or a persistent case_id.")
        return {
            "case_id": None,
            "sport": sport,
            "event": event,
            "market": args.get("market"),
            "home": args.get("home"),
            "away": args.get("away"),
            "event_id": args.get("event_id"),
        }

    def _evidence(self, args: dict) -> list[dict]:
        supplied = args.get("evidence")
        if supplied is not None:
            if not isinstance(supplied, list):
                raise ValueError("evidence must be a list of evidence objects.")
            return [dict(item) for item in supplied]
        case_id = str(args.get("case_id") or "").strip()
        if case_id:
            return self._case_store().evidence(case_id)
        event_id = args.get("event_id")
        if event_id:
            return EvidenceStore(self.app._db(initialize=True)).for_event(str(event_id))
        return []
