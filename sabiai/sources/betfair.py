from __future__ import annotations

from dataclasses import dataclass
from itertools import islice
from typing import Callable, Iterable

from .http import JsonHttpClient
from .registry import Source, SourceCost, SourceKind
from .service import SourceRequest


HttpPost = Callable[..., object]


def _chunks(values: list[str], size: int) -> Iterable[list[str]]:
    iterator = iter(values)
    while True:
        batch = list(islice(iterator, size))
        if not batch:
            return
        yield batch


@dataclass
class BetfairExchangeAdapter:
    """Strictly read-only Betfair Exchange market-discovery sensor.

    Only catalogue/price read operations are implemented. There is deliberately no order,
    account-funds or betting mutation method in this adapter.
    """

    app_key: str
    session_token: str
    http_post: HttpPost | None = None
    endpoint: str = "https://api.betfair.com/exchange/betting/json-rpc/v1"

    name = "Betfair Exchange · Read Only"

    def __post_init__(self) -> None:
        if not self.app_key.strip() or not self.session_token.strip():
            raise ValueError("Betfair read-only adapter needs app_key and session_token.")
        if self.http_post is None:
            self.http_post = JsonHttpClient(timeout_seconds=25).post

    @property
    def source(self) -> Source:
        return Source(
            name=self.name,
            kind=SourceKind.PUBLIC_ENDPOINT,
            cost=SourceCost.FREE,
            capabilities={"sport_catalog", "fixtures", "markets", "odds"},
            priority_bias=18,
            notes=(
                "Read-only Betfair Exchange Betting API catalogue and best-back prices. "
                "No placeOrders/replaceOrders/cancelOrders capability exists in Sabi Boy."
            ),
        )

    def fetch(self, request: SourceRequest) -> object:
        capability = request.capability.strip().casefold()
        metadata = request.metadata or {}
        if capability == "sport_catalog":
            rows = self._rpc("listEventTypes", {"filter": {}})
            return {
                "summary": f"Betfair returned {len(rows) if isinstance(rows, list) else 0} event type(s).",
                "reliability": "high",
                "raw": {"event_types": rows if isinstance(rows, list) else [], "partial": False},
            }
        market_filter = self._market_filter(metadata)
        if capability == "fixtures":
            rows = self._rpc("listEvents", {"filter": market_filter})
            return {
                "summary": f"Betfair returned {len(rows) if isinstance(rows, list) else 0} event(s).",
                "reliability": "high",
                "raw": {"events": rows if isinstance(rows, list) else [], "partial": False},
            }
        if capability in {"markets", "odds"}:
            max_results = max(1, min(int(metadata.get("max_results") or 500), 1000))
            catalogue = self._rpc(
                "listMarketCatalogue",
                {
                    "filter": market_filter,
                    "marketProjection": [
                        "EVENT", "EVENT_TYPE", "COMPETITION", "MARKET_START_TIME",
                        "MARKET_DESCRIPTION", "RUNNER_DESCRIPTION",
                    ],
                    "sort": "FIRST_TO_START",
                    "maxResults": max_results,
                },
            )
            catalogue = catalogue if isinstance(catalogue, list) else []
            books: list[dict] = []
            if capability == "odds" or bool(metadata.get("include_prices")):
                market_ids = [str(row.get("marketId")) for row in catalogue if isinstance(row, dict) and row.get("marketId")]
                # EX_BEST_OFFERS has request weight 5. Forty markets keeps each call at the
                # documented 200-point market-data request ceiling.
                for batch in _chunks(market_ids, 40):
                    result = self._rpc(
                        "listMarketBook",
                        {
                            "marketIds": batch,
                            "priceProjection": {
                                "priceData": ["EX_BEST_OFFERS"],
                                "exBestOffersOverrides": {"bestPricesDepth": 1},
                            },
                        },
                    )
                    if isinstance(result, list):
                        books.extend(item for item in result if isinstance(item, dict))
            return {
                "summary": f"Betfair returned {len(catalogue)} market catalogue row(s) and {len(books)} price book(s).",
                "reliability": "high",
                "raw": {"catalogue": catalogue, "books": books, "partial": len(catalogue) >= max_results},
            }
        raise ValueError(f"Betfair read-only adapter does not implement capability: {request.capability}")

    def _rpc(self, method: str, params: dict) -> object:
        response = self.http_post(
            self.endpoint,
            payload={
                "jsonrpc": "2.0",
                "method": f"SportsAPING/v1.0/{method}",
                "params": params,
                "id": 1,
            },
            headers={
                "X-Application": self.app_key,
                "X-Authentication": self.session_token,
            },
        )
        if not isinstance(response, dict):
            raise RuntimeError(f"Betfair {method} returned an invalid response.")
        if response.get("error"):
            error = response["error"]
            message = error.get("message") if isinstance(error, dict) else str(error)
            raise RuntimeError(f"Betfair {method} failed: {message}")
        return response.get("result")

    @staticmethod
    def _market_filter(metadata: dict) -> dict:
        market_filter: dict = {}
        event_type_id = metadata.get("event_type_id")
        if event_type_id:
            market_filter["eventTypeIds"] = [str(event_type_id)]
        event_ids = metadata.get("event_ids") or ([] if not metadata.get("event_id") else [metadata.get("event_id")])
        if event_ids:
            market_filter["eventIds"] = [str(value) for value in event_ids]
        competition_ids = metadata.get("competition_ids")
        if competition_ids:
            market_filter["competitionIds"] = [str(value) for value in competition_ids]
        market_types = metadata.get("market_type_codes")
        if market_types:
            market_filter["marketTypeCodes"] = [str(value) for value in market_types]
        start = metadata.get("commence_time_from")
        end = metadata.get("commence_time_to")
        if start or end:
            market_filter["marketStartTime"] = {
                key: value
                for key, value in {"from": start, "to": end}.items()
                if value
            }
        return market_filter
