from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .http import JsonHttpClient
from .registry import Source, SourceCost, SourceKind
from .service import SourceRequest


HttpGet = Callable[..., object]


SPORT_NAMES = {
    "football": "Soccer",
    "soccer": "Soccer",
    "basketball": "Basketball",
    "volleyball": "Volleyball",
    "tennis": "Tennis",
    "table_tennis": "Table Tennis",
    "table tennis": "Table Tennis",
    "baseball": "Baseball",
    "ice_hockey": "Ice Hockey",
    "ice hockey": "Ice Hockey",
    "hockey": "Ice Hockey",
    "cricket": "Cricket",
    "golf": "Golf",
    "handball": "Handball",
    "rugby": "Rugby",
    "motorsport": "Motorsport",
    "cycling": "Cycling",
    "fighting": "Fighting",
    "mma": "Fighting",
    "boxing": "Fighting",
}


@dataclass
class TheSportsDBAdapter:
    """Documented free v1 adapter for broad sports discovery/schedules/profiles.

    The free API has endpoint-specific result limits. Every partial endpoint keeps that
    limitation in its summary/raw metadata so Sabi Boy does not mistake a one-row free
    response for complete form, lineup or schedule coverage.
    """

    http_get: HttpGet | None = None
    api_key: str = "123"

    name = "TheSportsDB"
    base_url = "https://www.thesportsdb.com/api/v1/json"

    def __post_init__(self) -> None:
        if self.http_get is None:
            self.http_get = JsonHttpClient().get

    @property
    def source(self) -> Source:
        return Source(
            name=self.name,
            kind=SourceKind.PUBLIC_ENDPOINT,
            cost=SourceCost.FREE,
            capabilities={
                "fixtures",
                "event_search",
                "event_lookup",
                "team_search",
                "team_profile",
                "player_search",
                "player_profile",
                "player_stats",
                "league_table",
                "form",
                "schedule",
                "availability",
                "lineup",
                "stats",
                "event_stats",
                "event_results",
            },
            priority_bias=0,
            notes=(
                "Documented TheSportsDB v1 free API. Free endpoints have request/result limits; "
                "schedule/form may expose only one home event and lineup is not an injury feed."
            ),
        )

    def fetch(self, request: SourceRequest) -> object:
        capability = request.capability.strip().casefold()
        metadata = request.metadata or {}
        if capability == "fixtures":
            return self._fixtures(request)
        if capability == "event_search":
            return self._event_search(metadata)
        if capability == "event_lookup":
            return self._event_lookup(metadata)
        if capability == "team_search":
            return self._team_search(metadata)
        if capability == "team_profile":
            return self._team_profile(metadata)
        if capability == "player_search":
            return self._player_search(metadata)
        if capability == "player_profile":
            return self._player_profile(metadata)
        if capability == "player_stats":
            return self._player_stats(metadata)
        if capability == "league_table":
            return self._league_table(metadata)
        if capability == "form":
            return self._team_previous(metadata)
        if capability == "schedule":
            return self._team_next(metadata)
        if capability in {"availability", "lineup"}:
            return self._event_lineup(metadata)
        if capability in {"stats", "event_stats"}:
            if metadata.get("event_id"):
                return self._event_stats(metadata)
            if metadata.get("player_id"):
                return self._player_stats(metadata)
            raise ValueError("TheSportsDB stats request needs metadata.event_id or metadata.player_id.")
        if capability == "event_results":
            return self._event_results(metadata)
        raise ValueError(f"TheSportsDB does not implement capability: {request.capability}")

    def _url(self, endpoint: str) -> str:
        return f"{self.base_url}/{self.api_key}/{endpoint}"

    def _fixtures(self, request: SourceRequest) -> dict:
        metadata = request.metadata or {}
        date_value = metadata.get("date") or metadata.get("day")
        if not date_value:
            raise ValueError("TheSportsDB fixtures request needs metadata.date (YYYY-MM-DD).")
        params = {"d": date_value}
        sport_name = SPORT_NAMES.get((request.sport or "").casefold(), request.sport)
        if sport_name:
            params["s"] = sport_name
        if metadata.get("league_id"):
            params.pop("s", None)
            params["l"] = metadata["league_id"]
        payload = self.http_get(self._url("eventsday.php"), params=params)
        events = self._list(payload, "events")
        return {
            "summary": f"TheSportsDB returned {len(events)} event(s) for {date_value}{f' in {sport_name}' if sport_name else ''}.",
            "observed_at": str(date_value),
            "reliability": "medium",
            "raw": {
                "events": events,
                "coverage_note": "TheSportsDB free schedule endpoints have documented per-request result limits.",
            },
        }

    def _event_search(self, metadata: dict) -> dict:
        event = str(metadata.get("event") or metadata.get("query") or "").strip()
        if not event:
            raise ValueError("TheSportsDB event search needs metadata.event or metadata.query.")
        params = {"e": event.replace(" ", "_")}
        if metadata.get("date"):
            params["d"] = metadata["date"]
        if metadata.get("season"):
            params["s"] = metadata["season"]
        payload = self.http_get(self._url("searchevents.php"), params=params)
        events = self._list(payload, "event") or self._list(payload, "events")
        if not events:
            raise RuntimeError(f"No TheSportsDB event found for {event}.")
        first = events[0]
        name = first.get("strEvent") or event
        date = first.get("dateEvent") or first.get("strTimestamp") or "unknown date"
        league = first.get("strLeague") or "unknown competition"
        return {
            "summary": f"Found {name} in {league} on {date} via TheSportsDB.",
            "subject": name,
            "observed_at": str(first.get("strTimestamp") or date),
            "reliability": "medium",
            "raw": {
                "events": events,
                "coverage_note": "TheSportsDB free event search is result-limited.",
            },
        }

    def _event_lookup(self, metadata: dict) -> dict:
        event_id = metadata.get("event_id")
        if not event_id:
            raise ValueError("TheSportsDB event lookup needs metadata.event_id.")
        payload = self.http_get(self._url("lookupevent.php"), params={"id": event_id})
        events = self._list(payload, "events")
        if not events:
            raise RuntimeError(f"No TheSportsDB event found for id {event_id}.")
        event = events[0]
        name = event.get("strEvent") or str(event_id)
        return {
            "summary": f"Loaded event details for {name} from TheSportsDB.",
            "subject": name,
            "observed_at": str(event.get("strTimestamp") or event.get("dateEvent") or ""),
            "reliability": "medium",
            "raw": {"event": event},
        }

    def _team_search(self, metadata: dict) -> dict:
        team = str(metadata.get("team") or metadata.get("query") or "").strip()
        if not team:
            raise ValueError("TheSportsDB team search needs metadata.team or metadata.query.")
        payload = self.http_get(self._url("searchteams.php"), params={"t": team})
        teams = self._list(payload, "teams")
        if not teams:
            raise RuntimeError(f"No TheSportsDB team found for {team}.")
        first = teams[0]
        name = first.get("strTeam") or team
        return {
            "summary": f"Found {name} via TheSportsDB team search.",
            "subject": name,
            "reliability": "medium",
            "raw": {
                "teams": teams,
                "coverage_note": "TheSportsDB free team-name search is documented as returning a very limited result set.",
            },
        }

    def _team_profile(self, metadata: dict) -> dict:
        team_id = metadata.get("team_id")
        if not team_id:
            raise ValueError("TheSportsDB team profile needs metadata.team_id.")
        payload = self.http_get(self._url("lookupteam.php"), params={"id": team_id})
        teams = self._list(payload, "teams")
        if not teams:
            raise RuntimeError(f"No TheSportsDB team found for id {team_id}.")
        team = teams[0]
        name = team.get("strTeam") or str(team_id)
        league = team.get("strLeague") or "unknown competition"
        return {
            "summary": f"Loaded {name} team profile from TheSportsDB; primary competition: {league}.",
            "subject": name,
            "reliability": "medium",
            "raw": {"team": team},
        }

    def _player_search(self, metadata: dict) -> dict:
        player = str(metadata.get("player") or metadata.get("query") or "").strip()
        if not player:
            raise ValueError("TheSportsDB player search needs metadata.player or metadata.query.")
        payload = self.http_get(self._url("searchplayers.php"), params={"p": player})
        players = self._list(payload, "player") or self._list(payload, "players")
        if not players:
            raise RuntimeError(f"No TheSportsDB player found for {player}.")
        first = players[0]
        name = first.get("strPlayer") or player
        return {
            "summary": f"Found {name} via TheSportsDB player search.",
            "subject": name,
            "reliability": "medium",
            "raw": {"players": players},
        }

    def _player_profile(self, metadata: dict) -> dict:
        player_id = metadata.get("player_id")
        if not player_id:
            raise ValueError("TheSportsDB player profile needs metadata.player_id.")
        payload = self.http_get(self._url("lookupplayer.php"), params={"id": player_id})
        players = self._list(payload, "players")
        if not players:
            raise RuntimeError(f"No TheSportsDB player found for id {player_id}.")
        player = players[0]
        name = player.get("strPlayer") or str(player_id)
        team = player.get("strTeam") or "unknown team"
        return {
            "summary": f"Loaded {name} player profile from TheSportsDB; listed team: {team}.",
            "subject": name,
            "reliability": "medium",
            "raw": {"player": player},
        }

    def _player_stats(self, metadata: dict) -> dict:
        player_id = metadata.get("player_id")
        if not player_id:
            raise ValueError("TheSportsDB player stats needs metadata.player_id.")
        payload = self.http_get(self._url("lookupplayerstats.php"), params={"id": player_id})
        stats = self._list(payload, "playerstats") or self._list(payload, "stats")
        if not stats:
            raise RuntimeError(f"No TheSportsDB player statistics found for id {player_id}.")
        return {
            "summary": f"TheSportsDB returned {len(stats)} player-stat row(s) for player id {player_id}.",
            "subject": str(player_id),
            "reliability": "medium",
            "raw": {"stats": stats},
        }

    def _league_table(self, metadata: dict) -> dict:
        league_id = metadata.get("league_id")
        if not league_id:
            raise ValueError("TheSportsDB league table needs metadata.league_id.")
        params = {"l": league_id}
        if metadata.get("season"):
            params["s"] = metadata["season"]
        payload = self.http_get(self._url("lookuptable.php"), params=params)
        table = self._list(payload, "table")
        if not table:
            raise RuntimeError(f"No TheSportsDB league table found for id {league_id}.")
        return {
            "summary": f"TheSportsDB returned {len(table)} league-table row(s) for league id {league_id}.",
            "subject": str(league_id),
            "reliability": "medium",
            "raw": {"table": table},
        }

    def _team_previous(self, metadata: dict) -> dict:
        team_id = metadata.get("team_id")
        if not team_id:
            raise ValueError("TheSportsDB form request needs metadata.team_id.")
        payload = self.http_get(self._url("eventslast.php"), params={"id": team_id})
        events = self._list(payload, "results") or self._list(payload, "events")
        if not events:
            raise RuntimeError(f"No TheSportsDB previous event returned for team id {team_id}.")
        return {
            "summary": (
                f"TheSportsDB returned {len(events)} recent event row(s) for team id {team_id}. "
                "The free endpoint is partial and must not be treated as complete recent form."
            ),
            "subject": str(team_id),
            "reliability": "medium",
            "raw": {
                "events": events,
                "partial": True,
                "coverage_note": "TheSportsDB documents the free previous-team schedule as one home event; use another source for complete form.",
            },
        }

    def _team_next(self, metadata: dict) -> dict:
        team_id = metadata.get("team_id")
        if not team_id:
            raise ValueError("TheSportsDB schedule request needs metadata.team_id.")
        payload = self.http_get(self._url("eventsnext.php"), params={"id": team_id})
        events = self._list(payload, "events")
        if not events:
            raise RuntimeError(f"No TheSportsDB next event returned for team id {team_id}.")
        return {
            "summary": (
                f"TheSportsDB returned {len(events)} upcoming event row(s) for team id {team_id}. "
                "The free endpoint is partial and must not be treated as a complete schedule."
            ),
            "subject": str(team_id),
            "reliability": "medium",
            "raw": {
                "events": events,
                "partial": True,
                "coverage_note": "TheSportsDB documents the free next-team schedule as one home event; use another source for complete schedule/rest analysis.",
            },
        }

    def _event_lineup(self, metadata: dict) -> dict:
        event_id = metadata.get("event_id")
        if not event_id:
            raise ValueError("TheSportsDB lineup/availability request needs metadata.event_id.")
        payload = self.http_get(self._url("lookuplineup.php"), params={"id": event_id})
        rows = self._list(payload, "lineup") or self._list(payload, "lineups")
        if not rows:
            raise RuntimeError(f"No TheSportsDB lineup returned for event id {event_id}.")
        return {
            "summary": (
                f"TheSportsDB returned {len(rows)} lineup row(s) for event id {event_id}. "
                "This confirms listed lineup data but is not a complete injury/availability feed."
            ),
            "subject": str(event_id),
            "reliability": "medium",
            "raw": {
                "lineup": rows,
                "coverage_note": "Lineup evidence only; verify injuries, withdrawals and expected starters separately when material.",
            },
        }

    def _event_stats(self, metadata: dict) -> dict:
        event_id = metadata.get("event_id")
        if not event_id:
            raise ValueError("TheSportsDB event stats needs metadata.event_id.")
        payload = self.http_get(self._url("lookupeventstats.php"), params={"id": event_id})
        rows = self._list(payload, "eventstats") or self._list(payload, "stats")
        if not rows:
            raise RuntimeError(f"No TheSportsDB event statistics returned for event id {event_id}.")
        return {
            "summary": f"TheSportsDB returned {len(rows)} event-stat row(s) for event id {event_id}.",
            "subject": str(event_id),
            "reliability": "medium",
            "raw": {"stats": rows},
        }

    def _event_results(self, metadata: dict) -> dict:
        event_id = metadata.get("event_id")
        if not event_id:
            raise ValueError("TheSportsDB event results needs metadata.event_id.")
        payload = self.http_get(self._url("eventresults.php"), params={"id": event_id})
        rows = self._list(payload, "results") or self._list(payload, "eventresults")
        if not rows:
            raise RuntimeError(f"No TheSportsDB event results returned for event id {event_id}.")
        return {
            "summary": f"TheSportsDB returned {len(rows)} result row(s) for event id {event_id}.",
            "subject": str(event_id),
            "reliability": "medium",
            "raw": {"results": rows},
        }

    @staticmethod
    def _list(payload: object, key: str) -> list[dict]:
        if not isinstance(payload, dict):
            return []
        value = payload.get(key)
        if value is None:
            return []
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        return []
