from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Callable, Mapping

from .http import JsonHttpClient
from .registry import Source, SourceCost, SourceKind
from .service import SourceRequest


HttpPost = Callable[..., object]
SAFE_PATH_PART = re.compile(r"^[A-Za-z0-9_-]{2,100}$")
INTERNAL_METADATA = {
    "coalesce_wait_seconds",
    "parse_endpoint",
    "provider_sport",
    "require_complete",
}


@dataclass
class ParseBotAdapter:
    """Call one configured Parse scraper through a fixed, allowlisted endpoint set."""

    name: str
    api_key: str
    scraper_id: str
    endpoints: Mapping[str, str]
    sports: set[str] = field(default_factory=set)
    notes: str | None = None
    priority_bias: int = 25
    http_post: HttpPost | None = None

    base_url = "https://api.parse.bot/scraper"

    def __post_init__(self) -> None:
        if not self.api_key.strip():
            raise ValueError("Parse adapter needs an API key.")
        if not SAFE_PATH_PART.fullmatch(self.scraper_id):
            raise ValueError("Parse scraper ID contains unsupported characters.")
        if not self.endpoints:
            raise ValueError("Parse adapter needs at least one endpoint mapping.")
        if any(not SAFE_PATH_PART.fullmatch(endpoint) for endpoint in self.endpoints.values()):
            raise ValueError("Parse endpoint mapping contains unsupported characters.")
        if self.http_post is None:
            self.http_post = JsonHttpClient(timeout_seconds=25).post

    @property
    def allowed_endpoints(self) -> frozenset[str]:
        return frozenset(self.endpoints.values())

    @property
    def source(self) -> Source:
        capabilities = {key.split(":", 1)[0] for key in self.endpoints}
        return Source(
            name=self.name,
            kind=SourceKind.PUBLIC_ENDPOINT,
            cost=SourceCost.FREE,
            sports=set(self.sports),
            capabilities=capabilities,
            priority_bias=self.priority_bias,
            notes=self.notes
            or "Configured Parse API using free account credits. Endpoint calls are fixed and allowlisted.",
        )

    def fetch(self, request: SourceRequest) -> object:
        capability = request.capability.strip().casefold()
        sport = (request.sport or "").strip().casefold().replace(" ", "_")
        endpoint = self.endpoints.get(f"{capability}:{sport}") or self.endpoints.get(capability)
        if endpoint is None:
            raise ValueError(f"{self.name} does not implement capability: {request.capability}")

        metadata = dict(request.metadata or {})
        payload = {
            str(key): value
            for key, value in metadata.items()
            if key not in INTERNAL_METADATA and value is not None
        }
        response = self.http_post(
            f"{self.base_url}/{self.scraper_id}/{endpoint}",
            payload=payload,
            headers={"X-API-Key": self.api_key},
        )
        if not isinstance(response, dict):
            raise RuntimeError(f"{self.name} returned an invalid response.")
        state = str(response.get("status") or "success").casefold()
        if state not in {"success", "ok"}:
            raise RuntimeError(f"{self.name} endpoint {endpoint} returned {state}.")
        data = response.get("data")
        if data is None:
            raise RuntimeError(f"{self.name} endpoint {endpoint} returned no data.")
        return {
            "summary": f"{self.name} returned data from {endpoint}.",
            "reliability": "medium",
            "raw": {
                "data": data,
                "endpoint": endpoint,
                "execution_time": response.get("execution_time"),
                "partial": False,
            },
        }


@dataclass
class SportsBettingAnalyzerAdapter:
    """Read suggested picks from the configured analyzer API; never performs betting actions."""

    api_key: str
    http_post: HttpPost | None = None

    name = "Sports Betting AI Analyzer"
    endpoint = "https://sportsbettingaianalyzer.com/api/picks/suggested"

    def __post_init__(self) -> None:
        if not self.api_key.strip():
            raise ValueError("Sports Betting AI Analyzer needs an API key.")
        if self.http_post is None:
            self.http_post = JsonHttpClient(timeout_seconds=20).post

    @property
    def source(self) -> Source:
        return Source(
            name=self.name,
            kind=SourceKind.PUBLIC_ENDPOINT,
            cost=SourceCost.FREE,
            capabilities={"suggested_picks"},
            priority_bias=45,
            notes=(
                "Configured read-only suggested-picks API. Treat its output as one opinion to verify "
                "against event facts and fresh bookmaker prices."
            ),
        )

    def fetch(self, request: SourceRequest) -> object:
        if request.capability.strip().casefold() != "suggested_picks":
            raise ValueError(f"{self.name} does not implement capability: {request.capability}")
        sport = str((request.metadata or {}).get("provider_sport") or request.sport or "").strip()
        if not sport:
            raise ValueError("Sports Betting AI Analyzer request needs a sport.")
        response = self.http_post(
            self.endpoint,
            payload={"sport": sport},
            headers={"X-API-Key": self.api_key},
        )
        if not isinstance(response, dict):
            raise RuntimeError(f"{self.name} returned an invalid response.")
        return {
            "summary": f"{self.name} returned suggested picks for {sport}.",
            "reliability": "unverified",
            "raw": {"data": response, "partial": False},
        }
