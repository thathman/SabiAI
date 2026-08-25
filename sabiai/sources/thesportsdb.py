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

    The free API has endpoint-specific result limits. The adapter keeps that limitation in
    its summaries/raw metadata so Sabi Boy does not mistake a partial feed for complete form.
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
                "team_profile",
                "player_profile",
                "player_stats",
                "league_table",
            },
            priority_bias=0,
            notes=(
                "Documented TheSportsDB v1 free API. Free endpoints are rate/result limited; "
                "use as one evidence source, not as a complete injury/lineup feed."
            ),
        )

    def fetch(self, request: SourceRequest) -> object:
        capability = request.capability.strip().casefold()
        metadata = request.metadata or {}
        if capability == "fixtures":
            return self._fixtures(request)
        if capability == "event_search":
            return self._event_search(metadata)
        if capability == "team_profile":
            return self._team_profile(metadata)
        if capability == "player_profile":
            return self._player_profile(metadata)
        if capability == "player_stats":
            return self._player_stats(metadata)
        if capability == "league_table":
            return self._league_table(metadata)
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
                "coverage_note": "TheSportsDB free Schedule Day endpoint has a documented per-request result limit.",
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
                "coverage_note": "TheSportsDB free event search has a documented result limit.",
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
