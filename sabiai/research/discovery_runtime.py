from __future__ import annotations

from datetime import datetime

from sabiai.sources import SourceBundle, SourceRequest
from sabiai.storage import CoverageStore, SabiDatabase

from .discovery import (
    CoverageDiscoveryEngine as BaseCoverageDiscoveryEngine,
    DiscoveryResult,
    _find_market_keys,
)
from .market_refresh import MarketRefreshPolicy


class CoverageDiscoveryEngine(BaseCoverageDiscoveryEngine):
    """Runtime V2.4 discovery engine with hardened identity and tiered deep refresh."""

    def __init__(self, settings, database: SabiDatabase, bundle: SourceBundle | None = None):
        super().__init__(settings, database, bundle=bundle)
        self.store = CoverageStore(database)

    def _deep_market_enrichment(
        self,
        *,
        now: datetime,
        attempts: int,
        successes: int,
        max_requests: int,
        failures: list[str],
    ) -> tuple[int, int]:
        if "The Odds API · Markets" not in self.bundle.fetchers:
            return attempts, successes
        event_limit = max(1, int(getattr(self.settings, "coverage_deep_market_event_limit", 20)))
        key_limit = max(1, int(getattr(self.settings, "coverage_deep_market_key_limit", 12)))
        radar = self.store.radar(now=now, horizon_hours=24, limit=event_limit * 6, priced_only=True)
        enriched = 0
        for event in radar:
            if enriched >= event_limit or attempts + 1 >= max_requests:
                break
            bucket = MarketRefreshPolicy.bucket(event.get("starts_at"), now=now)
            tier = MarketRefreshPolicy.tier(event.get("starts_at"), now=now)
            if bucket is None or tier is None:
                continue
            source = next(
                (
                    row
                    for row in self.store.event_sources(str(event["id"]))
                    if row.get("source_name") == "The Odds API · Discovery"
                    and row.get("source_event_id")
                    and row.get("provider_sport_key")
                ),
                None,
            )
            if not source:
                continue
            provider_sport = source["provider_sport_key"]
            provider_event_id = source["source_event_id"]
            attempts += 1
            try:
                keys_response = self.service.execute(
                    SourceRequest(
                        request_key=self._key(
                            "the-odds-market-keys",
                            provider_sport,
                            provider_event_id,
                            bucket,
                        ),
                        capability="market_keys",
                        sport=event.get("sport"),
                        ttl_seconds=tier.interval_seconds,
                        metadata={
                            "provider_sport": provider_sport,
                            "event_id": provider_event_id,
                            "refresh_tier": tier.name,
                        },
                        source_names=("The Odds API · Markets",),
                    ),
                    self.bundle.fetchers,
                    allow_paid=True,
                    paid_reason=f"Explicit V2.4 deep-market discovery enabled at {tier.name} refresh tier.",
                )
                successes += 1
            except Exception as exc:
                failures.append(f"deep markets {event.get('event_name')}: {self._safe_error(exc)}")
                continue
            keys = [
                key
                for key in _find_market_keys(keys_response.payload)
                if key not in {"h2h", "spreads", "totals"}
            ][:key_limit]
            if not keys:
                continue
            attempts += 1
            try:
                odds_response = self.service.execute(
                    SourceRequest(
                        request_key=self._key(
                            "the-odds-event-odds",
                            provider_sport,
                            provider_event_id,
                            ",".join(keys),
                            bucket,
                        ),
                        capability="event_odds",
                        sport=event.get("sport"),
                        ttl_seconds=tier.interval_seconds,
                        metadata={
                            "provider_sport": provider_sport,
                            "event_id": provider_event_id,
                            "markets": keys,
                            "refresh_tier": tier.name,
                        },
                        source_names=("The Odds API · Markets",),
                    ),
                    self.bundle.fetchers,
                    allow_paid=True,
                    paid_reason=f"Explicit V2.4 deep-market price enrichment enabled at {tier.name} refresh tier.",
                )
                successes += 1
            except Exception as exc:
                failures.append(f"deep prices {event.get('event_name')}: {self._safe_error(exc)}")
                continue
            raw = odds_response.payload.get("raw") if isinstance(odds_response.payload, dict) else None
            event_payload = raw.get("event") if isinstance(raw, dict) and isinstance(raw.get("event"), dict) else None
            if event_payload:
                self._ingest_the_odds(event_payload, str(event["id"]), odds_response.source_name)
                enriched += 1
        return attempts, successes


__all__ = ["CoverageDiscoveryEngine", "DiscoveryResult"]
