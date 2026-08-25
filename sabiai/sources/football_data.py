from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .http import JsonHttpClient
from .registry import Source, SourceCost, SourceKind
from .service import SourceRequest


HttpGet = Callable[..., object]


@dataclass
class FootballDataAdapter:
    """Optional football-data.org v4 adapter.

    This is still a free source when a free-plan token is configured, but it is metered.
    TheSportsDB and cached/public data can therefore be preferred ahead of it.
    """

    token: str
    http_get: HttpGet | None = None

    name = "football-data.org"
    base_url = "https://api.football-data.org/v4"

    def __post_init__(self) -> None:
        if not self.token or not self.token.strip():
            raise ValueError("football-data.org adapter requires a token.")
        self.token = self.token.strip()
        if self.http_get is None:
            self.http_get = JsonHttpClient().get

    @property
    def source(self) -> Source:
        return Source(
            name=self.name,
            kind=SourceKind.PUBLIC_ENDPOINT,
            cost=SourceCost.FREE,
            sports={"football"},
            capabilities={"fixtures", "results", "team_matches", "standings"},
            priority_bias=5,
            notes=(
                "football-data.org v4 free-plan endpoint. Uses a configured free token and is rate limited; "
                "do not spend calls when cache or an unmetered public source already answers the question."
            ),
        )

    def fetch(self, request: SourceRequest) -> object:
        capability = request.capability.strip().casefold()
        metadata = request.metadata or {}
        if capability == "fixtures":
            return self._matches(metadata, default_status=None)
        if capability == "results":
            return self._matches(metadata, default_status="FINISHED")
        if capability == "team_matches":
            return self._team_matches(metadata)
        if capability == "standings":
            return self._standings(metadata)
        raise ValueError(f"football-data.org does not implement capability: {request.capability}")

    @property
    def _headers(self) -> dict[str, str]:
        return {"X-Auth-Token": self.token}

    def _matches(self, metadata: dict, *, default_status: str | None) -> dict:
        params = {
            "dateFrom": metadata.get("date_from") or metadata.get("date"),
            "dateTo": metadata.get("date_to") or metadata.get("date"),
            "status": metadata.get("status") or default_status,
            "competitions": metadata.get("competitions") or metadata.get("competition"),
        }
        payload = self.http_get(
            f"{self.base_url}/matches",
            params=params,
            headers=self._headers,
        )
        matches = payload.get("matches", []) if isinstance(payload, dict) else []
        matches = [item for item in matches if isinstance(item, dict)]
        status_text = params.get("status") or "requested"
        return {
            "summary": f"football-data.org returned {len(matches)} {status_text.lower()} football match(es).",
            "reliability": "high",
            "raw": {"matches": matches, "filters": params},
        }

    def _team_matches(self, metadata: dict) -> dict:
        team_id = metadata.get("team_id")
        if not team_id:
            raise ValueError("football-data.org team matches needs metadata.team_id.")
        params = {
            "dateFrom": metadata.get("date_from"),
            "dateTo": metadata.get("date_to"),
            "season": metadata.get("season"),
            "competitions": metadata.get("competitions") or metadata.get("competition"),
            "status": metadata.get("status"),
            "venue": metadata.get("venue"),
            "limit": metadata.get("limit"),
        }
        payload = self.http_get(
            f"{self.base_url}/teams/{team_id}/matches",
            params=params,
            headers=self._headers,
        )
        matches = payload.get("matches", []) if isinstance(payload, dict) else []
        matches = [item for item in matches if isinstance(item, dict)]
        return {
            "summary": f"football-data.org returned {len(matches)} match(es) for team id {team_id}.",
            "subject": str(team_id),
            "reliability": "high",
            "raw": {"matches": matches, "filters": params},
        }

    def _standings(self, metadata: dict) -> dict:
        competition = metadata.get("competition") or metadata.get("competition_id")
        if not competition:
            raise ValueError("football-data.org standings needs metadata.competition or competition_id.")
        params = {
            "season": metadata.get("season"),
            "matchday": metadata.get("matchday"),
        }
        payload = self.http_get(
            f"{self.base_url}/competitions/{competition}/standings",
            params=params,
            headers=self._headers,
        )
        standings = payload.get("standings", []) if isinstance(payload, dict) else []
        standings = [item for item in standings if isinstance(item, dict)]
        return {
            "summary": f"football-data.org returned {len(standings)} standings section(s) for {competition}.",
            "subject": str(competition),
            "reliability": "high",
            "raw": {"standings": standings},
        }
