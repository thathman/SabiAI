from __future__ import annotations

import hashlib

from sabiai.sources import SourceRequest, SourceService


class SourceTools:
    def __init__(self, app):
        self.app = app

    def handlers(self) -> dict:
        return {
            "source.catalog": self.catalog,
            "source.query": self.query,
        }

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
        return {"sources": sources}

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
