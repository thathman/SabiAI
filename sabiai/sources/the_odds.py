from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .http import JsonHttpClient
from .registry import Source, SourceCost, SourceKind
from .service import SourceRequest


HttpGet = Callable[..., object]

GROUP_TO_SPORT = {
    "soccer": "football",
    "football": "football",
    "american football": "american_football",
    "basketball": "basketball",
    "baseball": "baseball",
    "ice hockey": "ice_hockey",
    "hockey": "ice_hockey",
    "tennis": "tennis",
    "table tennis": "table_tennis",
    "cricket": "cricket",
    "rugby league": "rugby_league",
    "rugby union": "rugby",
    "rugby": "rugby",
    "aussie rules": "aussie_rules",
    "golf": "golf",
    "mma": "mma",
    "mixed martial arts": "mma",
    "boxing": "boxing",
    "motorsport": "motorsport",
    "motor sport": "motorsport",
    "cycling": "cycling",
    "darts": "darts",
    "snooker": "snooker",
    "badminton": "badminton",
    "volleyball": "volleyball",
    "handball": "handball",
    "water polo": "water_polo",
    "esports": "esports",
    "horse racing": "horse_racing",
    "greyhounds": "greyhound_racing",
    "greyhound racing": "greyhound_racing",
}


def canonical_sport(group: object, title: object = None) -> str:
    group_key = str(group or "").strip().casefold()
    title_key = str(title or "").strip().casefold()
    if group_key in GROUP_TO_SPORT:
        return GROUP_TO_SPORT[group_key]
    if title_key in GROUP_TO_SPORT:
        return GROUP_TO_SPORT[title_key]
    value = group_key or title_key or "unknown"
    return "_".join(part for part in value.replace("-", " ").split() if part)


@dataclass
class TheOddsApiDiscoveryAdapter:
    """Zero-quota event discovery endpoints from The Odds API v4.

    The provider documents /sports and /sports/{sport}/events as not consuming usage quota.
    Odds are intentionally split into a separate metered adapter so broad discovery cannot
    accidentally burn credits.
    """

    api_key: str
    http_get: HttpGet | None = None

    name = "The Odds API · Discovery"
    base_url = "https://api.the-odds-api.com/v4"

    def __post_init__(self) -> None:
        if not self.api_key.strip():
            raise ValueError("The Odds API discovery adapter needs an API key.")
        if self.http_get is None:
            self.http_get = JsonHttpClient(timeout_seconds=20).get

    @property
    def source(self) -> Source:
        return Source(
            name=self.name,
            kind=SourceKind.PUBLIC_ENDPOINT,
            cost=SourceCost.FREE,
            capabilities={"sport_catalog", "fixtures"},
            priority_bias=12,
            notes=(
                "The Odds API v4 sport/event discovery endpoints. Provider documentation states "
                "these endpoints do not consume odds usage quota. Market/price calls are a separate gated source."
            ),
        )

    def fetch(self, request: SourceRequest) -> object:
        capability = request.capability.strip().casefold()
        metadata = request.metadata or {}
        if capability == "sport_catalog":
            payload = self.http_get(f"{self.base_url}/sports/", params={"apiKey": self.api_key, "all": "true" if metadata.get("all") else None})
            rows = [item for item in payload if isinstance(item, dict)] if isinstance(payload, list) else []
            return {
                "summary": f"The Odds API returned {len(rows)} sport/league keys.",
                "reliability": "high",
                "raw": {"sports": rows, "partial": False, "quota_cost": 0},
            }
        if capability == "fixtures":
            provider_sport = str(metadata.get("provider_sport") or metadata.get("sport_key") or "").strip()
            if not provider_sport:
                raise ValueError("The Odds API fixtures request needs metadata.provider_sport.")
            params = {
                "apiKey": self.api_key,
                "dateFormat": "iso",
                "commenceTimeFrom": metadata.get("commence_time_from"),
                "commenceTimeTo": metadata.get("commence_time_to"),
            }
            payload = self.http_get(f"{self.base_url}/sports/{provider_sport}/events", params=params)
            rows = [item for item in payload if isinstance(item, dict)] if isinstance(payload, list) else []
            return {
                "summary": f"The Odds API returned {len(rows)} event(s) for {provider_sport}.",
                "reliability": "high",
                "raw": {
                    "events": rows,
                    "provider_sport": provider_sport,
                    "partial": False,
                    "quota_cost": 0,
                },
            }
        raise ValueError(f"The Odds API discovery adapter does not implement capability: {request.capability}")


@dataclass
class TheOddsApiMarketsAdapter:
    """Metered odds/market sensor; never a ticket builder.

    The source is marked PAID even when the configured account has free credits because each
    odds request consumes quota. Sabi Boy must explicitly enable metered market coverage.
    """

    api_key: str
    regions: str = "uk,eu"
    http_get: HttpGet | None = None

    name = "The Odds API · Markets"
    base_url = "https://api.the-odds-api.com/v4"

    def __post_init__(self) -> None:
        if not self.api_key.strip():
            raise ValueError("The Odds API markets adapter needs an API key.")
        if self.http_get is None:
            self.http_get = JsonHttpClient(timeout_seconds=25).get

    @property
    def source(self) -> Source:
        return Source(
            name=self.name,
            kind=SourceKind.PAID_API,
            cost=SourceCost.PAID,
            capabilities={"odds", "market_keys", "event_odds"},
            priority_bias=0,
            notes=(
                "Read-only The Odds API v4 market sensor. Calls consume provider quota, so this source "
                "is behind Sabi Boy's explicit metered-source gate even on a free-credit account."
            ),
        )

    def fetch(self, request: SourceRequest) -> object:
        capability = request.capability.strip().casefold()
        metadata = request.metadata or {}
        provider_sport = str(metadata.get("provider_sport") or metadata.get("sport_key") or "").strip()
        if not provider_sport:
            raise ValueError("The Odds API market request needs metadata.provider_sport.")
        base_params = {
            "apiKey": self.api_key,
            "regions": str(metadata.get("regions") or self.regions),
            "dateFormat": "iso",
            "oddsFormat": "decimal",
            "includeLinks": "true",
            "includeSids": "true",
        }
        if capability == "odds":
            markets = metadata.get("markets") or ("h2h", "spreads", "totals")
            market_text = ",".join(str(item) for item in markets) if not isinstance(markets, str) else markets
            params = {
                **base_params,
                "markets": market_text,
                "commenceTimeFrom": metadata.get("commence_time_from"),
                "commenceTimeTo": metadata.get("commence_time_to"),
            }
            payload = self.http_get(f"{self.base_url}/sports/{provider_sport}/odds", params=params)
            rows = [item for item in payload if isinstance(item, dict)] if isinstance(payload, list) else []
            return {
                "summary": f"The Odds API returned market prices for {len(rows)} event(s) in {provider_sport}.",
                "reliability": "high",
                "raw": {"events": rows, "provider_sport": provider_sport, "partial": False},
            }
        event_id = str(metadata.get("event_id") or "").strip()
        if not event_id:
            raise ValueError(f"The Odds API {capability} request needs metadata.event_id.")
        if capability == "market_keys":
            payload = self.http_get(
                f"{self.base_url}/sports/{provider_sport}/events/{event_id}/markets",
                params={key: value for key, value in base_params.items() if key not in {"oddsFormat", "includeLinks", "includeSids"}},
            )
            return {
                "summary": f"The Odds API returned recently observed market keys for event {event_id}.",
                "reliability": "high",
                "raw": {"market_keys": payload, "provider_sport": provider_sport, "event_id": event_id, "partial": True},
            }
        if capability == "event_odds":
            markets = metadata.get("markets")
            if not markets:
                raise ValueError("The Odds API event_odds request needs metadata.markets.")
            market_text = ",".join(str(item) for item in markets) if not isinstance(markets, str) else markets
            payload = self.http_get(
                f"{self.base_url}/sports/{provider_sport}/events/{event_id}/odds",
                params={**base_params, "markets": market_text},
            )
            if not isinstance(payload, dict):
                raise RuntimeError("The Odds API event odds endpoint returned an invalid payload.")
            return {
                "summary": f"The Odds API returned deep market prices for event {event_id}.",
                "reliability": "high",
                "raw": {"event": payload, "provider_sport": provider_sport, "partial": False},
            }
        raise ValueError(f"The Odds API markets adapter does not implement capability: {request.capability}")
