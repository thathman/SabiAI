from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import hashlib
from typing import Any, Iterable
from uuid import uuid4
from zoneinfo import ZoneInfo

from sabiai.sources import SourceBundle, SourceRequest, SourceService, default_source_bundle
from sabiai.sources.the_odds import canonical_sport
from sabiai.storage import SabiDatabase
from sabiai.storage.coverage import CoverageStore

from .market_inventory import MarketInventoryNormalizer, expected_market_families, market_family_gap


ESPN_DEFAULTS = {
    "football": {"league": "eng.1", "league_slug": "eng.1", "espn_sport": "soccer"},
    "basketball": {"league": "nba", "league_slug": "nba", "espn_sport": "basketball"},
    "baseball": {"league": "mlb", "league_slug": "mlb", "espn_sport": "baseball"},
    "ice_hockey": {"league": "nhl", "league_slug": "nhl", "espn_sport": "hockey"},
    "american_football": {"league": "nfl", "league_slug": "nfl", "espn_sport": "football"},
}

LONG_HORIZON_SPORTS = {"golf", "motorsport", "cycling"}
EVENT_HORIZON_SPORTS = {"mma", "boxing"}


@dataclass(frozen=True)
class DiscoveryResult:
    run_id: str
    horizon_hours: int
    canonical_events: int
    priced_events: int
    market_catalogue: int
    market_offers: int
    prefiltered_events: int
    source_attempts: int
    source_successes: int
    source_failures: tuple[str, ...]
    details: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "horizon_hours": self.horizon_hours,
            "canonical_events": self.canonical_events,
            "priced_events": self.priced_events,
            "market_catalogue": self.market_catalogue,
            "market_offers": self.market_offers,
            "prefiltered_events": self.prefiltered_events,
            "source_attempts": self.source_attempts,
            "source_successes": self.source_successes,
            "source_failures": list(self.source_failures),
            "details": self.details,
        }


class CoverageDiscoveryEngine:
    """Large deterministic discovery universe; no LLM calls and no wagers.

    Sources are unioned, not treated as mutually exclusive fallbacks. A source that sees only
    one league can contribute those events without preventing another source from adding the
    competitions it can see. Expensive/metered market sensors stay behind explicit settings.
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
        horizon_hours: int | None = None,
        allow_metered: bool | None = None,
    ) -> DiscoveryResult:
        now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        horizon = max(1, int(horizon_hours or getattr(self.settings, "discovery_horizon_hours", 72)))
        sports = list(dict.fromkeys(str(item).strip().casefold() for item in self.settings.research_sports if str(item).strip()))
        max_events = max(100, int(getattr(self.settings, "discovery_max_events", 2000)))
        max_requests = max(10, int(getattr(self.settings, "discovery_max_source_requests", 300)))
        allow_metered = bool(
            getattr(self.settings, "coverage_metered_markets_enabled", False)
            if allow_metered is None else allow_metered
        )
        run_id = f"coverage:{uuid4()}"
        self.store.start_run(run_id, horizon_hours=horizon, sports_requested=len(sports))

        attempts = 0
        successes = 0
        failures: list[str] = []
        raw_events_seen = 0
        canonical_ids: set[str] = set()
        provider_event_counts: defaultdict[tuple[str, str], int] = defaultdict(int)
        zone = self._zone()

        # Union every configured no-cost/calendar source independently. The Odds API and
        # Betfair have their own broad catalogue paths below and are excluded from this loop.
        excluded = {"The Odds API · Discovery", "The Odds API · Markets", "Betfair Exchange · Read Only"}
        for sport in sports:
            sport_horizon = self._horizon_for_sport(sport, horizon)
            end = now + timedelta(hours=sport_horizon)
            days = self._local_days(now, end, zone)
            candidates = [
                source for source in self.bundle.registry.candidates(sport=sport, capability="fixtures", include_paid=False)
                if source.name in self.bundle.fetchers and source.name not in excluded
            ]
            for source in candidates:
                if source.name == "ESPN Public Data" and sport not in ESPN_DEFAULTS:
                    continue
                for day in days:
                    if attempts >= max_requests or len(canonical_ids) >= max_events:
                        break
                    metadata: dict[str, Any] = {"date": day.isoformat()}
                    if source.name == "ESPN Public Data":
                        metadata.update(ESPN_DEFAULTS[sport])
                    attempts += 1
                    try:
                        response = self.service.execute(
                            SourceRequest(
                                request_key=self._key("calendar", source.name, sport, day.isoformat()),
                                capability="fixtures",
                                sport=sport,
                                ttl_seconds=max(900, int(getattr(self.settings, "discovery_source_ttl_seconds", 3600))),
                                metadata=metadata,
                                source_names=(source.name,),
                            ),
                            self.bundle.fetchers,
                            allow_paid=False,
                        )
                        successes += 1
                    except Exception as exc:
                        failures.append(f"{sport} via {source.name} on {day}: {self._safe_error(exc)}")
                        continue
                    rows = list(normalize_source_events(response.payload, sport=sport, source=response.source_name))
                    raw_events_seen += len(rows)
                    for event in rows:
                        if not self._inside_window(event.get("starts_at"), now, end):
                            continue
                        canonical_id = self.store.upsert_event(
                            event,
                            source_name=response.source_name,
                            source_payload=event,
                            now=now,
                        )
                        canonical_ids.add(canonical_id)
                        provider_event_counts[(response.source_name, sport)] += 1
                        self._ingest_embedded(event, canonical_id, response.source_name)
                if attempts >= max_requests or len(canonical_ids) >= max_events:
                    break
            if attempts >= max_requests or len(canonical_ids) >= max_events:
                break

        # Zero-quota The Odds API event discovery can add the leagues/books that our public
        # fixture sources do not expose. Odds themselves remain gated separately.
        provider_sports: dict[str, list[dict[str, Any]]] = defaultdict(list)
        if "The Odds API · Discovery" in self.bundle.fetchers and attempts < max_requests:
            attempts += 1
            try:
                catalog_response = self.service.execute(
                    SourceRequest(
                        request_key=self._key("the-odds-sports"),
                        capability="sport_catalog",
                        ttl_seconds=21600,
                        source_names=("The Odds API · Discovery",),
                    ),
                    self.bundle.fetchers,
                    allow_paid=False,
                )
                successes += 1
                for row in _raw_list(catalog_response.payload, "sports"):
                    sport = canonical_sport(row.get("group"), row.get("title"))
                    if sport in sports and row.get("active", True):
                        provider_sports[sport].append(row)
            except Exception as exc:
                failures.append(f"The Odds API sport catalog: {self._safe_error(exc)}")
            max_leagues = max(1, int(getattr(self.settings, "the_odds_max_leagues_per_sport", 30)))
            for sport in sports:
                sport_end = now + timedelta(hours=self._horizon_for_sport(sport, horizon))
                for provider in provider_sports.get(sport, [])[:max_leagues]:
                    if attempts >= max_requests or len(canonical_ids) >= max_events:
                        break
                    provider_key = str(provider.get("key") or "").strip()
                    if not provider_key:
                        continue
                    attempts += 1
                    try:
                        response = self.service.execute(
                            SourceRequest(
                                request_key=self._key("the-odds-events", provider_key, now.date().isoformat(), sport_end.date().isoformat()),
                                capability="fixtures",
                                sport=sport,
                                ttl_seconds=3600,
                                metadata={
                                    "provider_sport": provider_key,
                                    "commence_time_from": now.isoformat(),
                                    "commence_time_to": sport_end.isoformat(),
                                },
                                source_names=("The Odds API · Discovery",),
                            ),
                            self.bundle.fetchers,
                            allow_paid=False,
                        )
                        successes += 1
                    except Exception as exc:
                        failures.append(f"{sport}/{provider_key} via The Odds API: {self._safe_error(exc)}")
                        continue
                    rows = list(normalize_source_events(response.payload, sport=sport, source=response.source_name, competition=provider.get("title")))
                    raw_events_seen += len(rows)
                    for event in rows:
                        if not self._inside_window(event.get("starts_at"), now, sport_end):
                            continue
                        canonical_id = self.store.upsert_event(
                            event,
                            source_name=response.source_name,
                            provider_sport_key=provider_key,
                            source_payload=event,
                            now=now,
                        )
                        canonical_ids.add(canonical_id)
                        provider_event_counts[(response.source_name, provider_key)] += 1

        # Metered broad winner/handicap/total prices are deliberately a second stage.
        if allow_metered and "The Odds API · Markets" in self.bundle.fetchers:
            metered_limit = max(1, int(getattr(self.settings, "coverage_metered_sport_limit", 12)))
            ranked_provider_keys: list[tuple[int, str, str]] = []
            for sport, rows in provider_sports.items():
                for row in rows:
                    key = str(row.get("key") or "")
                    count = provider_event_counts.get(("The Odds API · Discovery", key), 0)
                    if count:
                        ranked_provider_keys.append((count, sport, key))
            ranked_provider_keys.sort(reverse=True)
            for _count, sport, provider_key in ranked_provider_keys[:metered_limit]:
                if attempts >= max_requests:
                    break
                sport_end = now + timedelta(hours=self._horizon_for_sport(sport, horizon))
                attempts += 1
                try:
                    response = self.service.execute(
                        SourceRequest(
                            request_key=self._key("the-odds-markets", provider_key, now.isoformat(timespec="hours")),
                            capability="odds",
                            sport=sport,
                            ttl_seconds=max(300, int(getattr(self.settings, "market_refresh_seconds", 1800))),
                            metadata={
                                "provider_sport": provider_key,
                                "markets": ("h2h", "spreads", "totals"),
                                "commence_time_from": now.isoformat(),
                                "commence_time_to": sport_end.isoformat(),
                            },
                            source_names=("The Odds API · Markets",),
                        ),
                        self.bundle.fetchers,
                        allow_paid=True,
                        paid_reason="Explicit Sabi Boy coverage-metered market sensor enabled by runtime configuration.",
                    )
                    successes += 1
                except Exception as exc:
                    failures.append(f"{sport}/{provider_key} market sensor: {self._safe_error(exc)}")
                    continue
                for event_payload in _raw_list(response.payload, "events"):
                    event = normalize_single_event(event_payload, sport=sport, source=response.source_name)
                    if not event:
                        continue
                    canonical_id = self.store.upsert_event(
                        event,
                        source_name="The Odds API · Discovery",
                        provider_sport_key=provider_key,
                        source_payload=event_payload,
                        now=now,
                    )
                    canonical_ids.add(canonical_id)
                    self._ingest_the_odds(event_payload, canonical_id, response.source_name)

        # Exchange catalogue discovery is excellent for niche sports and market-type breadth.
        if "Betfair Exchange · Read Only" in self.bundle.fetchers and attempts < max_requests:
            attempts += 1
            event_types: list[dict[str, Any]] = []
            try:
                response = self.service.execute(
                    SourceRequest(
                        request_key=self._key("betfair-event-types"),
                        capability="sport_catalog",
                        ttl_seconds=21600,
                        source_names=("Betfair Exchange · Read Only",),
                    ),
                    self.bundle.fetchers,
                    allow_paid=False,
                )
                successes += 1
                event_types = _raw_list(response.payload, "event_types")
            except Exception as exc:
                failures.append(f"Betfair event types: {self._safe_error(exc)}")
            by_sport: dict[str, list[dict]] = defaultdict(list)
            for row in event_types:
                event_type = row.get("eventType") if isinstance(row.get("eventType"), dict) else row
                sport = canonical_sport(event_type.get("name") if isinstance(event_type, dict) else None)
                if sport in sports:
                    by_sport[sport].append(row)
            max_markets = max(10, min(int(getattr(self.settings, "betfair_max_markets_per_sport", 500)), 1000))
            for sport in sports:
                for item in by_sport.get(sport, [])[:1]:
                    if attempts >= max_requests:
                        break
                    event_type = item.get("eventType") if isinstance(item.get("eventType"), dict) else item
                    event_type_id = event_type.get("id") if isinstance(event_type, dict) else None
                    if not event_type_id:
                        continue
                    sport_end = now + timedelta(hours=self._horizon_for_sport(sport, horizon))
                    attempts += 1
                    try:
                        response = self.service.execute(
                            SourceRequest(
                                request_key=self._key("betfair-markets", event_type_id, now.isoformat(timespec="hours")),
                                capability="odds",
                                sport=sport,
                                ttl_seconds=max(300, int(getattr(self.settings, "market_refresh_seconds", 1800))),
                                metadata={
                                    "event_type_id": str(event_type_id),
                                    "commence_time_from": now.isoformat(),
                                    "commence_time_to": sport_end.isoformat(),
                                    "max_results": max_markets,
                                    "include_prices": bool(getattr(self.settings, "betfair_prices_enabled", True)),
                                },
                                source_names=("Betfair Exchange · Read Only",),
                            ),
                            self.bundle.fetchers,
                            allow_paid=False,
                        )
                        successes += 1
                    except Exception as exc:
                        failures.append(f"{sport} via Betfair: {self._safe_error(exc)}")
                        continue
                    raw = response.payload.get("raw") if isinstance(response.payload, dict) else None
                    raw = raw if isinstance(raw, dict) else {}
                    catalogue = raw.get("catalogue") if isinstance(raw.get("catalogue"), list) else []
                    provider_map: dict[str, str] = {}
                    for market in catalogue:
                        if not isinstance(market, dict):
                            continue
                        event_payload = market.get("event") if isinstance(market.get("event"), dict) else {}
                        event = normalize_single_event(event_payload, sport=sport, source=response.source_name, competition=((market.get("competition") or {}).get("name") if isinstance(market.get("competition"), dict) else None))
                        if not event:
                            continue
                        event["starts_at"] = event.get("starts_at") or market.get("marketStartTime")
                        canonical_id = self.store.upsert_event(event, source_name=response.source_name, source_payload=event_payload, now=now)
                        canonical_ids.add(canonical_id)
                        if event_payload.get("id"):
                            provider_map[str(event_payload["id"])] = canonical_id
                    catalog, offers = MarketInventoryNormalizer(response.source_name).betfair(raw, event_ids=provider_map)
                    self._persist_markets(catalog, offers, provider_map=provider_map)

        if allow_metered and bool(getattr(self.settings, "coverage_deep_markets_enabled", False)):
            attempts, successes = self._deep_market_enrichment(
                now=now,
                attempts=attempts,
                successes=successes,
                max_requests=max_requests,
                failures=failures,
            )

        self.store.prune_offers(keep_days=max(7, int(getattr(self.settings, "market_history_keep_days", 21))))
        current = self.store.current_counts(now=now, horizon_hours=horizon)
        try:
            local_day = now.astimezone(zone).date().isoformat()
            prefiltered = len(
                self.store.research_candidates(
                    local_day,
                    timezone_name=getattr(self.settings, "timezone", "Africa/Lagos"),
                    limit=max(1, int(getattr(self.settings, "prefilter_max_events", 300))),
                )
            )
        except Exception:
            prefiltered = 0
        details = self._coverage_details(now=now, horizon_hours=horizon, sports=sports)
        details["source_failures"] = failures[-100:]
        self.store.finish_run(
            run_id,
            source_attempts=attempts,
            source_successes=successes,
            source_failures=len(failures),
            events_seen=raw_events_seen,
            canonical_events=current["events"],
            priced_events=current["priced_events"],
            market_catalogue_count=current["market_catalogue"],
            market_offer_count=current["market_offers"],
            prefiltered_events=prefiltered,
            details=details,
        )
        return DiscoveryResult(
            run_id=run_id,
            horizon_hours=horizon,
            canonical_events=current["events"],
            priced_events=current["priced_events"],
            market_catalogue=current["market_catalogue"],
            market_offers=current["market_offers"],
            prefiltered_events=prefiltered,
            source_attempts=attempts,
            source_successes=successes,
            source_failures=tuple(failures),
            details=details,
        )

    def _deep_market_enrichment(self, *, now: datetime, attempts: int, successes: int, max_requests: int, failures: list[str]) -> tuple[int, int]:
        if "The Odds API · Markets" not in self.bundle.fetchers:
            return attempts, successes
        event_limit = max(1, int(getattr(self.settings, "coverage_deep_market_event_limit", 20)))
        key_limit = max(1, int(getattr(self.settings, "coverage_deep_market_key_limit", 12)))
        radar = self.store.radar(now=now, horizon_hours=24, limit=event_limit * 3, priced_only=True)
        enriched = 0
        for event in radar:
            if enriched >= event_limit or attempts + 1 >= max_requests:
                break
            source = next((row for row in self.store.event_sources(str(event["id"])) if row.get("source_name") == "The Odds API · Discovery" and row.get("source_event_id") and row.get("provider_sport_key")), None)
            if not source:
                continue
            provider_sport = source["provider_sport_key"]
            provider_event_id = source["source_event_id"]
            attempts += 1
            try:
                keys_response = self.service.execute(
                    SourceRequest(
                        request_key=self._key("the-odds-market-keys", provider_sport, provider_event_id, now.isoformat(timespec="hours")),
                        capability="market_keys",
                        sport=event.get("sport"),
                        ttl_seconds=1800,
                        metadata={"provider_sport": provider_sport, "event_id": provider_event_id},
                        source_names=("The Odds API · Markets",),
                    ),
                    self.bundle.fetchers,
                    allow_paid=True,
                    paid_reason="Explicit deep-market discovery enabled for near-start shortlisted events.",
                )
                successes += 1
            except Exception as exc:
                failures.append(f"deep markets {event.get('event_name')}: {self._safe_error(exc)}")
                continue
            keys = [key for key in _find_market_keys(keys_response.payload) if key not in {"h2h", "spreads", "totals"}][:key_limit]
            if not keys:
                continue
            attempts += 1
            try:
                odds_response = self.service.execute(
                    SourceRequest(
                        request_key=self._key("the-odds-event-odds", provider_sport, provider_event_id, ",".join(keys), now.isoformat(timespec="hours")),
                        capability="event_odds",
                        sport=event.get("sport"),
                        ttl_seconds=900,
                        metadata={"provider_sport": provider_sport, "event_id": provider_event_id, "markets": keys},
                        source_names=("The Odds API · Markets",),
                    ),
                    self.bundle.fetchers,
                    allow_paid=True,
                    paid_reason="Explicit deep-market price enrichment enabled for a near-start event.",
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

    def _ingest_embedded(self, event: dict[str, Any], event_id: str, source_name: str) -> None:
        catalog, offers = MarketInventoryNormalizer(source_name).embedded(event, event_id=event_id)
        for market in catalog:
            self.store.upsert_market(event_id, market)
        for offer in offers:
            self.store.record_offer(event_id, offer)

    def _ingest_the_odds(self, event_payload: dict[str, Any], event_id: str, source_name: str) -> None:
        catalog, offers = MarketInventoryNormalizer(source_name).the_odds_api(event_payload, event_id=event_id)
        for market in catalog:
            self.store.upsert_market(event_id, market)
        for offer in offers:
            self.store.record_offer(event_id, offer)

    def _persist_markets(self, catalog: list[dict], offers: list[dict], *, provider_map: dict[str, str]) -> None:
        # Betfair normalizer carries provider_event_id in metadata. Other normalizers are
        # persisted directly by their event-specific helpers.
        catalogue_ids: dict[tuple[str, str, str], str] = {}
        for market in catalog:
            provider_event_id = str((market.get("metadata") or {}).get("provider_event_id") or "")
            event_id = provider_map.get(provider_event_id)
            if not event_id:
                continue
            catalog_id = self.store.upsert_market(event_id, market)
            catalogue_ids[(event_id, str(market.get("source_market_id") or ""), str(market.get("bookmaker") or ""))] = catalog_id
        for offer in offers:
            provider_event_id = str((offer.get("metadata") or {}).get("provider_event_id") or "")
            event_id = provider_map.get(provider_event_id)
            if not event_id:
                continue
            key = (event_id, str(offer.get("source_market_id") or ""), str(offer.get("bookmaker") or ""))
            if key in catalogue_ids:
                offer["catalogue_id"] = catalogue_ids[key]
            self.store.record_offer(event_id, offer)

    def _coverage_details(self, *, now: datetime, horizon_hours: int, sports: list[str]) -> dict[str, Any]:
        radar = self.store.radar(now=now, horizon_hours=horizon_hours, limit=5000)
        by_sport: dict[str, dict[str, Any]] = {
            sport: {"sport": sport, "events": 0, "priced_events": 0, "market_families": set(), "sources": set()}
            for sport in sports
        }
        for event in radar:
            sport = str(event.get("sport") or "unknown")
            row = by_sport.setdefault(sport, {"sport": sport, "events": 0, "priced_events": 0, "market_families": set(), "sources": set()})
            row["events"] += 1
            inventory = self.store.market_inventory(str(event["id"]), max_age_seconds=max(3600, horizon_hours * 3600))
            if inventory["offers"]:
                row["priced_events"] += 1
            row["market_families"].update(str(item.get("family")) for item in inventory["catalogue"])
            row["sources"].update(str(item.get("source_name")) for item in inventory["sources"])
        output = []
        for sport, row in sorted(by_sport.items()):
            families = sorted(row.pop("market_families"))
            sources = sorted(row.pop("sources"))
            output.append({
                **row,
                "market_families": families,
                "source_count": len(sources),
                "sources": sources,
                "expected_minimum": list(expected_market_families(sport)),
                "missing_minimum": market_family_gap(sport, families),
            })
        return {"sports": output}

    def _horizon_for_sport(self, sport: str, base: int) -> int:
        if sport in EVENT_HORIZON_SPORTS:
            return max(base, int(getattr(self.settings, "discovery_event_horizon_hours", 336)))
        if sport in LONG_HORIZON_SPORTS:
            return max(base, int(getattr(self.settings, "discovery_long_horizon_hours", 168)))
        return base

    def _zone(self):
        try:
            return ZoneInfo(getattr(self.settings, "timezone", "Africa/Lagos"))
        except Exception:
            return timezone.utc

    @staticmethod
    def _local_days(start: datetime, end: datetime, zone) -> list[date]:
        first = start.astimezone(zone).date()
        last = end.astimezone(zone).date()
        days = []
        current = first
        while current <= last:
            days.append(current)
            current += timedelta(days=1)
        return days

    @staticmethod
    def _inside_window(value: object, start: datetime, end: datetime) -> bool:
        parsed = _parse_time(value)
        if parsed is None:
            return False
        return start - timedelta(hours=6) <= parsed <= end

    @staticmethod
    def _key(*parts: object) -> str:
        raw = "|".join(str(item) for item in parts)
        return "coverage:" + hashlib.sha256(raw.encode()).hexdigest()[:28]

    @staticmethod
    def _safe_error(exc: Exception) -> str:
        return f"{type(exc).__name__}: {str(exc)[:280]}"


def normalize_source_events(payload: object, *, sport: str, source: str, competition: str | None = None) -> Iterable[dict[str, Any]]:
    for row in _event_rows(payload):
        event = normalize_single_event(row, sport=sport, source=source, competition=competition)
        if event:
            yield event


def normalize_single_event(row: dict[str, Any], *, sport: str, source: str, competition: str | None = None) -> dict[str, Any] | None:
    if not isinstance(row, dict):
        return None
    # Betfair listEvents wraps the event object.
    if isinstance(row.get("event"), dict) and not any(key in row for key in ("home_team", "strHomeTeam", "homeTeamName", "competitions")):
        outer = row
        row = dict(row["event"])
        row.setdefault("marketCount", outer.get("marketCount"))
    home = _first(row, "strHomeTeam", "homeTeamName", "homeTeam", "home", "home_name", "home_team")
    away = _first(row, "strAwayTeam", "awayTeamName", "awayTeam", "away", "away_name", "away_team")
    competitions = row.get("competitions") if isinstance(row.get("competitions"), list) else []
    if (not home or not away) and competitions and isinstance(competitions[0], dict):
        for competitor in competitions[0].get("competitors") or []:
            if not isinstance(competitor, dict):
                continue
            team = competitor.get("team") if isinstance(competitor.get("team"), dict) else competitor
            label = _first(team, "displayName", "name", "shortName")
            if competitor.get("homeAway") == "home":
                home = home or label
            elif competitor.get("homeAway") == "away":
                away = away or label
    name = _first(row, "strEvent", "name", "shortName", "displayName", "event_name")
    if not name and home and away:
        name = f"{home} vs {away}"
    if not name:
        return None
    starts = _first(row, "strTimestamp", "date", "startTime", "dateEvent", "starts_at", "kickoffTime", "commence_time", "openDate")
    league = competition or _first(row, "strLeague", "tournament", "league", "competition", "category", "sport_title")
    country = _first(row, "strCountry", "country", "countryName", "country_name", "region", "nation", "countryCode")
    division = _first(row, "strDivision", "division", "divisionName", "division_name", "tier", "level", "leagueLevel")
    event_id = _first(row, "idEvent", "eventId", "id", "uid")
    event = {
        "sport": str(sport).casefold(),
        "event": name,
        "home": home,
        "away": away,
        "competition": league,
        "country": country,
        "division": division,
        "starts_at": starts,
        "event_id": event_id,
        "source": source,
    }
    odds = _embedded_odds(row)
    if odds:
        event["odds"] = odds
    return {key: value for key, value in event.items() if value not in (None, "", [])}


def _event_rows(payload: object) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    raw = payload.get("raw")
    if raw is not None:
        found = _event_rows(raw)
        if found:
            return found
    for key in ("events", "event", "results", "data"):
        value = payload.get(key)
        if isinstance(value, list):
            rows = [item for item in value if isinstance(item, dict)]
            if rows:
                return rows
        if isinstance(value, dict):
            found = _event_rows(value)
            if found:
                return found
    return []


def _raw_list(payload: object, key: str) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    raw = payload.get("raw")
    if isinstance(raw, dict) and isinstance(raw.get(key), list):
        return [item for item in raw[key] if isinstance(item, dict)]
    if isinstance(payload.get(key), list):
        return [item for item in payload[key] if isinstance(item, dict)]
    return []


def _embedded_odds(row: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    direct = (
        ("homeOdds", "Home"),
        ("drawOdds", "Draw"),
        ("awayOdds", "Away"),
    )
    for key, label in direct:
        if row.get(key) is None:
            continue
        try:
            price = float(row[key])
        except (TypeError, ValueError):
            continue
        if price > 1:
            result.append({"label": label, "decimal_odds": price, "market": "winner"})
    # Preserve provider market structure when a fixture payload happens to include it.
    for key in ("odds", "markets"):
        value = row.get(key)
        if not isinstance(value, list):
            continue
        for item in value:
            if not isinstance(item, dict):
                continue
            price = item.get("decimal_odds") or item.get("price") or item.get("odd")
            try:
                numeric = float(price)
            except (TypeError, ValueError):
                continue
            if numeric <= 1:
                continue
            result.append({
                "label": item.get("label") or item.get("name") or item.get("selection") or "Selection",
                "decimal_odds": numeric,
                "market": item.get("market") or item.get("market_key"),
                "line": item.get("line") or item.get("point"),
                "period": item.get("period"),
                "participant": item.get("participant") or item.get("description"),
                "bookmaker": item.get("bookmaker"),
                "observed_at": item.get("observed_at") or item.get("last_update"),
            })
    return result


def _find_market_keys(payload: object) -> list[str]:
    found: list[str] = []
    def visit(value: object, *, under_markets: bool = False) -> None:
        if isinstance(value, list):
            for item in value:
                visit(item, under_markets=under_markets)
        elif isinstance(value, dict):
            for key, child in value.items():
                child_under = under_markets or str(key).casefold() in {"markets", "market_keys"}
                if child_under and str(key).casefold() == "key" and isinstance(child, str):
                    found.append(child)
                else:
                    visit(child, under_markets=child_under)
    visit(payload)
    return list(dict.fromkeys(found))


def _first(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = row.get(key)
        if value not in (None, "", []):
            if isinstance(value, dict):
                return value.get("name") or value.get("displayName") or value.get("title")
            return value
    return None


def _parse_time(value: object) -> datetime | None:
    if value is None or not str(value).strip():
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            number = float(value)
            if number > 100_000_000_000:
                number /= 1000
            return datetime.fromtimestamp(number, timezone.utc)
        except (ValueError, OSError, OverflowError):
            return None
    text = str(value).strip()
    if text.isdigit():
        return _parse_time(float(text))
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = datetime.combine(date.fromisoformat(text), datetime.min.time())
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
