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
            "sports.event_lookup": self.event_lookup,
            "sports.team_search": self.team_search,
            "sports.team_profile": self.team_profile,
            "sports.team_form": self.team_form,
            "sports.team_schedule": self.team_schedule,
            "sports.compare_form": self.compare_form,
            "sports.player_search": self.player_search,
            "sports.player_profile": self.player_profile,
            "sports.player_stats": self.player_stats,
            "sports.event_lineup": self.event_lineup,
            "sports.event_stats": self.event_stats,
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
        return self._query(
            "event_search",
            str(args.get("sport") or "").strip() or None,
            metadata,
            ttl_seconds=int(args.get("ttl_seconds", 3600)),
        )

    def event_lookup(self, args: dict) -> dict:
        event_id = args.get("event_id") or self._resolve_event_id(args)
        return self._query(
            "event_lookup",
            str(args.get("sport") or "").strip() or None,
            {"event_id": event_id},
            ttl_seconds=int(args.get("ttl_seconds", 3600)),
        )

    def team_search(self, args: dict) -> dict:
        team = str(args.get("team") or args.get("query") or "").strip()
        if not team:
            raise ValueError("sports.team_search needs team/query.")
        return self._query(
            "team_search",
            str(args.get("sport") or "").strip() or None,
            {"team": team},
            ttl_seconds=int(args.get("ttl_seconds", 86400)),
        )

    def team_profile(self, args: dict) -> dict:
        team_id = args.get("team_id") or self._resolve_team_id(args)
        return self._query(
            "team_profile",
            str(args.get("sport") or "").strip() or None,
            {"team_id": team_id},
            ttl_seconds=int(args.get("ttl_seconds", 86400)),
        )

    def team_form(self, args: dict) -> dict:
        team_id = args.get("team_id") or self._resolve_team_id(args)
        result = self._query(
            "form",
            str(args.get("sport") or "").strip() or None,
            {"team_id": team_id},
            ttl_seconds=int(args.get("ttl_seconds", 21600)),
        )
        result["team"] = args.get("team")
        result["team_id"] = str(team_id)
        result["needs_more_sources"] = self._partial(result)
        return result

    def team_schedule(self, args: dict) -> dict:
        team_id = args.get("team_id") or self._resolve_team_id(args)
        result = self._query(
            "schedule",
            str(args.get("sport") or "").strip() or None,
            {"team_id": team_id},
            ttl_seconds=int(args.get("ttl_seconds", 21600)),
        )
        result["team"] = args.get("team")
        result["team_id"] = str(team_id)
        result["needs_more_sources"] = self._partial(result)
        return result

    def compare_form(self, args: dict) -> dict:
        home = str(args.get("home") or "").strip()
        away = str(args.get("away") or "").strip()
        if not home or not away:
            raise ValueError("sports.compare_form needs explicit home and away team names.")
        sport = str(args.get("sport") or "").strip() or None
        home_result = self.team_form({"team": home, "sport": sport or "", "ttl_seconds": args.get("ttl_seconds", 21600)})
        away_result = self.team_form({"team": away, "sport": sport or "", "ttl_seconds": args.get("ttl_seconds", 21600)})
        return {
            "home": {"team": home, "form": home_result},
            "away": {"team": away, "form": away_result},
            "complete": not (home_result.get("needs_more_sources") or away_result.get("needs_more_sources")),
            "note": (
                "At least one free-source form response is partial; use another source before treating this as a complete form comparison."
                if home_result.get("needs_more_sources") or away_result.get("needs_more_sources")
                else None
            ),
        }

    def player_search(self, args: dict) -> dict:
        player = str(args.get("player") or args.get("query") or "").strip()
        if not player:
            raise ValueError("sports.player_search needs player/query.")
        return self._query(
            "player_search",
            str(args.get("sport") or "").strip() or None,
            {"player": player},
            ttl_seconds=int(args.get("ttl_seconds", 86400)),
        )

    def player_profile(self, args: dict) -> dict:
        player_id = args.get("player_id") or self._resolve_player_id(args)
        return self._query(
            "player_profile",
            str(args.get("sport") or "").strip() or None,
            {"player_id": player_id},
            ttl_seconds=int(args.get("ttl_seconds", 86400)),
        )

    def player_stats(self, args: dict) -> dict:
        player_id = args.get("player_id") or self._resolve_player_id(args)
        return self._query(
            "player_stats",
            str(args.get("sport") or "").strip() or None,
            {"player_id": player_id},
            ttl_seconds=int(args.get("ttl_seconds", 21600)),
        )

    def event_lineup(self, args: dict) -> dict:
        event_id = args.get("event_id") or self._resolve_event_id(args)
        result = self._query(
            "availability",
            str(args.get("sport") or "").strip() or None,
            {"event_id": event_id},
            ttl_seconds=int(args.get("ttl_seconds", 1800)),
        )
        result["event_id"] = str(event_id)
        result["complete_availability"] = False
        result["note"] = "This source provides lineup evidence, not a complete injury/withdrawal feed. Combine with official/team/news checks when availability matters."
        return result

    def event_stats(self, args: dict) -> dict:
        event_id = args.get("event_id") or self._resolve_event_id(args)
        result = self._query(
            "event_stats",
            str(args.get("sport") or "").strip() or None,
            {"event_id": event_id},
            ttl_seconds=int(args.get("ttl_seconds", 21600)),
        )
        result["event_id"] = str(event_id)
        return result

    def _resolve_team_id(self, args: dict) -> str:
        team = str(args.get("team") or args.get("query") or "").strip()
        if not team:
            raise ValueError("Provide team or team_id.")
        found = self.team_search({"team": team, "sport": args.get("sport") or ""})
        payload = found.get("payload") or {}
        teams = ((payload.get("raw") or {}).get("teams") or []) if isinstance(payload, dict) else []
        if not teams or not teams[0].get("idTeam"):
            raise RuntimeError(f"Could not resolve a source team ID for {team}.")
        return str(teams[0]["idTeam"])

    def _resolve_player_id(self, args: dict) -> str:
        player = str(args.get("player") or args.get("query") or "").strip()
        if not player:
            raise ValueError("Provide player or player_id.")
        found = self.player_search({"player": player, "sport": args.get("sport") or ""})
        payload = found.get("payload") or {}
        players = ((payload.get("raw") or {}).get("players") or []) if isinstance(payload, dict) else []
        if not players or not players[0].get("idPlayer"):
            raise RuntimeError(f"Could not resolve a source player ID for {player}.")
        return str(players[0]["idPlayer"])

    def _resolve_event_id(self, args: dict) -> str:
        event = str(args.get("event") or args.get("query") or "").strip()
        if not event:
            raise ValueError("Provide event or event_id.")
        found = self.event_search(
            {
                "event": event,
                "sport": args.get("sport") or "",
                "date": args.get("date"),
                "season": args.get("season"),
            }
        )
        payload = found.get("payload") or {}
        events = ((payload.get("raw") or {}).get("events") or []) if isinstance(payload, dict) else []
        if not events or not events[0].get("idEvent"):
            raise RuntimeError(f"Could not resolve a source event ID for {event}.")
        return str(events[0]["idEvent"])

    @staticmethod
    def _partial(result: dict) -> bool:
        payload = result.get("payload") or {}
        raw = payload.get("raw") if isinstance(payload, dict) else None
        return bool(isinstance(raw, dict) and raw.get("partial"))

    def _query(self, capability: str, sport: str | None, metadata: dict, *, ttl_seconds: int) -> dict:
        clean_metadata = {key: value for key, value in metadata.items() if value is not None and value != ""}
        raw_key = repr((capability, (sport or "").casefold(), sorted(clean_metadata.items())))
        request = SourceRequest(
            request_key=f"sports:{hashlib.sha256(raw_key.encode('utf-8')).hexdigest()[:24]}",
            capability=capability,
            sport=sport,
            ttl_seconds=ttl_seconds,
            metadata=clean_metadata,
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
