"""Approved V2.5 source-expansion adapters.

The adapters in this module deliberately share the small ``SourceRequest`` contract used by
the existing cache/economy layer.  They do not place wagers and they never put credentials in
URLs or returned payloads.  Optional providers are represented in the catalogue even when they
are not configured, so the dashboard can distinguish ``disabled``/``not_configured`` from an
unknown source.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
import importlib
import json
from pathlib import Path
import re
from typing import Any, Callable, Mapping

from .http import JsonHttpClient
from .registry import Source, SourceCost, SourceKind
from .service import SourceRequest


HttpGet = Callable[..., object]
_SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9_.-]{1,120}$")


def _client(http_get: HttpGet | None, *, timeout: int = 20) -> HttpGet:
    return http_get or JsonHttpClient(timeout_seconds=timeout).get


def _clean_params(values: Mapping[str, object]) -> dict[str, object]:
    return {str(key): value for key, value in values.items() if value not in (None, "", [])}


def _segment(value: object, label: str) -> str:
    text = str(value or "").strip()
    if not text or not _SAFE_SEGMENT.fullmatch(text):
        raise ValueError(f"{label} contains unsupported path characters.")
    return text


def _rows(payload: object) -> list[dict[str, Any]]:
    """Extract a provider list without assuming every API uses the same envelope."""
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("response", "data", "events", "matches", "races", "results", "items"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            nested = _rows(value)
            if nested:
                return nested
    mrdata = payload.get("MRData")
    if isinstance(mrdata, dict):
        return _rows(mrdata)
    for value in payload.values():
        if isinstance(value, (dict, list)):
            nested = _rows(value)
            if nested:
                return nested
    return []


def _configured_source(
    *,
    name: str,
    kind: SourceKind,
    cost: SourceCost,
    sports: set[str],
    capabilities: set[str],
    configured: bool,
    notes: str,
    priority_bias: int = 0,
    request_budget_per_day: int | None = None,
    object_budget_per_month: int | None = None,
) -> Source:
    return Source(
        name=name,
        kind=kind,
        cost=cost,
        sports=sports,
        capabilities=capabilities,
        enabled=bool(configured),
        health="unknown" if configured else "not_configured",
        notes=notes,
        priority_bias=priority_bias,
        request_budget_per_day=request_budget_per_day,
        object_budget_per_month=object_budget_per_month,
    )


def _result(name: str, rows: list[dict[str, Any]], payload: object, *, reliability: str, **extra: Any) -> dict[str, Any]:
    return {
        "summary": f"{name} returned {len(rows)} record(s).",
        "reliability": reliability,
        **extra,
        "raw": {"events": rows, "provider_payload": payload, "partial": False},
    }


def _first(value: object, *keys: str) -> object | None:
    if not isinstance(value, dict):
        return None
    for key in keys:
        item = value.get(key)
        if item not in (None, "", []):
            if isinstance(item, dict):
                return item.get("name") or item.get("displayName") or item.get("title") or item.get("common_name")
            return item
    return None


def _american_to_decimal(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number < 0:
        return round(1 + 100 / abs(number), 6)
    if number >= 100:
        return round(1 + number / 100, 6)
    if number > 1:
        return round(number, 6)
    return None


@dataclass
class ApiSportsAdapter:
    """API-Sports family adapter using the documented ``x-apisports-key`` header."""

    api_key: str
    http_get: HttpGet | None = None
    name = "API-Sports"

    _routes = {
        "football": ("https://v3.football.api-sports.io", "fixtures"),
        "basketball": ("https://v1.basketball.api-sports.io", "games"),
        "baseball": ("https://v1.baseball.api-sports.io", "games"),
        "ice_hockey": ("https://v1.hockey.api-sports.io", "games"),
        "hockey": ("https://v1.hockey.api-sports.io", "games"),
        "volleyball": ("https://v1.volleyball.api-sports.io", "games"),
        "handball": ("https://v1.handball.api-sports.io", "games"),
        "rugby": ("https://v1.rugby.api-sports.io", "games"),
        "mma": ("https://v1.mma.api-sports.io", "fights"),
        "motorsport": ("https://v1.formula-1.api-sports.io", "races"),
    }

    def __post_init__(self) -> None:
        self.api_key = self.api_key.strip()
        if not self.api_key:
            raise ValueError("API-Sports adapter requires a key.")
        self.http_get = _client(self.http_get)

    @property
    def source(self) -> Source:
        return _configured_source(
            name=self.name,
            kind=SourceKind.PAID_API,
            cost=SourceCost.PAID,
            sports=set(self._routes),
            capabilities={"fixtures", "event_lookup", "teams", "players", "standings", "form", "stats", "injuries", "availability", "odds", "results"},
            configured=bool(self.api_key),
            notes="Metered/free-allowance API-Sports family. Targeted enrichment only; quota is never spent by broad radar unless explicitly enabled.",
            priority_bias=20,
        )

    def fetch(self, request: SourceRequest) -> object:
        sport = (request.sport or request.metadata.get("sport") or "").casefold().replace(" ", "_")
        if sport not in self._routes:
            raise ValueError(f"API-Sports does not have a verified route for sport: {sport or 'missing'}")
        base, fixture_path = self._routes[sport]
        capability = request.capability.casefold().strip()
        paths = {
            "fixtures": fixture_path,
            "results": fixture_path,
            "event_lookup": fixture_path,
            "teams": "teams",
            "players": "players",
            "standings": "standings",
            "form": "fixtures",
            "stats": "fixtures/statistics",
            "injuries": "injuries",
            "availability": "injuries",
            "odds": "odds",
        }
        path = paths.get(capability)
        if path is None:
            raise ValueError(f"{self.name} does not implement capability: {request.capability}")
        metadata = request.metadata or {}
        params: dict[str, object] = {}
        if capability in {"fixtures", "results"}:
            params.update({"date": metadata.get("date"), "next": metadata.get("next"), "last": metadata.get("last"), "league": metadata.get("league"), "season": metadata.get("season")})
            if capability == "results":
                params["status"] = metadata.get("status", "FT")
        elif capability == "event_lookup":
            params.update({"id": metadata.get("event_id") or metadata.get("fixture_id") or metadata.get("game_id") or metadata.get("race_id")})
        else:
            params.update({key: metadata.get(key) for key in ("id", "team", "team_id", "league", "season", "player", "player_id", "date", "next", "last", "event", "fixture")})
        payload = self.http_get(
            f"{base}/{path}",
            params=_clean_params(params),
            headers={"x-apisports-key": self.api_key},
        )
        provider_rows = _rows(payload)
        normalized = [self._normalize(row, sport=sport) for row in provider_rows]
        normalized = [row for row in normalized if row]
        return _result(self.name, normalized, payload, reliability="medium", subject=str(metadata.get("event_id") or "") or None)

    @staticmethod
    def _normalize(row: dict[str, Any], *, sport: str) -> dict[str, Any]:
        fixture = row.get("fixture") if isinstance(row.get("fixture"), dict) else row
        teams = row.get("teams") if isinstance(row.get("teams"), dict) else {}
        home = _first(teams.get("home"), "name", "team") or _first(row, "homeTeam", "home")
        away = _first(teams.get("away"), "name", "team") or _first(row, "awayTeam", "away")
        league = _first(row.get("league"), "name", "league") or _first(row, "league")
        starts = _first(fixture, "date", "startTime", "timestamp") or _first(row, "date", "startTime")
        event_id = _first(fixture, "id") or _first(row, "id", "game_id", "race_id")
        name = _first(row, "name", "event_name") or (f"{home} vs {away}" if home and away else None)
        result = {"sport": sport, "event": name, "home": home, "away": away, "competition": league, "starts_at": starts, "event_id": event_id, "provider_event_id": event_id}
        return {key: value for key, value in result.items() if value not in (None, "", [])}


@dataclass
class SportsGameOddsAdapter:
    """SportsGameOdds v2 market sensor; never an executable bookmaker."""

    api_key: str
    http_get: HttpGet | None = None
    name = "SportsGameOdds"
    base_url = "https://api.sportsgameodds.com/v2"

    def __post_init__(self) -> None:
        self.api_key = self.api_key.strip()
        if not self.api_key:
            raise ValueError("SportsGameOdds adapter requires a key.")
        self.http_get = _client(self.http_get)

    @property
    def source(self) -> Source:
        return _configured_source(
            name=self.name,
            kind=SourceKind.PAID_API,
            cost=SourceCost.PAID,
            sports={"football", "basketball", "baseball", "ice_hockey", "hockey", "tennis", "golf", "mma", "american_football"},
            capabilities={"fixtures", "event_lookup", "sport_catalog", "league_catalog", "market_catalog", "teams", "players", "usage", "odds", "results"},
            configured=bool(self.api_key),
            notes="Current SportsGameOdds v2 market sensor. Prices inform consensus and research priority but cannot satisfy the SportyBet/Bet9ja action-book gate.",
            priority_bias=30,
        )

    def fetch(self, request: SourceRequest) -> object:
        capability = request.capability.casefold().strip()
        endpoints = {
            "fixtures": "events",
            "event_lookup": "events",
            "odds": "events",
            "results": "events",
            "sport_catalog": "sports",
            "league_catalog": "leagues",
            "market_catalog": "markets",
            "teams": "teams",
            "players": "players",
            "usage": "account/usage",
        }
        endpoint = endpoints.get(capability)
        if endpoint is None:
            raise ValueError(f"{self.name} does not implement capability: {request.capability}")
        metadata = request.metadata or {}
        params = {
            "oddsAvailable": metadata.get("odds_available", True) if capability in {"fixtures", "odds"} else None,
            "leagueID": metadata.get("league_id") or metadata.get("leagueID"),
            "oddID": metadata.get("odd_id") or metadata.get("oddID"),
            "includeAltLines": metadata.get("include_alt_lines"),
            "cursor": metadata.get("cursor"),
            "limit": metadata.get("limit"),
            "sportID": metadata.get("sport_id") or metadata.get("sportID"),
            "eventID": metadata.get("event_id") or metadata.get("eventID"),
        }
        payload = self.http_get(
            f"{self.base_url}/{endpoint}",
            params=_clean_params(params),
            headers={"x-api-key": self.api_key},
        )
        provider_rows = _rows(payload)
        normalized = [self._normalize_event(row, sport=request.sport or "") for row in provider_rows] if endpoint == "events" else provider_rows
        normalized = [row for row in normalized if row]
        raw_key = {
            "sport_catalog": "sports",
            "league_catalog": "leagues",
            "market_catalog": "markets",
            "teams": "teams",
            "players": "players",
            "usage": "usage",
        }.get(capability, "events")
        return {
            "summary": f"{self.name} returned {len(normalized)} record(s) from {endpoint}.",
            "reliability": "medium",
            "market_sensor": True,
            "raw": {raw_key: normalized, "provider_payload": payload, "partial": False},
        }

    @classmethod
    def _normalize_event(cls, row: dict[str, Any], sport: str) -> dict[str, Any]:
        status = row.get("status") if isinstance(row.get("status"), dict) else {}
        teams = row.get("teams") if isinstance(row.get("teams"), dict) else {}
        home = _first(teams.get("home"), "name", "displayName") or _first(row, "homeTeam", "home")
        away = _first(teams.get("away"), "name", "displayName") or _first(row, "awayTeam", "away")
        competition = _first(row, "leagueName", "league", "competition")
        name = _first(row, "name", "eventName", "shortName") or (f"{home} vs {away}" if home and away else None)
        odds: list[dict[str, Any]] = []
        raw_odds = row.get("odds") if isinstance(row.get("odds"), dict) else {}
        for odd_id, odd in raw_odds.items():
            if not isinstance(odd, dict):
                continue
            by_book = odd.get("byBookmaker") if isinstance(odd.get("byBookmaker"), dict) else {}
            for bookmaker, quote in by_book.items():
                quote = quote if isinstance(quote, dict) else {"odds": quote}
                decimal = _american_to_decimal(quote.get("odds") or quote.get("price"))
                if decimal is None or not quote.get("available", True):
                    continue
                parts = str(odd_id).split("-")
                side = parts[-1] if len(parts) >= 1 else None
                bet_type = parts[-2] if len(parts) >= 2 else None
                period = parts[-3] if len(parts) >= 3 else None
                entity = parts[-4] if len(parts) >= 4 else None
                stat = "-".join(parts[:-4]) if len(parts) > 4 else None
                family = {"ml": "winner", "ml3way": "winner", "sp": "handicap", "ou": "total"}.get(bet_type or "", bet_type)
                odds.append({"source_market_id": str(odd_id), "source_outcome_id": str(odd_id), "bookmaker": bookmaker, "decimal_odds": decimal, "line": quote.get("spread") or quote.get("overUnder"), "selection": str(odd_id), "market": str(odd_id), "family": family, "metric": stat, "period": period, "participant": entity, "side": side, "observed_at": quote.get("lastUpdatedAt")})
        result = {"sport": str(sport).casefold(), "event": name, "home": home, "away": away, "competition": competition, "starts_at": status.get("startsAt") or row.get("startsAt"), "event_id": row.get("eventID") or row.get("id"), "provider_event_id": row.get("eventID") or row.get("id")}
        if odds:
            result["odds"] = odds
        return {key: value for key, value in result.items() if value not in (None, "", [])}


@dataclass
class PandaScoreAdapter:
    """PandaScore esports evidence adapter using Bearer authentication."""

    token: str
    http_get: HttpGet | None = None
    name = "PandaScore"
    base_url = "https://api.pandascore.co"

    def __post_init__(self) -> None:
        self.token = self.token.strip()
        if not self.token:
            raise ValueError("PandaScore adapter requires a token.")
        self.http_get = _client(self.http_get)

    @property
    def source(self) -> Source:
        return _configured_source(
            name=self.name,
            kind=SourceKind.PAID_API,
            cost=SourceCost.PAID,
            sports={"esports"},
            capabilities={"fixtures", "results", "event_lookup", "teams", "players", "tournaments", "leagues", "series", "standings", "rosters", "stats"},
            configured=bool(self.token),
            notes="Authenticated esports evidence specialist. Provider IDs stay scoped to PandaScore and are not portable to other providers.",
            priority_bias=20,
        )

    def fetch(self, request: SourceRequest) -> object:
        capability = request.capability.casefold().strip()
        metadata = request.metadata or {}
        if capability in {"fixtures", "results"}:
            game = str(metadata.get("game") or metadata.get("videogame") or "").strip().strip("/")
            if game:
                game = _segment(game, "PandaScore game")
            endpoint = f"/{game}/matches" if game else "/matches"
            if capability == "results":
                endpoint += "/past"
        elif capability == "event_lookup":
            identifier = metadata.get("event_id") or metadata.get("match_id")
            if not identifier:
                raise ValueError("PandaScore event lookup needs metadata.event_id or match_id.")
            endpoint = f"/matches/{_segment(identifier, 'PandaScore match id')}"
        else:
            routes = {"teams": "teams", "players": "players", "tournaments": "tournaments", "leagues": "leagues", "series": "series", "standings": "standings", "rosters": "rosters", "stats": "matches"}
            if capability not in routes:
                raise ValueError(f"{self.name} does not implement capability: {request.capability}")
            endpoint = f"/{routes[capability]}"
        params = {key: metadata.get(key) for key in ("page", "per_page", "sort", "filter", "range", "search")}
        payload = self.http_get(f"{self.base_url}{endpoint}", params=_clean_params(params), headers={"Authorization": f"Bearer {self.token}"})
        provider_rows = _rows(payload)
        normalized = [self._normalize_match(row) for row in provider_rows] if capability in {"fixtures", "results", "event_lookup"} else provider_rows
        normalized = [row for row in normalized if row]
        return _result(self.name, normalized, payload, reliability="high", provider="pandascore")

    @staticmethod
    def _normalize_match(row: dict[str, Any]) -> dict[str, Any]:
        opponents = row.get("opponents") if isinstance(row.get("opponents"), list) else []
        names = []
        for item in opponents[:2]:
            if isinstance(item, dict):
                opponent = item.get("opponent") if isinstance(item.get("opponent"), dict) else item
                names.append(_first(opponent, "name", "slug"))
        league = _first(row.get("league"), "name", "slug")
        serie = _first(row.get("serie"), "name", "slug")
        tournament = _first(row.get("tournament"), "name", "slug")
        event_id = row.get("id")
        return {key: value for key, value in {
            "sport": "esports",
            "event": _first(row, "name", "slug") or (" vs ".join(str(name) for name in names if name) if names else None),
            "home": names[0] if names else None,
            "away": names[1] if len(names) > 1 else None,
            "competition": league or serie or tournament,
            "division": _first(row.get("tournament"), "name", "slug"),
            "starts_at": row.get("begin_at") or row.get("scheduled_at"),
            "event_id": event_id,
            "provider_event_id": event_id,
            "provider_competition_id": _first(row.get("league"), "id"),
        }.items() if value not in (None, "", [])}


@dataclass
class JolpicaF1Adapter:
    """Public Jolpica/Ergast-compatible F1 structured source."""

    http_get: HttpGet | None = None
    name = "Jolpica F1"
    base_url = "https://api.jolpi.ca/ergast/f1"

    def __post_init__(self) -> None:
        self.http_get = _client(self.http_get)

    @property
    def source(self) -> Source:
        return _configured_source(
            name=self.name,
            kind=SourceKind.PUBLIC_ENDPOINT,
            cost=SourceCost.FREE,
            sports={"motorsport"},
            capabilities={"fixtures", "schedule", "results", "standings", "drivers", "constructors", "qualifying", "sprint", "laps", "pit_stops"},
            configured=True,
            notes="Public Jolpica F1 structured source. Cache historical requests and respect the volunteer-hosted service limits.",
            priority_bias=5,
        )

    def fetch(self, request: SourceRequest) -> object:
        capability = request.capability.casefold().strip()
        metadata = request.metadata or {}
        season = _segment(metadata.get("season") or "current", "Jolpica season")
        round_value = _segment(metadata["round"], "Jolpica round") if metadata.get("round") is not None else None
        routes = {
            "fixtures": f"{season}.json",
            "schedule": f"{season}.json",
            "results": f"{season}/{round_value}/results.json" if round_value else f"{season}/results.json",
            "standings": f"{season}/driverstandings.json",
            "drivers": f"{season}/drivers.json",
            "constructors": f"{season}/constructors.json",
            "qualifying": f"{season}/qualifying.json",
            "sprint": f"{season}/sprint.json",
            "laps": f"{season}/{round_value}/laps/{_segment(metadata['lap'], 'Jolpica lap')}.json" if round_value and metadata.get("lap") else f"{season}/{round_value}/laps.json" if round_value else f"{season}/laps.json",
            "pit_stops": f"{season}/{round_value}/pitstops.json" if round_value else f"{season}/pitstops.json",
        }
        route = routes.get(capability)
        if route is None:
            raise ValueError(f"{self.name} does not implement capability: {request.capability}")
        payload = self.http_get(f"{self.base_url}/{route}", params={"limit": metadata.get("limit"), "offset": metadata.get("offset")}, headers=None)
        races = self._races(payload)
        return _result(self.name, races, payload, reliability="high", provider="jolpica")

    @staticmethod
    def _races(payload: object) -> list[dict[str, Any]]:
        if not isinstance(payload, dict):
            return _rows(payload)
        mrdata = payload.get("MRData") if isinstance(payload.get("MRData"), dict) else payload
        table = mrdata.get("RaceTable") if isinstance(mrdata, dict) else None
        races = table.get("Races") if isinstance(table, dict) else None
        return [row for row in races if isinstance(row, dict)] if isinstance(races, list) else _rows(payload)


@dataclass
class FastF1Adapter:
    """Lazy FastF1 evidence adapter with optional injected module for tests."""

    cache_dir: Path | None = None
    fastf1_module: object | None = None
    name = "FastF1"

    def __post_init__(self) -> None:
        if self.fastf1_module is None:
            try:
                self.fastf1_module = importlib.import_module("fastf1")
            except ModuleNotFoundError:
                self.fastf1_module = None
        if self.cache_dir and self.fastf1_module is not None:
            cache = getattr(self.fastf1_module, "Cache", None)
            enable = getattr(cache, "enable_cache", None)
            if callable(enable):
                self.cache_dir.expanduser().mkdir(parents=True, exist_ok=True)
                enable(str(self.cache_dir.expanduser()))

    @property
    def source(self) -> Source:
        return _configured_source(
            name=self.name,
            kind=SourceKind.OPEN_DATA,
            cost=SourceCost.FREE,
            sports={"motorsport"},
            capabilities={"schedule", "session_results", "timing", "telemetry", "weather", "tyres", "positions"},
            configured=self.fastf1_module is not None,
            notes="Local FastF1 analytical dependency for timing, telemetry, tyres and weather. Historical data is cached locally.",
            priority_bias=10,
        )

    def fetch(self, request: SourceRequest) -> object:
        if self.fastf1_module is None:
            raise RuntimeError("FastF1 is not installed; source is not_configured.")
        metadata = request.metadata or {}
        capability = request.capability.casefold().strip()
        if capability == "schedule":
            year = int(metadata.get("year") or metadata.get("season") or datetime.now(timezone.utc).year)
            schedule = self.fastf1_module.get_event_schedule(year)
            rows = self._records(schedule)
        else:
            year = int(metadata.get("year") or metadata.get("season") or datetime.now(timezone.utc).year)
            event = metadata.get("event") or metadata.get("round")
            identifier = metadata.get("identifier") or metadata.get("session") or "R"
            if event is None:
                raise ValueError("FastF1 session evidence needs metadata.event/round.")
            session = self.fastf1_module.get_session(year, event, identifier)
            load = getattr(session, "load", None)
            if callable(load):
                load(telemetry=capability == "telemetry", weather=capability == "weather", messages=False)
            value = getattr(session, {"session_results": "results", "timing": "laps", "telemetry": "laps", "weather": "weather_data", "tyres": "laps", "positions": "pos_data"}.get(capability, "results"), None)
            rows = self._records(value)
        return _result(self.name, rows, rows, reliability="high", provider="fastf1")

    @staticmethod
    def _records(value: object) -> list[dict[str, Any]]:
        if value is None:
            return []
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        to_dict = getattr(value, "to_dict", None)
        if callable(to_dict):
            try:
                result = to_dict("records")
                return [item for item in result if isinstance(item, dict)] if isinstance(result, list) else []
            except TypeError:
                result = to_dict()
                return [result] if isinstance(result, dict) else []
        return [value] if isinstance(value, dict) else []


@dataclass
class CricsheetAdapter:
    """Local, incremental Cricsheet JSON query adapter (historical, not live fixtures)."""

    data_dir: Path | None = None
    name = "Cricsheet"
    _index: dict[str, Path] | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        self.data_dir = self.data_dir.expanduser() if self.data_dir else None

    @property
    def source(self) -> Source:
        return _configured_source(
            name=self.name,
            kind=SourceKind.OPEN_DATA,
            cost=SourceCost.FREE,
            sports={"cricket"},
            capabilities={"historical", "match_lookup", "stats", "player_stats", "team_stats"},
            configured=bool(self.data_dir and self.data_dir.is_dir()),
            notes="Local Cricsheet JSON analytical dataset. It is historical ball-by-ball evidence, not a live fixture or odds API.",
            priority_bias=5,
        )

    def fetch(self, request: SourceRequest) -> object:
        if not self.data_dir or not self.data_dir.is_dir():
            raise RuntimeError("Cricsheet data directory is not configured.")
        metadata = request.metadata or {}
        match_id = str(metadata.get("match_id") or metadata.get("event_id") or "").strip()
        if match_id:
            path = self._find(match_id)
            if path is None:
                raise RuntimeError(f"Cricsheet match {match_id} was not found in the local dataset.")
            payload = json.loads(path.read_text(encoding="utf-8"))
            rows = [payload] if isinstance(payload, dict) else []
        else:
            rows = []
            for path in self._paths()[: max(1, min(int(metadata.get("limit") or 25), 100))]:
                try:
                    value = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue
                if isinstance(value, dict):
                    rows.append(value)
        return _result(self.name, rows, rows, reliability="high", provider="cricsheet")

    def _paths(self) -> list[Path]:
        return sorted(self.data_dir.rglob("*.json")) if self.data_dir else []

    def _find(self, match_id: str) -> Path | None:
        if self._index is None:
            self._index = {path.stem: path for path in self._paths()}
        return self._index.get(match_id) or next((path for stem, path in self._index.items() if match_id in stem), None)


@dataclass
class SportsDataIOAdapter:
    """Targeted SportsDataIO adapter using the documented subscription-key header."""

    api_key: str
    http_get: HttpGet | None = None
    name = "SportsDataIO"
    base_url = "https://api.sportsdata.io/v3"

    def __post_init__(self) -> None:
        self.api_key = self.api_key.strip()
        if not self.api_key:
            raise ValueError("SportsDataIO adapter requires a key.")
        self.http_get = _client(self.http_get)

    @property
    def source(self) -> Source:
        return _configured_source(
            name=self.name,
            kind=SourceKind.PAID_API,
            cost=SourceCost.PAID,
            sports={"american_football", "basketball", "baseball", "ice_hockey", "football", "soccer"},
            capabilities={"fixtures", "results", "standings", "stats", "injuries", "availability", "players", "teams", "odds"},
            configured=bool(self.api_key),
            notes="Commercial targeted evidence source. League APIs provide depth; Global coverage must not be mislabeled as deep injury/player evidence.",
            priority_bias=35,
        )

    def fetch(self, request: SourceRequest) -> object:
        sport = str(request.metadata.get("api_sport") or request.metadata.get("league") or request.sport or "").casefold().replace(" ", "")
        sport = {"americanfootball": "nfl", "icehockey": "nhl", "soccer": "soccer"}.get(sport, sport)
        sport = _segment(sport, "SportsDataIO sport")
        if not sport:
            raise ValueError("SportsDataIO request needs sport or metadata.api_sport.")
        capability = request.capability.casefold().strip()
        metadata = request.metadata or {}
        date_value = metadata.get("date") or date.today().isoformat()
        if capability in {"fixtures", "results"}:
            path = f"{sport}/scores/json/GamesByDate/{date_value}"
        else:
            resources = {"standings": "scores/json/Standings", "stats": "stats/json/PlayerSeasonStats", "injuries": "scores/json/Injuries", "availability": "scores/json/Injuries", "players": "scores/json/Players", "teams": "scores/json/Teams", "odds": "odds/json/GameOddsByDate"}
            resource = resources.get(capability)
            if resource is None:
                raise ValueError(f"{self.name} does not implement capability: {request.capability}")
            path = f"{sport}/{resource}"
        payload = self.http_get(f"{self.base_url}/{path}", params={}, headers={"Ocp-Apim-Subscription-Key": self.api_key})
        provider_rows = _rows(payload)
        normalized = [ApiSportsAdapter._normalize(row, sport=request.sport or sport) for row in provider_rows] if capability in {"fixtures", "results"} else provider_rows
        normalized = [row for row in normalized if row]
        return _result(self.name, normalized, payload, reliability="high", provider="sportsdataio")


@dataclass
class SportMonksAdapter:
    """SportMonks v2 cricket and v3 motorsport/football evidence adapter."""

    token: str
    http_get: HttpGet | None = None
    name = "SportMonks"
    base_url = "https://api.sportmonks.com/v3"

    def __post_init__(self) -> None:
        self.token = self.token.strip()
        if not self.token:
            raise ValueError("SportMonks adapter requires a token.")
        self.http_get = _client(self.http_get)

    @property
    def source(self) -> Source:
        return _configured_source(
            name=self.name,
            kind=SourceKind.PAID_API,
            cost=SourceCost.PAID,
            sports={"cricket", "motorsport", "football"},
            capabilities={"fixtures", "results", "standings", "teams", "players", "drivers", "venues", "seasons", "schedules", "live_scores"},
            configured=bool(self.token),
            notes="Authenticated specialist source. Uses Cricket routes and Motorsport API v3; deprecated Formula One v1 routes are not used.",
            priority_bias=40,
        )

    def fetch(self, request: SourceRequest) -> object:
        sport = (request.sport or request.metadata.get("sport") or "").casefold().replace(" ", "_")
        family = "motorsport" if sport in {"motorsport", "f1", "formula_1"} else "cricket" if sport == "cricket" else "football"
        capability = request.capability.casefold().strip()
        routes = {"fixtures": "fixtures", "results": "fixtures", "standings": "standings", "teams": "teams", "players": "players", "drivers": "drivers", "venues": "venues", "seasons": "seasons", "schedules": "schedules", "live_scores": "livescores"}
        route = routes.get(capability)
        if route is None:
            raise ValueError(f"{self.name} does not implement capability: {request.capability}")
        identifier = request.metadata.get("event_id") or request.metadata.get("fixture_id")
        if identifier:
            route = f"{route}/{_segment(identifier, 'SportMonks identifier')}"
        include = request.metadata.get("include")
        params = {"include": include, "per_page": request.metadata.get("per_page"), "page": request.metadata.get("page")}
        payload = self.http_get(f"{self.base_url}/{family}/{route}", params=_clean_params(params), headers={"Authorization": self.token})
        provider_rows = _rows(payload)
        normalized = [self._normalize(row, sport=sport or family) for row in provider_rows] if capability in {"fixtures", "results", "schedules", "live_scores"} else provider_rows
        normalized = [row for row in normalized if row]
        return _result(self.name, normalized, payload, reliability="high", provider="sportmonks", api_family=family)

    @staticmethod
    def _normalize(row: dict[str, Any], *, sport: str) -> dict[str, Any]:
        participants = row.get("participants") if isinstance(row.get("participants"), list) else []
        names = [_first(item, "name", "short_code") for item in participants[:2]]
        event_id = row.get("id")
        return {key: value for key, value in {"sport": sport, "event": row.get("name") or (" vs ".join(str(name) for name in names if name) if names else None), "home": names[0] if names else None, "away": names[1] if len(names) > 1 else None, "competition": _first(row.get("league"), "name") or _first(row, "league_name", "competition"), "starts_at": row.get("starting_at") or row.get("start_time"), "event_id": event_id, "provider_event_id": event_id}.items() if value not in (None, "", [])}


@dataclass
class StatsBombOpenDataAdapter:
    """Incremental local reader for StatsBomb/Hudl Open Data."""

    data_dir: Path | None = None
    name = "StatsBomb / Hudl Open Data"

    def __post_init__(self) -> None:
        self.data_dir = self.data_dir.expanduser() if self.data_dir else None

    @property
    def source(self) -> Source:
        return _configured_source(
            name=self.name,
            kind=SourceKind.OPEN_DATA,
            cost=SourceCost.FREE,
            sports={"football"},
            capabilities={"historical", "matches", "events", "lineups", "stats", "360"},
            configured=bool(self.data_dir and self.data_dir.is_dir()),
            notes="Historical football analytical dataset. Use for calibration/backtesting, not live fixtures or odds; preserve StatsBomb attribution.",
            priority_bias=6,
        )

    def fetch(self, request: SourceRequest) -> object:
        if not self.data_dir or not self.data_dir.is_dir():
            raise RuntimeError("StatsBomb Open Data directory is not configured.")
        metadata = request.metadata or {}
        capability = request.capability.casefold().strip()
        match_id = str(metadata.get("match_id") or metadata.get("event_id") or "").strip()
        candidates = sorted(self.data_dir.rglob("*.json"))
        if capability == "matches":
            candidates = [path for path in candidates if any("match" in part.casefold() for part in path.parts)]
        elif capability == "events":
            candidates = [path for path in candidates if any("event" in part.casefold() for part in path.parts)]
        elif capability == "lineups":
            candidates = [path for path in candidates if any("lineup" in part.casefold() for part in path.parts)]
        if match_id:
            candidates = [path for path in candidates if match_id in path.stem]
        rows: list[dict[str, Any]] = []
        for path in candidates[: max(1, min(int(metadata.get("limit") or 25), 100))]:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(payload, list):
                rows.extend(item for item in payload if isinstance(item, dict))
            elif isinstance(payload, dict):
                rows.append(payload)
        return _result(self.name, rows, rows, reliability="high", provider="statsbomb_open_data")


@dataclass
class OpenLigaDBAdapter:
    """Free OpenLigaDB football corroboration adapter."""

    http_get: HttpGet | None = None
    name = "OpenLigaDB"
    base_url = "https://api.openligadb.de"

    def __post_init__(self) -> None:
        self.http_get = _client(self.http_get)

    @property
    def source(self) -> Source:
        return _configured_source(
            name=self.name,
            kind=SourceKind.PUBLIC_ENDPOINT,
            cost=SourceCost.FREE,
            sports={"football"},
            capabilities={"fixtures", "results", "event_lookup", "league_catalog", "team_catalog", "standings", "last_changed"},
            configured=True,
            notes="Free football fixture/result corroboration source. Query only the requested league and season.",
            priority_bias=8,
        )

    def fetch(self, request: SourceRequest) -> object:
        capability = request.capability.casefold().strip()
        metadata = request.metadata or {}
        league = _segment(metadata.get("league") or metadata.get("league_id"), "OpenLigaDB league") if (metadata.get("league") or metadata.get("league_id")) else None
        season = _segment(metadata.get("season"), "OpenLigaDB season") if metadata.get("season") is not None else None
        if capability in {"fixtures", "results", "standings", "last_changed"} and (not league or not season):
            raise ValueError("OpenLigaDB request needs metadata.league and metadata.season.")
        if capability in {"fixtures", "results"}:
            path = f"/getmatchdata/{league}/{season}"
        elif capability == "standings":
            path = f"/getbltable/{league}/{season}"
        elif capability == "last_changed":
            path = f"/getlastchangedate/{league}/{season}"
        elif capability == "event_lookup":
            identifier = metadata.get("event_id") or metadata.get("match_id")
            if not identifier:
                raise ValueError("OpenLigaDB event lookup needs metadata.event_id or match_id.")
            path = f"/getmatchdata/{_segment(identifier, 'OpenLigaDB match id')}"
        elif capability == "league_catalog":
            path = "/getavailableleagues"
        elif capability == "team_catalog":
            path = "/getavailableteams"
        else:
            raise ValueError(f"{self.name} does not implement capability: {request.capability}")
        payload = self.http_get(f"{self.base_url}{path}", params=None, headers=None)
        provider_rows = _rows(payload)
        normalized = [self._normalize(row) for row in provider_rows] if capability in {"fixtures", "results", "event_lookup"} else provider_rows
        normalized = [row for row in normalized if row]
        return _result(self.name, normalized, payload, reliability="medium", provider="openligadb")

    @staticmethod
    def _normalize(row: dict[str, Any]) -> dict[str, Any]:
        event = row.get("match") if isinstance(row.get("match"), dict) else row
        home = _first(event.get("team1"), "teamName", "name") or _first(event, "homeTeamName", "home")
        away = _first(event.get("team2"), "teamName", "name") or _first(event, "awayTeamName", "away")
        event_id = event.get("matchID") or event.get("id")
        return {key: value for key, value in {"sport": "football", "event": event.get("name") or (f"{home} vs {away}" if home and away else None), "home": home, "away": away, "competition": _first(event.get("leagueName"), "name") or event.get("leagueName"), "starts_at": event.get("matchDateTimeUTC") or event.get("matchDateTime"), "event_id": event_id, "provider_event_id": event_id}.items() if value not in (None, "", [])}


@dataclass
class NbaLiveDataAdapter:
    """NBA public LiveData scoreboard/boxscore corroboration source."""

    http_get: HttpGet | None = None
    name = "NBA LiveData"
    base_url = "https://cdn.nba.com/static/json/liveData"

    def __post_init__(self) -> None:
        self.http_get = _client(self.http_get)

    @property
    def source(self) -> Source:
        return _configured_source(
            name=self.name,
            kind=SourceKind.PUBLIC_ENDPOINT,
            cost=SourceCost.FREE,
            sports={"basketball"},
            capabilities={"fixtures", "live_scores", "results", "event_lookup", "stats"},
            configured=True,
            notes="Public NBA LiveData corroboration endpoint with medium reliability; do not make it the sole NBA source.",
            priority_bias=9,
        )

    def fetch(self, request: SourceRequest) -> object:
        capability = request.capability.casefold().strip()
        metadata = request.metadata or {}
        if capability in {"fixtures", "live_scores", "results"}:
            path = "scoreboard/todaysScoreboard_00.json"
        elif capability in {"event_lookup", "stats"}:
            game_id = metadata.get("game_id") or metadata.get("event_id")
            if not game_id:
                raise ValueError("NBA LiveData event lookup needs metadata.game_id or event_id.")
            path = f"boxscore/boxscore_{_segment(game_id, 'NBA game id')}.json"
        else:
            raise ValueError(f"{self.name} does not implement capability: {request.capability}")
        payload = self.http_get(f"{self.base_url}/{path}", params=None, headers=None)
        games = payload.get("scoreboard", {}).get("games", []) if isinstance(payload, dict) and isinstance(payload.get("scoreboard"), dict) else _rows(payload)
        normalized = [self._normalize(game) for game in games if isinstance(game, dict)]
        normalized = [row for row in normalized if row]
        return _result(self.name, normalized, payload, reliability="medium", provider="nba_livedata")

    @staticmethod
    def _normalize(row: dict[str, Any]) -> dict[str, Any]:
        home = _first(row.get("homeTeam"), "teamName", "teamTricode")
        away = _first(row.get("awayTeam"), "teamName", "teamTricode")
        event_id = row.get("gameId")
        return {key: value for key, value in {"sport": "basketball", "event": row.get("gameLabel") or (f"{away} vs {home}" if home and away else None), "home": home, "away": away, "competition": "NBA", "starts_at": row.get("gameTimeUTC") or row.get("gameEt"), "event_id": event_id, "provider_event_id": event_id, "status": row.get("gameStatusText") or row.get("gameStatus")}.items() if value not in (None, "", [])}


__all__ = [
    "ApiSportsAdapter",
    "SportsGameOddsAdapter",
    "PandaScoreAdapter",
    "JolpicaF1Adapter",
    "FastF1Adapter",
    "CricsheetAdapter",
    "SportsDataIOAdapter",
    "SportMonksAdapter",
    "StatsBombOpenDataAdapter",
    "OpenLigaDBAdapter",
    "NbaLiveDataAdapter",
]
