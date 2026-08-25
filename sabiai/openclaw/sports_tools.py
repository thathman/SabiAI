from __future__ import annotations

import hashlib

from sabiai.sources import SourceRequest, SourceService


class SportsTools:
    """Plain-language sports lookup tools with provider-scoped identity handling.

    Source IDs are never assumed to be portable. A TheSportsDB team id is resolved and used
    only with TheSportsDB; an ESPN team id is resolved and used only with ESPN. This matters
    whenever Sabi Boy combines multiple free sources for form or availability research.
    """

    _DEFAULT_FORM_SOURCES = ("TheSportsDB", "ESPN Public Data")

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
            "sports.team_injuries": self.team_injuries,
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
        metadata = {"date": date_value, **self._provider_context(args)}
        if args.get("league_id"):
            metadata["league_id"] = args["league_id"]
        return self._query(
            "fixtures",
            sport or None,
            metadata,
            ttl_seconds=int(args.get("ttl_seconds", 900)),
            source_names=self._source_names(args),
        )

    def event_search(self, args: dict) -> dict:
        event = str(args.get("event") or args.get("query") or "").strip()
        if not event:
            raise ValueError("sports.event_search needs an event/query.")
        metadata = {"event": event, **self._provider_context(args)}
        if args.get("date"):
            metadata["date"] = args["date"]
        if args.get("season"):
            metadata["season"] = args["season"]
        return self._query(
            "event_search",
            str(args.get("sport") or "").strip() or None,
            metadata,
            ttl_seconds=int(args.get("ttl_seconds", 3600)),
            source_names=self._source_names(args),
        )

    def event_lookup(self, args: dict) -> dict:
        source_names = self._source_names(args)
        event_id = args.get("event_id") or self._resolve_event_id(args, source_names=source_names)
        return self._query(
            "event_lookup",
            str(args.get("sport") or "").strip() or None,
            {"event_id": event_id, **self._provider_context(args)},
            ttl_seconds=int(args.get("ttl_seconds", 3600)),
            source_names=source_names,
        )

    def team_search(self, args: dict) -> dict:
        team = str(args.get("team") or args.get("query") or "").strip()
        if not team:
            raise ValueError("sports.team_search needs team/query.")
        return self._query(
            "team_search",
            str(args.get("sport") or "").strip() or None,
            {"team": team, **self._provider_context(args)},
            ttl_seconds=int(args.get("ttl_seconds", 86400)),
            source_names=self._source_names(args),
        )

    def team_profile(self, args: dict) -> dict:
        source_names = self._source_names(args)
        team_id = args.get("team_id") or self._resolve_team_id(args, source_names=source_names)
        return self._query(
            "team_profile",
            str(args.get("sport") or "").strip() or None,
            {"team_id": team_id, **self._provider_context(args)},
            ttl_seconds=int(args.get("ttl_seconds", 86400)),
            source_names=source_names,
        )

    def team_form(self, args: dict) -> dict:
        team = str(args.get("team") or "").strip()
        sport = str(args.get("sport") or "").strip() or None
        if not team and not args.get("team_id"):
            raise ValueError("sports.team_form needs an explicit team name or provider-specific team_id.")

        requested = self._source_names(args)
        if requested:
            sources = requested
        elif args.get("team_id"):
            raise ValueError(
                "A raw team_id is provider-specific. Supply source/source_names with team_id, or use the team name so Sabi Boy can resolve each provider safely."
            )
        else:
            sources = self._DEFAULT_FORM_SOURCES

        results, failures = self._team_multi_source(
            capability="form",
            team=team,
            sport=sport,
            args=args,
            sources=sources,
            ttl_seconds=int(args.get("ttl_seconds", 21600)),
        )
        if not results:
            raise RuntimeError("No free source returned usable form data. " + "; ".join(failures))

        complete = any(not item.get("partial", False) for item in results)
        return {
            "team": team or None,
            "sport": sport,
            "sources": results,
            "complete": complete,
            "needs_more_sources": not complete,
            "failures": failures,
            "note": (
                None
                if complete
                else "Available free-source form is partial. Ask the Research Scout for another public/official source before treating the form picture as complete."
            ),
        }

    def team_schedule(self, args: dict) -> dict:
        team = str(args.get("team") or "").strip()
        sport = str(args.get("sport") or "").strip() or None
        source_names = self._source_names(args)
        if args.get("team_id") and not source_names:
            raise ValueError("team_id is provider-specific; include source/source_names.")
        if source_names:
            sources = source_names
        elif team:
            sources = self._DEFAULT_FORM_SOURCES
        else:
            raise ValueError("sports.team_schedule needs team or provider-specific team_id + source.")

        results, failures = self._team_multi_source(
            capability="schedule",
            team=team,
            sport=sport,
            args=args,
            sources=sources,
            ttl_seconds=int(args.get("ttl_seconds", 21600)),
        )
        if not results:
            raise RuntimeError("No free source returned usable schedule data. " + "; ".join(failures))
        return {
            "team": team or None,
            "sport": sport,
            "sources": results,
            "complete": any(not item.get("partial", False) for item in results),
            "failures": failures,
        }

    def team_injuries(self, args: dict) -> dict:
        """Check a team availability/injury feed without claiming it is exhaustive.

        ESPN is currently the built-in no-key injury source for its covered leagues. Official
        team/league/news confirmation is still requested for material absences because public
        injury feed coverage differs greatly by sport and competition.
        """
        team = str(args.get("team") or "").strip()
        sport = str(args.get("sport") or "").strip() or None
        source_names = self._source_names(args) or ("ESPN Public Data",)
        if args.get("team_id") and not self._source_names(args):
            raise ValueError("team_id is provider-specific; include source/source_names.")
        if not team and not args.get("team_id"):
            raise ValueError("sports.team_injuries needs team or provider-specific team_id + source.")

        results, failures = self._team_multi_source(
            capability="injuries",
            team=team,
            sport=sport,
            args=args,
            sources=source_names,
            ttl_seconds=int(args.get("ttl_seconds", 1800)),
        )
        return {
            "team": team or None,
            "sport": sport,
            "sources": results,
            "complete": False,
            "needs_official_confirmation": True,
            "failures": failures,
            "note": (
                "Public injury/availability feeds are supporting evidence, not the final word. "
                "For a selection affected by availability, Sabi Boy should also check a current official team/league source or fresh reputable reporting."
            ),
        }

    def compare_form(self, args: dict) -> dict:
        home = str(args.get("home") or "").strip()
        away = str(args.get("away") or "").strip()
        if not home or not away:
            raise ValueError("sports.compare_form needs explicit home and away team names.")
        shared = {
            "sport": str(args.get("sport") or "").strip(),
            "league": args.get("league"),
            "league_slug": args.get("league_slug"),
            "espn_sport": args.get("espn_sport"),
            "season": args.get("season"),
            "limit": args.get("limit", 10),
            "ttl_seconds": args.get("ttl_seconds", 21600),
        }
        if args.get("source"):
            shared["source"] = args["source"]
        if args.get("source_names"):
            shared["source_names"] = args["source_names"]
        home_result = self.team_form({"team": home, **shared})
        away_result = self.team_form({"team": away, **shared})
        complete = bool(home_result.get("complete") and away_result.get("complete"))
        return {
            "home_team": home,
            "away_team": away,
            "home": home_result,
            "away": away_result,
            "complete": complete,
            "note": (
                None
                if complete
                else "At least one side still has only partial free-source form coverage. Research another source before treating this as a complete comparison."
            ),
        }

    def player_search(self, args: dict) -> dict:
        player = str(args.get("player") or args.get("query") or "").strip()
        if not player:
            raise ValueError("sports.player_search needs player/query.")
        return self._query(
            "player_search",
            str(args.get("sport") or "").strip() or None,
            {"player": player, **self._provider_context(args)},
            ttl_seconds=int(args.get("ttl_seconds", 86400)),
            source_names=self._source_names(args),
        )

    def player_profile(self, args: dict) -> dict:
        source_names = self._source_names(args)
        player_id = args.get("player_id") or self._resolve_player_id(args, source_names=source_names)
        return self._query(
            "player_profile",
            str(args.get("sport") or "").strip() or None,
            {"player_id": player_id, **self._provider_context(args)},
            ttl_seconds=int(args.get("ttl_seconds", 86400)),
            source_names=source_names,
        )

    def player_stats(self, args: dict) -> dict:
        source_names = self._source_names(args)
        player_id = args.get("player_id") or self._resolve_player_id(args, source_names=source_names)
        return self._query(
            "player_stats",
            str(args.get("sport") or "").strip() or None,
            {"player_id": player_id, **self._provider_context(args)},
            ttl_seconds=int(args.get("ttl_seconds", 21600)),
            source_names=source_names,
        )

    def event_lineup(self, args: dict) -> dict:
        source_names = self._source_names(args)
        event_id = args.get("event_id") or self._resolve_event_id(args, source_names=source_names)
        result = self._query(
            "availability",
            str(args.get("sport") or "").strip() or None,
            {"event_id": event_id, **self._provider_context(args)},
            ttl_seconds=int(args.get("ttl_seconds", 1800)),
            source_names=source_names,
        )
        result["event_id"] = str(event_id)
        result["complete_availability"] = False
        result["note"] = (
            "This is lineup/availability evidence, not guaranteed complete injury or withdrawal coverage. "
            "Combine with official/team/news checks when availability matters."
        )
        return result

    def event_stats(self, args: dict) -> dict:
        source_names = self._source_names(args)
        event_id = args.get("event_id") or self._resolve_event_id(args, source_names=source_names)
        result = self._query(
            "event_stats",
            str(args.get("sport") or "").strip() or None,
            {"event_id": event_id, **self._provider_context(args)},
            ttl_seconds=int(args.get("ttl_seconds", 21600)),
            source_names=source_names,
        )
        result["event_id"] = str(event_id)
        return result

    def _team_multi_source(
        self,
        *,
        capability: str,
        team: str,
        sport: str | None,
        args: dict,
        sources: tuple[str, ...],
        ttl_seconds: int,
    ) -> tuple[list[dict], list[str]]:
        results: list[dict] = []
        failures: list[str] = []
        provider_context = self._provider_context(args)
        for source_name in sources:
            try:
                if args.get("team_id"):
                    team_id = str(args["team_id"])
                else:
                    team_id = self._resolve_team_id_for_source(
                        team,
                        sport=sport,
                        source_name=source_name,
                        args=args,
                    )
                metadata = {
                    "team_id": team_id,
                    "limit": args.get("limit", 10),
                    **provider_context,
                }
                if args.get("season"):
                    metadata["season"] = args["season"]
                response = self._query(
                    capability,
                    sport,
                    metadata,
                    ttl_seconds=ttl_seconds,
                    source_names=(source_name,),
                )
                results.append(
                    {
                        "source": source_name,
                        "team_id": team_id,
                        "partial": self._partial(response),
                        "response": response,
                    }
                )
            except Exception as exc:
                failures.append(f"{source_name}: {exc}")
        return results, failures

    def _resolve_team_id(self, args: dict, *, source_names: tuple[str, ...] = ()) -> str:
        team = str(args.get("team") or args.get("query") or "").strip()
        if not team:
            raise ValueError("Provide team or team_id.")
        if len(source_names) > 1:
            raise ValueError("Resolve a provider-specific team id from only one source at a time.")
        source_name = source_names[0] if source_names else None
        if source_name:
            return self._resolve_team_id_for_source(
                team,
                sport=str(args.get("sport") or "").strip() or None,
                source_name=source_name,
                args=args,
            )
        found = self.team_search({"team": team, "sport": args.get("sport") or ""})
        return self._extract_team_id(found, source_name=found.get("source"))

    def _resolve_team_id_for_source(
        self,
        team: str,
        *,
        sport: str | None,
        source_name: str,
        args: dict,
    ) -> str:
        found = self._query(
            "team_search",
            sport,
            {"team": team, **self._provider_context(args)},
            ttl_seconds=86400,
            source_names=(source_name,),
        )
        return self._extract_team_id(found, source_name=source_name)

    @staticmethod
    def _extract_team_id(found: dict, *, source_name: str | None) -> str:
        payload = found.get("payload") or {}
        raw = payload.get("raw") if isinstance(payload, dict) else None
        teams = raw.get("teams") if isinstance(raw, dict) else None
        if not isinstance(teams, list) or not teams:
            raise RuntimeError("Source returned no team identity candidates.")
        first = teams[0] if isinstance(teams[0], dict) else {}
        if (source_name or "").casefold() == "thesportsdb".casefold():
            value = first.get("idTeam")
        elif (source_name or "").casefold() == "ESPN Public Data".casefold():
            value = first.get("id") or first.get("uid")
        else:
            value = first.get("idTeam") or first.get("id") or first.get("uid")
        if value is None or str(value).strip() == "":
            raise RuntimeError(f"{source_name or 'Source'} returned a team but no usable provider team id.")
        return str(value)

    def _resolve_player_id(self, args: dict, *, source_names: tuple[str, ...] = ()) -> str:
        player = str(args.get("player") or args.get("query") or "").strip()
        if not player:
            raise ValueError("Provide player or player_id.")
        found = self.player_search(
            {
                "player": player,
                "sport": args.get("sport") or "",
                "source_names": list(source_names) if source_names else None,
            }
        )
        payload = found.get("payload") or {}
        players = ((payload.get("raw") or {}).get("players") or []) if isinstance(payload, dict) else []
        if not players or not players[0].get("idPlayer"):
            raise RuntimeError(f"Could not resolve a source player ID for {player}.")
        return str(players[0]["idPlayer"])

    def _resolve_event_id(self, args: dict, *, source_names: tuple[str, ...] = ()) -> str:
        event = str(args.get("event") or args.get("query") or "").strip()
        if not event:
            raise ValueError("Provide event or event_id.")
        found = self.event_search(
            {
                "event": event,
                "sport": args.get("sport") or "",
                "date": args.get("date"),
                "season": args.get("season"),
                "league": args.get("league"),
                "league_slug": args.get("league_slug"),
                "source_names": list(source_names) if source_names else None,
            }
        )
        payload = found.get("payload") or {}
        events = ((payload.get("raw") or {}).get("events") or []) if isinstance(payload, dict) else []
        if not events:
            raise RuntimeError(f"Could not resolve a source event ID for {event}.")
        first = events[0]
        source = (found.get("source") or "").casefold()
        if source == "thesportsdb".casefold():
            value = first.get("idEvent")
        else:
            value = first.get("idEvent") or first.get("id") or first.get("uid")
        if value is None:
            raise RuntimeError(f"Could not resolve a provider event ID for {event}.")
        return str(value)

    @staticmethod
    def _partial(result: dict) -> bool:
        payload = result.get("payload") or {}
        raw = payload.get("raw") if isinstance(payload, dict) else None
        return bool(isinstance(raw, dict) and raw.get("partial"))

    @staticmethod
    def _provider_context(args: dict) -> dict:
        keys = ("league", "league_slug", "espn_sport", "season")
        return {key: args[key] for key in keys if args.get(key) is not None and args.get(key) != ""}

    @staticmethod
    def _source_names(args: dict) -> tuple[str, ...]:
        raw = args.get("source_names")
        if raw is None and args.get("source"):
            raw = [args["source"]]
        if raw is None:
            return ()
        if isinstance(raw, str):
            raw = [raw]
        if not isinstance(raw, list):
            raise ValueError("source/source_names must be a source name or list of source names.")
        return tuple(str(value).strip() for value in raw if str(value).strip())

    def _query(
        self,
        capability: str,
        sport: str | None,
        metadata: dict,
        *,
        ttl_seconds: int,
        source_names: tuple[str, ...] = (),
    ) -> dict:
        clean_metadata = {key: value for key, value in metadata.items() if value is not None and value != ""}
        raw_key = repr(
            (
                capability,
                (sport or "").casefold(),
                sorted(clean_metadata.items()),
                tuple(name.casefold() for name in source_names),
            )
        )
        request = SourceRequest(
            request_key=f"sports:{hashlib.sha256(raw_key.encode('utf-8')).hexdigest()[:24]}",
            capability=capability,
            sport=sport,
            ttl_seconds=ttl_seconds,
            metadata=clean_metadata,
            source_names=source_names,
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
