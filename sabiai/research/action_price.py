from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
import hashlib
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from sabiai.sources import SourceBundle, SourceRequest, SourceService, default_source_bundle
from sabiai.storage import CoverageStore, SabiDatabase

from .discovery import normalize_source_events
from .market_inventory import MarketInventoryNormalizer


# These are the SportyBet Parse routes that have been verified in the controlled
# runtime. Do not broaden this list without testing the provider route first.
SPORTYBET_PARSE_SPORTS = ("football", "basketball", "ice_hockey")
SPORTYBET_SOURCE = "Parse · SportyBet"


@dataclass(frozen=True)
class ActionPriceRefreshResult:
    """Observable result of one no-model SportyBet action-price refresh."""

    scan_date: str
    sports_requested: tuple[str, ...]
    source_attempts: int
    source_successes: int
    events_seen: int
    events_persisted: int
    priced_events: int
    market_catalogue: int
    market_offers: int
    source_failures: tuple[str, ...] = ()
    disabled: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "scan_date": self.scan_date,
            "sports_requested": list(self.sports_requested),
            "source_attempts": self.source_attempts,
            "source_successes": self.source_successes,
            "events_seen": self.events_seen,
            "events_persisted": self.events_persisted,
            "priced_events": self.priced_events,
            "market_catalogue": self.market_catalogue,
            "market_offers": self.market_offers,
            "source_failures": list(self.source_failures),
            "disabled": self.disabled,
        }


class ActionPriceEnricher:
    """Persist the complete eligible SportyBet slate for a research cycle.

    This is deliberately deterministic and model-free. It uses one explicit Parse
    request per verified SportyBet sport, then normalizes and stores every returned
    event and embedded action-book offer up to an explicit safety limit. The source
    request key matches the daily fixture collector so a same-cycle collector call
    and enrichment pass reuse the same cached response instead of spending another
    Parse credit.
    """

    def __init__(self, settings, database: SabiDatabase, bundle: SourceBundle | None = None):
        self.settings = settings
        self.database = database
        self.database.initialize()
        self.bundle = bundle or default_source_bundle(settings)
        self.service = SourceService(database, self.bundle.registry)
        self.store = CoverageStore(database)

    def refresh(
        self,
        *,
        now: datetime | None = None,
        scan_date: str | None = None,
        sports: Iterable[str] | None = None,
    ) -> ActionPriceRefreshResult:
        now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        day = scan_date or self._local_date(now)
        requested = self._sports(sports)
        if not bool(getattr(self.settings, "action_price_enrichment_enabled", True)):
            return ActionPriceRefreshResult(
                scan_date=day,
                sports_requested=requested,
                source_attempts=0,
                source_successes=0,
                events_seen=0,
                events_persisted=0,
                priced_events=0,
                market_catalogue=0,
                market_offers=0,
                disabled=True,
            )
        if SPORTYBET_SOURCE not in self.bundle.fetchers:
            return ActionPriceRefreshResult(
                scan_date=day,
                sports_requested=requested,
                source_attempts=0,
                source_successes=0,
                events_seen=0,
                events_persisted=0,
                priced_events=0,
                market_catalogue=0,
                market_offers=0,
                source_failures=("Parse · SportyBet is not configured; action-price enrichment skipped.",),
            )

        max_events = max(1, int(getattr(self.settings, "action_price_max_events_per_sport", 1000)))
        attempts = successes = events_seen = events_persisted = priced_events = 0
        market_catalogue = market_offers = 0
        failures: list[str] = []
        for sport in requested:
            request = SourceRequest(
                request_key=self._request_key(sport, day),
                capability="fixtures",
                sport=sport,
                ttl_seconds=max(300, int(getattr(self.settings, "market_refresh_seconds", 1800))),
                metadata={"date": day, "sport": sport},
                source_names=(SPORTYBET_SOURCE,),
            )
            attempts += 1
            try:
                response = self.service.execute(
                    request,
                    self.bundle.fetchers,
                    allow_paid=False,
                )
                successes += 1
                failures.extend(str(item) for item in (response.failures or ()))
            except Exception as exc:
                failures.append(f"{sport} via {SPORTYBET_SOURCE}: {self._safe_error(exc)}")
                continue

            rows = list(normalize_source_events(response.payload, sport=sport, source=SPORTYBET_SOURCE))
            events_seen += len(rows)
            accepted = 0
            for event in rows:
                if accepted >= max_events:
                    break
                if self._local_date(event.get("starts_at")) != day:
                    continue
                event.setdefault("competition", "Unresolved")
                event.setdefault("country", "Unresolved")
                event.setdefault("division", "Unresolved")
                try:
                    event_id = self.store.upsert_event(
                        event,
                        source_name=SPORTYBET_SOURCE,
                        provider_sport_key=sport,
                        source_payload=event,
                        now=now,
                    )
                except Exception as exc:
                    failures.append(f"{sport} event persistence: {self._safe_error(exc)}")
                    continue
                events_persisted += 1
                accepted += 1
                catalog, offers = MarketInventoryNormalizer(SPORTYBET_SOURCE).embedded(
                    event,
                    event_id=event_id,
                )
                for market in catalog:
                    try:
                        self.store.upsert_market(event_id, market)
                        market_catalogue += 1
                    except Exception as exc:
                        failures.append(f"{sport} market persistence: {self._safe_error(exc)}")
                offer_count = 0
                for offer in offers:
                    try:
                        self.store.record_offer(event_id, offer)
                        market_offers += 1
                        offer_count += 1
                    except Exception as exc:
                        failures.append(f"{sport} price persistence: {self._safe_error(exc)}")
                if offer_count:
                    priced_events += 1

        return ActionPriceRefreshResult(
            scan_date=day,
            sports_requested=requested,
            source_attempts=attempts,
            source_successes=successes,
            events_seen=events_seen,
            events_persisted=events_persisted,
            priced_events=priced_events,
            market_catalogue=market_catalogue,
            market_offers=market_offers,
            source_failures=tuple(failures[-100:]),
        )

    def _sports(self, sports: Iterable[str] | None) -> tuple[str, ...]:
        configured = sports if sports is not None else getattr(self.settings, "research_sports", ())
        allowed = {item.casefold() for item in SPORTYBET_PARSE_SPORTS}
        normalized: list[str] = []
        for item in configured:
            value = str(item).strip().casefold().replace(" ", "_")
            if value == "soccer":
                value = "football"
            if value in allowed and value not in normalized:
                normalized.append(value)
        return tuple(normalized)

    def _local_date(self, value: object) -> str | None:
        if value is None or not str(value).strip():
            return None
        try:
            zone = ZoneInfo(getattr(self.settings, "timezone", "Africa/Lagos"))
        except Exception:
            zone = timezone.utc
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            try:
                epoch = float(value)
                if epoch > 100_000_000_000:
                    epoch /= 1000
                return datetime.fromtimestamp(epoch, timezone.utc).astimezone(zone).date().isoformat()
            except (OverflowError, OSError, ValueError):
                return None
        text = str(value).strip()
        if text.isdigit():
            return self._local_date(float(text))
        try:
            if len(text) == 10:
                return date.fromisoformat(text).isoformat()
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(zone).date().isoformat()

    @staticmethod
    def _request_key(sport: str, day: str) -> str:
        digest = hashlib.sha256(
            f"daily-fixtures|fixtures|{sport}|{day}|{SPORTYBET_SOURCE}".encode()
        ).hexdigest()[:24]
        return f"daily-fixtures:{digest}"

    @staticmethod
    def _safe_error(exc: Exception) -> str:
        return f"{type(exc).__name__}: {str(exc)[:280]}"


__all__ = ["ActionPriceEnricher", "ActionPriceRefreshResult", "SPORTYBET_PARSE_SPORTS"]
