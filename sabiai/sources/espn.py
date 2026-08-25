from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from .http import JsonHttpClient
from .registry import Source, SourceCost, SourceKind
from .service import SourceRequest


HttpGet = Callable[..., object]


DEFAULT_LEAGUES = {
    "basketball": "nba",
    "baseball": "mlb",
    "ice_hockey": "nhl",
    "ice hockey": "nhl",
    "hockey": "nhl",
    "american_football": "nfl",
    "american football": "nfl",
    "nfl": "nfl",
}

ESPN_SPORTS = {
    "football": "soccer",
    "soccer": "soccer",
    "basketball": "basketball",
    "baseball": "baseball",
    "ice_hockey": "hockey",
    "ice hockey": "hockey",
    "hockey": "hockey",
    "american_football": "football",
    "american football": "football",
    "nfl": "football",
}


@dataclass
class EspnPublicAdapter:
    """Secondary no-key adapter for ESPN's public site-facing JSON endpoints.

    ESPN does not publish this as a supported developer API contract. Treat it as a useful
    public-web data source with medium reliability and fall back cleanly if routes change.
    """

    http_get: HttpGet | None = None

    name = "ESPN Public Data"
    base_url = "https://site.api.espn.com/apis/site/v2/sports"

    def __post_init__(self) -> None:
        if self.http_get is None:
            self.http_get = JsonHttpClient().get

    @property
    def source(self) -> Source:
        return Source(
            name=self.name,
            kind=SourceKind.PUBLIC_ENDPOINT,
            cost=SourceCost.FREE,
            sports={
                "football",
                "soccer",
                "basketball",
                "baseball",
                "ice_hockey",
                "ice hockey",
                "hockey",
                "american_football",
                "american football",
                "nfl",
            },
            capabilities={
                "fixtures",
                "team_search",
                "team_profile",
                "form",
                "schedule",
                "availability",
                "injuries",
                "event_stats",
                "stats",
                "news",
            },
            priority_bias=5,
            notes=(
                "No-key ESPN site-facing JSON used as a secondary free source. It is not a published developer API contract; "
                "routes/coverage vary by sport and league."
            ),
        )

    def fetch(self, request: SourceRequest) -> object:
        capability = request.capability.strip().casefold()
        metadata = request.metadata or {}
        if capability == "fixtures":
            return self._scoreboard(request, metadata)
        if capability == "team_search":
            return self._team_search(request, metadata)
        if capability == "team_profile":
            return self._team_profile(request, metadata)
        if capability == "form":
            return self._team_schedule(request, metadata, recent_only=True)
        if capability == "schedule":
            return self._team_schedule(request, metadata, recent_only=False)
        if capability in {"availability", "injuries"}:
            return self._injuries(request, metadata)
        if capability in {"stats", "event_stats"}:
            return self._event_summary(request, metadata)
        if capability == "news":
            return self._news(request, metadata)
        raise ValueError(f"ESPN public adapter does not implement capability: {request.capability}")

    def _route(self, request: SourceRequest, metadata: dict, resource: str) -> str:
        sport_raw = (request.sport or metadata.get("sport") or "").casefold().strip()
        espn_sport = str(metadata.get("espn_sport") or ESPN_SPORTS.get(sport_raw) or sport_raw).strip()
        league = str(metadata.get("league") or metadata.get("league_slug") or DEFAULT_LEAGUES.get(sport_raw) or "").strip()
        if not espn_sport:
            raise ValueError("ESPN request needs sport/espn_sport.")
        if not league:
            raise ValueError(
                "ESPN request needs metadata.league for this sport/competition (for example eng.1, usa.1, nba, wnba, mlb or nhl)."
            )
        return f"{self.base_url}/{espn_sport}/{league}/{resource.lstrip('/')}"

    def _scoreboard(self, request: SourceRequest, metadata: dict) -> dict:
        params = {}
        date_value = metadata.get("date") or metadata.get("day")
        if date_value:
            params["dates"] = self._date_key(str(date_value))
        payload = self.http_get(self._route(request, metadata, "scoreboard"), params=params or None)
        events = self._list(payload, "events")
        return {
            "summary": f"ESPN public data returned {len(events)} event(s){f' for {date_value}' if date_value else ''}.",
            "observed_at": str(date_value or ""),
            "reliability": "medium",
            "raw": {"events": events, "partial": False, "source_contract": "public_site_json"},
        }

    def _team_search(self, request: SourceRequest, metadata: dict) -> dict:
        query = str(metadata.get("team") or metadata.get("query") or "").strip()
        if not query:
            raise ValueError("ESPN team search needs metadata.team/query.")
        payload = self.http_get(self._route(request, metadata, "teams"), params=None)
        teams = self._extract_teams(payload)
        needle = self._norm(query)
        matches = [
            team
            for team in teams
            if needle in self._norm(str(team.get("displayName") or team.get("name") or ""))
            or self._norm(str(team.get("displayName") or team.get("name") or "")) in needle
        ]
        if not matches:
            raise RuntimeError(f"ESPN public data did not find team {query} in the requested league.")
        first = matches[0]
        return {
            "summary": f"Found {first.get('displayName') or first.get('name') or query} in ESPN public team data.",
            "subject": str(first.get("displayName") or first.get("name") or query),
            "reliability": "medium",
            "raw": {"teams": matches, "partial": False},
        }

    def _team_profile(self, request: SourceRequest, metadata: dict) -> dict:
        team_id = metadata.get("team_id")
        if not team_id:
            raise ValueError("ESPN team profile needs metadata.team_id.")
        payload = self.http_get(self._route(request, metadata, f"teams/{team_id}"), params=None)
        team = payload.get("team") if isinstance(payload, dict) and isinstance(payload.get("team"), dict) else payload
        if not isinstance(team, dict):
            raise RuntimeError(f"ESPN public data returned no team profile for {team_id}.")
        name = team.get("displayName") or team.get("name") or str(team_id)
        return {
            "summary": f"Loaded {name} team profile from ESPN public data.",
            "subject": str(name),
            "reliability": "medium",
            "raw": {"team": team},
        }

    def _team_schedule(self, request: SourceRequest, metadata: dict, *, recent_only: bool) -> dict:
        team_id = metadata.get("team_id")
        if not team_id:
            raise ValueError("ESPN team schedule/form needs metadata.team_id.")
        params = {}
        if metadata.get("season"):
            params["season"] = metadata["season"]
        payload = self.http_get(
            self._route(request, metadata, f"teams/{team_id}/schedule"),
            params=params or None,
        )
        events = self._list(payload, "events")
        if not events:
            raise RuntimeError(f"ESPN public data returned no schedule events for team {team_id}.")

        if recent_only:
            completed = [event for event in events if self._event_completed(event)]
            completed.sort(key=lambda event: str(event.get("date") or ""), reverse=True)
            limit = max(1, min(int(metadata.get("limit") or 10), 25))
            selected = completed[:limit]
            if not selected:
                raise RuntimeError(f"ESPN public data returned no completed recent events for team {team_id}.")
            return {
                "summary": f"ESPN public data returned {len(selected)} completed recent event(s) for team {team_id}.",
                "subject": str(team_id),
                "reliability": "medium",
                "raw": {"events": selected, "partial": False, "requested_limit": limit},
            }

        return {
            "summary": f"ESPN public data returned {len(events)} schedule event(s) for team {team_id}.",
            "subject": str(team_id),
            "reliability": "medium",
            "raw": {"events": events, "partial": False},
        }

    def _injuries(self, request: SourceRequest, metadata: dict) -> dict:
        team_id = metadata.get("team_id")
        resource = f"teams/{team_id}/injuries" if team_id else "injuries"
        payload = self.http_get(self._route(request, metadata, resource), params=None)
        injuries = self._list(payload, "injuries")
        if not injuries and isinstance(payload, dict):
            # Some leagues nest injuries by team. Preserve the raw object rather than claiming empty.
            nested = payload.get("items") or payload.get("teams")
            if isinstance(nested, list):
                injuries = [item for item in nested if isinstance(item, dict)]
        return {
            "summary": f"ESPN public data returned {len(injuries)} injury-report item(s){f' for team {team_id}' if team_id else ''}.",
            "subject": str(team_id) if team_id else None,
            "reliability": "medium",
            "raw": {
                "injuries": injuries,
                "payload": payload if not injuries else None,
                "partial": False,
                "coverage_note": "Use official team/league confirmation for important availability decisions because public injury-feed coverage varies by league.",
            },
        }

    def _event_summary(self, request: SourceRequest, metadata: dict) -> dict:
        event_id = metadata.get("event_id")
        if not event_id:
            raise ValueError("ESPN event stats needs metadata.event_id.")
        payload = self.http_get(
            self._route(request, metadata, "summary"),
            params={"event": event_id},
        )
        if not isinstance(payload, dict) or not payload:
            raise RuntimeError(f"ESPN public data returned no event summary for {event_id}.")
        return {
            "summary": f"Loaded ESPN public event summary/statistics for event {event_id}.",
            "subject": str(event_id),
            "reliability": "medium",
            "raw": {"summary": payload, "partial": False},
        }

    def _news(self, request: SourceRequest, metadata: dict) -> dict:
        team_id = metadata.get("team_id")
        resource = f"teams/{team_id}/news" if team_id else "news"
        payload = self.http_get(self._route(request, metadata, resource), params=None)
        articles = self._list(payload, "articles") or self._list(payload, "news")
        return {
            "summary": f"ESPN public data returned {len(articles)} news item(s){f' for team {team_id}' if team_id else ''}.",
            "subject": str(team_id) if team_id else None,
            "reliability": "medium",
            "raw": {"articles": articles, "partial": False},
        }

    @staticmethod
    def _date_key(value: str) -> str:
        return value.replace("-", "")

    @staticmethod
    def _norm(value: str) -> str:
        return "".join(ch for ch in value.casefold() if ch.isalnum())

    @staticmethod
    def _list(payload: object, key: str) -> list[dict]:
        if not isinstance(payload, dict):
            return []
        value = payload.get(key)
        return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []

    @classmethod
    def _extract_teams(cls, payload: object) -> list[dict]:
        if not isinstance(payload, dict):
            return []
        sports = payload.get("sports")
        if isinstance(sports, list):
            teams = []
            for sport in sports:
                leagues = sport.get("leagues") if isinstance(sport, dict) else None
                if not isinstance(leagues, list):
                    continue
                for league in leagues:
                    entries = league.get("teams") if isinstance(league, dict) else None
                    if not isinstance(entries, list):
                        continue
                    for entry in entries:
                        if isinstance(entry, dict):
                            team = entry.get("team") if isinstance(entry.get("team"), dict) else entry
                            if isinstance(team, dict):
                                teams.append(team)
            return teams
        teams = payload.get("teams")
        if isinstance(teams, list):
            result = []
            for entry in teams:
                if not isinstance(entry, dict):
                    continue
                team = entry.get("team") if isinstance(entry.get("team"), dict) else entry
                if isinstance(team, dict):
                    result.append(team)
            return result
        return []

    @staticmethod
    def _event_completed(event: dict) -> bool:
        status = event.get("status") if isinstance(event, dict) else None
        status_type = status.get("type") if isinstance(status, dict) else None
        if isinstance(status_type, dict) and status_type.get("completed") is not None:
            return bool(status_type.get("completed"))
        competitions = event.get("competitions") if isinstance(event, dict) else None
        if isinstance(competitions, list) and competitions:
            comp_status = competitions[0].get("status") if isinstance(competitions[0], dict) else None
            comp_type = comp_status.get("type") if isinstance(comp_status, dict) else None
            if isinstance(comp_type, dict) and comp_type.get("completed") is not None:
                return bool(comp_type.get("completed"))
        return False
