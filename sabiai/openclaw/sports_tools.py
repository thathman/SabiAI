from __future__ import annotations

import hashlib

from sabiai.sources import SourceRequest, SourceService


class SportsTools:
    def __init__(self, app):
        self.app = app

    def handlers(self) -> dict:
        return {
            "sports.list": self.list_sports,
            "sports.describe": self.describe,
            "sports.fixtures": self.fixtures,
            "sports.event_search": self.event_search,
            "sports.team_profile": self.team_profile,
            "sports.player_profile": self.player_profile,
            "sports.player_stats": self.player_stats,
        }

    def list_sports(self, args: dict) -> dict:
        return {
            "sports": [
                {"name": profile.name, "slug": profile.slug}
                for profile in self.app.sports.all()
            ],
            "open_ended": True,
            "note": "This registry is a starting knowledge set, not a coverage limit.",
        }

    def describe(self, args: dict) -> dict:
        profile = self.app.sports.resolve(str(args.get("sport", "")))
        return {
            "name": profile.name,
            "slug": profile.slug,
            "participant_shape": profile.participant_shape,
            "event_parts": list(profile.event_parts),
            "common_metrics": list(profile.common_metrics),
            "research_topics": list(profile.research_topics),
            "draw_possible": profile.draw_possible,
            "needs_discovery": profile.needs_discovery,
        }

    def fixtures(self, args: dict) -> dict:
        sport = str(args.get("sport") or "").strip()
        date_value = str(args.get("date") or "").strip()
        if not date_value:
            raise ValueError("sports.fixtures needs date in YYYY-MM-DD format.")
        metadata = {"date": date_value}
        if args.get("league_id"):
            metadata["league_id"] = args["league_id"]
        return self._query("fixtures", sport or None, metadata, ttl_seconds=int(args.get("ttl_seconds", 900)))

    def event_search(self, args: dict) -> dict:
        event = str(args.get("event") or args.get("query") or "").strip()
        if not event:
            raise ValueError("sports.event_search needs an event/query.")
        metadata = {"event": event}
        if args.get("date"):
            metadata["date"] = args["date"]
        if args.get("season"):
            metadata["season"] = args["season"]
        return self._query("event_search", str(args.get("sport") or "").strip() or None, metadata, ttl_seconds=int(args.get("ttl_seconds", 3600)))

    def team_profile(self, args: dict) -> dict:
        if not args.get("team_id"):
            raise ValueError("sports.team_profile needs team_id.")
        return self._query(
            "team_profile",
            str(args.get("sport") or "").strip() or None,
            {"team_id": args["team_id"]},
            ttl_seconds=int(args.get("ttl_seconds", 86400)),
        )

    def player_profile(self, args: dict) -> dict:
        if not args.get("player_id"):
            raise ValueError("sports.player_profile needs player_id.")
        return self._query(
            "player_profile",
            str(args.get("sport") or "").strip() or None,
            {"player_id": args["player_id"]},
            ttl_seconds=int(args.get("ttl_seconds", 86400)),
        )

    def player_stats(self, args: dict) -> dict:
        if not args.get("player_id"):
            raise ValueError("sports.player_stats needs player_id.")
        return self._query(
            "player_stats",
            str(args.get("sport") or "").strip() or None,
            {"player_id": args["player_id"]},
            ttl_seconds=int(args.get("ttl_seconds", 21600)),
        )

    def _query(self, capability: str, sport: str | None, metadata: dict, *, ttl_seconds: int) -> dict:
        raw_key = repr((capability, (sport or "").casefold(), sorted(metadata.items())))
        request = SourceRequest(
            request_key=f"sports:{hashlib.sha256(raw_key.encode('utf-8')).hexdigest()[:24]}",
            capability=capability,
            sport=sport,
            ttl_seconds=ttl_seconds,
            metadata=metadata,
        )
        response = SourceService(
            self.app._db(initialize=True),
            self.app.source_bundle.registry,
        ).execute(request, self.app.source_bundle.fetchers)
        return {
            "source": response.source_name,
            "cache_hit": response.cache_hit,
            "fetched_at": response.fetched_at.isoformat(),
            "payload": response.payload,
            "fallback_failures": list(response.failures),
        }
