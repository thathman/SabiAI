from __future__ import annotations

import hashlib

from sabiai.sources import SourceLearningService, SourceRequest, SourceService

from .serializers import json_value


class SourceTools:
    def __init__(self, app):
        self.app = app

    def handlers(self) -> dict:
        return {
            "source.catalog": self.catalog,
            "source.query": self.query,
            "source.discovery.plan": self.discovery_plan,
            "source.discovery.save": self.discovery_save,
            "source.discovery.verify": self.discovery_verify,
            "source.discovery.check": self.discovery_check,
            "source.discovery.list": self.discovery_list,
        }

    def _learning(self) -> SourceLearningService:
        return SourceLearningService(self.app._db(initialize=True))

    def catalog(self, args: dict) -> dict:
        db = self.app._db(initialize=True)
        sources = []
        for source in self.app.source_bundle.registry.all():
            db.upsert_source(source)
            sources.append(
                {
                    "name": source.name,
                    "kind": source.kind.value,
                    "cost": source.cost.value,
                    "priority": source.priority,
                    "sports": sorted(source.sports),
                    "capabilities": sorted(source.capabilities),
                    "has_direct_adapter": source.name in self.app.source_bundle.fetchers,
                    "notes": source.notes,
                }
            )
        learned = self._learning().list(status="verified", limit=int(args.get("learned_limit", 100)))
        return {
            "sources": sources,
            "learned_verified_sources": [json_value(item) for item in learned],
            "note": "Learned sources may require OpenClaw Browser/Search unless a direct Python adapter is explicitly registered.",
        }

    def query(self, args: dict) -> dict:
        capability = str(args.get("capability") or "").strip()
        if not capability:
            raise ValueError("source.query needs capability.")
        sport = str(args.get("sport") or "").strip() or None
        metadata = dict(args.get("metadata") or {})
        source_names = self._source_names(args)
        request_key = str(args.get("request_key") or "").strip()
        if not request_key:
            request_key = self._request_key(capability, sport, metadata, source_names)
        request = SourceRequest(
            request_key=request_key,
            capability=capability,
            sport=sport,
            ttl_seconds=int(args.get("ttl_seconds", 900)),
            metadata=metadata,
            source_names=source_names,
        )
        response = SourceService(
            self.app._db(initialize=True),
            self.app.source_bundle.registry,
        ).execute(
            request,
            self.app.source_bundle.fetchers,
            allow_paid=bool(args.get("allow_paid", False) and self.app.settings.paid_sources_enabled),
            paid_reason=args.get("paid_reason"),
        )
        return {
            "source": response.source_name,
            "cache_hit": response.cache_hit,
            "paid": response.paid,
            "fetched_at": response.fetched_at.isoformat(),
            "failures_before_success": list(response.failures),
            "payload": response.payload,
        }

    def discovery_plan(self, args: dict) -> dict:
        sport = str(args.get("sport") or "").strip()
        if not sport:
            raise ValueError("source.discovery.plan needs sport.")
        capability = str(args.get("capability") or "").strip() or None
        existing = self._learning().best(sport=sport, capability=capability, limit=int(args.get("limit", 20)))
        return {
            "sport": sport,
            "capability": capability,
            "verified_sources": [json_value(item) for item in existing],
            "needs_discovery": not bool(existing),
            "questions": SourceLearningService.discovery_questions(sport, capability),
            "next_step": (
                "Use verified learned sources first. If coverage is still insufficient, use OpenClaw Search/Browser to discover official/public sources and save candidates with source.discovery.save."
            ),
        }

    def discovery_save(self, args: dict) -> dict:
        source = self._learning().discover(
            name=str(args.get("name") or ""),
            url=str(args.get("url") or ""),
            kind=str(args.get("kind") or "official"),
            sports=args.get("sports") or ([args["sport"]] if args.get("sport") else []),
            capabilities=args.get("capabilities") or ([args["capability"]] if args.get("capability") else []),
            reliability=str(args.get("reliability") or "unknown"),
            notes=args.get("notes"),
        )
        return json_value(source)

    def discovery_verify(self, args: dict) -> dict:
        source_id = str(args.get("source_id") or "").strip()
        if not source_id:
            raise ValueError("source.discovery.verify needs source_id.")
        return json_value(
            self._learning().verify(
                source_id,
                status=str(args.get("status") or "verified"),
                reliability=args.get("reliability"),
                notes=args.get("notes"),
            )
        )

    def discovery_check(self, args: dict) -> dict:
        source_id = str(args.get("source_id") or "").strip()
        if not source_id:
            raise ValueError("source.discovery.check needs source_id.")
        return json_value(
            self._learning().record_check(
                source_id,
                ok=bool(args.get("ok", False)),
                error=args.get("error"),
            )
        )

    def discovery_list(self, args: dict) -> dict:
        rows = self._learning().list(
            status=args.get("status"),
            sport=args.get("sport"),
            capability=args.get("capability"),
            limit=int(args.get("limit", 100)),
        )
        return {"sources": [json_value(item) for item in rows]}

    @staticmethod
    def _source_names(args: dict) -> tuple[str, ...]:
        raw = args.get("source_names")
        if raw is None and args.get("source"):
            raw = [args.get("source")]
        if raw is None:
            return ()
        if isinstance(raw, str):
            raw = [raw]
        if not isinstance(raw, list):
            raise ValueError("source/source_names must be a source name or list of source names.")
        return tuple(str(name).strip() for name in raw if str(name).strip())

    @staticmethod
    def _request_key(
        capability: str,
        sport: str | None,
        metadata: dict,
        source_names: tuple[str, ...] = (),
    ) -> str:
        raw = repr(
            (
                capability.casefold(),
                (sport or "").casefold(),
                sorted(metadata.items()),
                tuple(name.casefold() for name in source_names),
            )
        )
        return f"source:{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:24]}"
