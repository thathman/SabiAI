from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from typing import Any

from sabiai.sources import SourceBundle, SourceRequest, SourceService, default_source_bundle
from sabiai.sports import FormService, sport_engine_profile
from sabiai.storage import SabiDatabase


_ESPN_LEAGUES = {
    "basketball": "nba",
    "baseball": "mlb",
    "ice_hockey": "nhl",
    "american_football": "nfl",
}

_FOOTBALL_LEAGUES = {
    "premier league": "eng.1",
    "english premier league": "eng.1",
    "championship": "eng.2",
    "la liga": "esp.1",
    "bundesliga": "ger.1",
    "serie a": "ita.1",
    "ligue 1": "fra.1",
    "eredivisie": "ned.1",
    "liga portugal": "por.1",
    "super lig": "tur.1",
    "mls": "usa.1",
    "major league soccer": "usa.1",
    "uefa champions league": "uefa.champions",
    "champions league": "uefa.champions",
    "uefa europa league": "uefa.europa",
}


@dataclass(frozen=True, slots=True)
class EvidenceBuildResult:
    enriched: int
    ready: int
    weak: int
    failures: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "enriched": self.enriched,
            "ready": self.ready,
            "weak": self.weak,
            "failures": list(self.failures),
        }


class CandidateEvidenceBuilder:
    """Build bounded free-first evidence packets before model decisions.

    Limited-credit Parse sources are intentionally excluded here. When public structured data
    cannot close a gap, the packet names the missing work for Research Scout/Browser/Search.
    """

    def __init__(self, settings, database: SabiDatabase, bundle: SourceBundle | None = None):
        self.settings = settings
        self.database = database
        self.database.initialize()
        self.bundle = bundle or default_source_bundle(settings)
        self.service = SourceService(database, self.bundle.registry)
        self.form = FormService()

    def enrich_in_place(self, events: list[dict[str, Any]], *, limit: int = 6) -> EvidenceBuildResult:
        failures: list[str] = []
        enriched = ready = weak = 0
        for index, event in enumerate(events):
            if not isinstance(event, dict):
                continue
            if index >= max(1, int(limit)):
                event["evidence_packet"] = self._budget_limited(event)
                weak += 1
                continue
            try:
                packet = self.build(event)
            except Exception as exc:
                packet = self._failed(event, exc)
                failures.append(f"{event.get('event') or 'event'}: {type(exc).__name__}: {str(exc)[:240]}")
            event["evidence_packet"] = packet
            enriched += 1
            if packet.get("ready_for_decision"):
                ready += 1
            else:
                weak += 1
        return EvidenceBuildResult(enriched, ready, weak, tuple(failures[-100:]))

    def build(self, event: dict[str, Any]) -> dict[str, Any]:
        sport = str(event.get("sport") or "unknown")
        profile = sport_engine_profile(sport)
        home = str(event.get("home") or "").strip()
        away = str(event.get("away") or "").strip()
        sections: dict[str, Any] = {}
        failures: list[str] = []
        sources_used: set[str] = set()

        if home and away and profile.event_shape in {"team", "head_to_head"}:
            home_rows, home_failures = self._team_evidence(home, event)
            away_rows, away_failures = self._team_evidence(away, event)
            failures.extend(home_failures)
            failures.extend(away_failures)
            sources_used.update(row["source"] for row in (*home_rows, *away_rows) if row.get("source"))

            home_form = self.form.summarize(home, [row["form"] for row in home_rows if row.get("form")], limit=10)
            away_form = self.form.summarize(away, [row["form"] for row in away_rows if row.get("form")], limit=10)
            sections["form"] = {"home": home_form, "away": away_form}
            if home_rows:
                h2h = self.form.head_to_head(home, away, [row["form"] for row in home_rows if row.get("form")], limit=10)
                if h2h.get("meetings"):
                    sections["h2h"] = h2h

            availability_checked = any(isinstance(row.get("injuries"), dict) for row in (*home_rows, *away_rows))
            if availability_checked:
                sections["availability"] = {
                    "checked": True,
                    "home": self._injury_rows(home_rows),
                    "away": self._injury_rows(away_rows),
                    "needs_official_confirmation": True,
                    "note": "A structured injury feed was checked; an empty list means no listed injury, not guaranteed full availability.",
                }

            schedule = {
                "home": self._schedule_summary(home_rows),
                "away": self._schedule_summary(away_rows),
            }
            if schedule["home"] or schedule["away"]:
                sections["schedule"] = schedule
        else:
            event_rows, event_failures = self._event_evidence(event)
            failures.extend(event_failures)
            sources_used.update(row.get("source") for row in event_rows if row.get("source"))
            if event_rows:
                sections["event_sources"] = event_rows

        missing = self._missing_topics(profile, sections)
        ready_for_decision = self._ready(profile, sections)
        quality = "strong" if ready_for_decision and len(sections) >= 3 else "fair" if ready_for_decision else "weak"
        return {
            "quality": quality,
            "ready_for_decision": ready_for_decision,
            "sources": sorted(source for source in sources_used if source),
            "sections": sections,
            "required_topics": list(profile.evidence_topics),
            "missing_topics": missing,
            "source_failures": failures[-20:],
            "fallback_tasks": self._fallback_tasks(event, profile, missing, failures),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "note": (
                "Structured free-source evidence is sufficient for a bounded model decision."
                if ready_for_decision
                else "Do not auto-promote this event. Research Scout/browser/search should close the listed evidence gaps first."
            ),
        }

    def _team_evidence(self, team: str, event: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
        sport = str(event.get("sport") or "").strip()
        results: list[dict[str, Any]] = []
        failures: list[str] = []
        for source in self._team_sources(sport):
            try:
                context = self._provider_context(event, source)
                identity = self._query(source, "team_search", sport, {"team": team, **context}, ttl_seconds=86400)
                team_id = self._team_id(identity, source)
                row: dict[str, Any] = {"source": source, "team_id": team_id}
                try:
                    form = self._query(source, "form", sport, {"team_id": team_id, "limit": 10, **context}, ttl_seconds=21600)
                    row["form"] = self._form_item(source, team_id, form)
                except Exception as exc:
                    failures.append(f"{team}/{source}/form: {type(exc).__name__}: {str(exc)[:160]}")
                try:
                    schedule = self._query(source, "schedule", sport, {"team_id": team_id, "limit": 12, **context}, ttl_seconds=21600)
                    row["schedule"] = self._compact_payload(schedule)
                except Exception as exc:
                    failures.append(f"{team}/{source}/schedule: {type(exc).__name__}: {str(exc)[:160]}")
                if self._source_supports(source, "injuries"):
                    try:
                        injuries = self._query(source, "injuries", sport, {"team_id": team_id, **context}, ttl_seconds=1800)
                        row["injuries"] = self._compact_payload(injuries)
                    except Exception as exc:
                        failures.append(f"{team}/{source}/injuries: {type(exc).__name__}: {str(exc)[:160]}")
                results.append(row)
            except Exception as exc:
                failures.append(f"{team}/{source}: {type(exc).__name__}: {str(exc)[:180]}")
        return results, failures

    def _event_evidence(self, event: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
        sport = str(event.get("sport") or "").strip()
        name = str(event.get("event") or "").strip()
        results: list[dict[str, Any]] = []
        failures: list[str] = []
        if not name:
            return results, ["Event has no canonical name for evidence lookup."]
        for source in self._event_sources(sport):
            try:
                response = self._query(
                    source,
                    "event_search",
                    sport,
                    {"event": name, "date": str(event.get("starts_at") or "")[:10], **self._provider_context(event, source)},
                    ttl_seconds=3600,
                )
                results.append({"source": source, **self._compact_payload(response)})
            except Exception as exc:
                failures.append(f"{source}/event_search: {type(exc).__name__}: {str(exc)[:180]}")
        return results, failures

    def _team_sources(self, sport: str) -> tuple[str, ...]:
        candidates = []
        for source in self.bundle.registry.candidates(sport=sport, capability="team_search", include_paid=False):
            if source.name not in self.bundle.fetchers or source.name.startswith("Parse ·"):
                continue
            if source.capabilities and "team_search" not in {item.casefold() for item in source.capabilities}:
                continue
            candidates.append(source.name)
            if len(candidates) >= 2:
                break
        return tuple(candidates)

    def _event_sources(self, sport: str) -> tuple[str, ...]:
        candidates = []
        for source in self.bundle.registry.candidates(sport=sport, capability="event_search", include_paid=False):
            if source.name not in self.bundle.fetchers or source.name.startswith("Parse ·"):
                continue
            if source.capabilities and "event_search" not in {item.casefold() for item in source.capabilities}:
                continue
            candidates.append(source.name)
            if len(candidates) >= 2:
                break
        return tuple(candidates)

    def _source_supports(self, source_name: str, capability: str) -> bool:
        source = next((item for item in self.bundle.registry.all() if item.name == source_name), None)
        if source is None:
            return False
        return not source.capabilities or capability.casefold() in {item.casefold() for item in source.capabilities}

    def _query(self, source_name: str, capability: str, sport: str, metadata: dict[str, Any], *, ttl_seconds: int):
        clean = {key: value for key, value in metadata.items() if value not in (None, "")}
        raw_key = repr((source_name, capability, sport.casefold(), sorted(clean.items())))
        request = SourceRequest(
            request_key=f"engine-evidence:{hashlib.sha256(raw_key.encode()).hexdigest()[:24]}",
            capability=capability,
            sport=sport,
            ttl_seconds=ttl_seconds,
            metadata=clean,
            source_names=(source_name,),
        )
        return self.service.execute(request, self.bundle.fetchers, allow_paid=False)

    @staticmethod
    def _team_id(response, source_name: str) -> str:
        payload = response.payload if hasattr(response, "payload") else response
        raw = payload.get("raw") if isinstance(payload, dict) else None
        teams = raw.get("teams") if isinstance(raw, dict) else None
        if not isinstance(teams, list) or not teams:
            raise RuntimeError("Source returned no team identity candidates.")
        first = teams[0] if isinstance(teams[0], dict) else {}
        if source_name.casefold() == "thesportsdb":
            value = first.get("idTeam")
        elif source_name.casefold() == "espn public data":
            value = first.get("id") or first.get("uid")
        else:
            value = first.get("idTeam") or first.get("id") or first.get("uid")
        if value in (None, ""):
            raise RuntimeError("Source returned a team without a provider team id.")
        return str(value)

    @staticmethod
    def _form_item(source: str, team_id: str, response) -> dict[str, Any]:
        return {"source": source, "team_id": team_id, "response": {"payload": response.payload if hasattr(response, "payload") else response}}

    @staticmethod
    def _compact_payload(response) -> dict[str, Any]:
        payload = response.payload if hasattr(response, "payload") else response
        if not isinstance(payload, dict):
            return {"summary": str(payload)[:500]}
        output = {"summary": str(payload.get("summary") or "")[:500], "subject": payload.get("subject"), "reliability": payload.get("reliability")}
        raw = payload.get("raw")
        if isinstance(raw, dict):
            for key in ("injuries", "events", "results", "lineup"):
                rows = raw.get(key)
                if isinstance(rows, list):
                    output[key] = rows[:8]
                    output[f"{key}_count"] = len(rows)
            if raw.get("partial") is not None:
                output["partial"] = bool(raw.get("partial"))
        return {key: value for key, value in output.items() if value not in (None, "")}

    @staticmethod
    def _injury_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        found: list[dict[str, Any]] = []
        for row in rows:
            injuries = row.get("injuries") if isinstance(row.get("injuries"), dict) else {}
            for item in injuries.get("injuries") or []:
                if not isinstance(item, dict):
                    continue
                athlete = item.get("athlete") if isinstance(item.get("athlete"), dict) else {}
                found.append({
                    "player": athlete.get("displayName") or athlete.get("fullName") or item.get("name") or item.get("player"),
                    "status": item.get("status"),
                    "detail": item.get("details") or item.get("detail") or item.get("description"),
                    "source": row.get("source"),
                })
        return found[:20]

    @staticmethod
    def _schedule_summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        for row in rows:
            schedule = row.get("schedule") if isinstance(row.get("schedule"), dict) else {}
            events = schedule.get("events") or schedule.get("results") or []
            if events:
                output.append({"source": row.get("source"), "summary": schedule.get("summary"), "events": events[:6]})
        return output[:2]

    @staticmethod
    def _missing_topics(profile, sections: dict[str, Any]) -> list[str]:
        missing: list[str] = []
        if profile.event_shape in {"team", "head_to_head"}:
            form = sections.get("form") if isinstance(sections.get("form"), dict) else {}
            home = form.get("home") if isinstance(form.get("home"), dict) else {}
            away = form.get("away") if isinstance(form.get("away"), dict) else {}
            if not home.get("played") or not away.get("played"):
                missing.append("recent form for both participants")
            if profile.requires_lineup_or_roster and "availability" not in sections:
                missing.append("current lineup/roster availability")
            if "schedule" not in sections:
                missing.append("schedule/rest/travel context")
        else:
            if "event_sources" not in sections:
                missing.append("event-specific public evidence")
            missing.append("participant recent form from a sport-specific source")
        if profile.requires_weather:
            missing.append("current weather/conditions when materially relevant")
        if profile.requires_surface_or_venue:
            missing.append("surface/venue/course/track context when materially relevant")
        return list(dict.fromkeys(missing))

    @staticmethod
    def _ready(profile, sections: dict[str, Any]) -> bool:
        if profile.needs_discovery:
            return False
        if profile.event_shape in {"team", "head_to_head"}:
            form = sections.get("form") if isinstance(sections.get("form"), dict) else {}
            home = form.get("home") if isinstance(form.get("home"), dict) else {}
            away = form.get("away") if isinstance(form.get("away"), dict) else {}
            if not (home.get("played") and away.get("played")):
                return False
            if profile.requires_lineup_or_roster and "availability" not in sections:
                return False
            return True
        # Event lookup alone is never treated as enough evidence for an automated race/fight/field bet.
        return False

    @staticmethod
    def _fallback_tasks(event: dict[str, Any], profile, missing: list[str], failures: list[str]) -> list[str]:
        tasks = [f"Research Scout: verify {topic}." for topic in missing]
        if failures:
            tasks.append("Retry failed free sources or use a verified official/public source through OpenClaw Browser/Search.")
        if profile.settlement_concerns:
            tasks.append("Verify target-book settlement rules: " + "; ".join(profile.settlement_concerns) + ".")
        return list(dict.fromkeys(tasks))[:12]

    def _provider_context(self, event: dict[str, Any], source_name: str) -> dict[str, Any]:
        if source_name.casefold() != "espn public data":
            return {}
        sport = str(event.get("sport") or "").casefold().replace(" ", "_")
        league = event.get("league") or event.get("league_slug")
        if not league:
            if sport == "football":
                league = _FOOTBALL_LEAGUES.get(str(event.get("competition") or "").casefold())
            else:
                league = _ESPN_LEAGUES.get(sport)
        return {"league": league} if league else {}

    @staticmethod
    def _budget_limited(event: dict[str, Any]) -> dict[str, Any]:
        return {
            "quality": "weak",
            "ready_for_decision": False,
            "sources": [],
            "sections": {},
            "missing_topics": ["deep research budget not allocated to this event"],
            "fallback_tasks": ["Keep as WATCH unless a later bounded research pass enriches this event."],
            "note": "Event was discovered/priced but not deep-researched in this bounded model slice.",
        }

    @staticmethod
    def _failed(event: dict[str, Any], exc: Exception) -> dict[str, Any]:
        return {
            "quality": "weak",
            "ready_for_decision": False,
            "sources": [],
            "sections": {},
            "missing_topics": ["automatic evidence build failed"],
            "source_failures": [f"{type(exc).__name__}: {str(exc)[:240]}"],
            "fallback_tasks": ["Research Scout should rebuild this event's evidence from verified public/official sources."],
            "note": "Do not auto-promote this event until evidence is rebuilt.",
        }


__all__ = ["CandidateEvidenceBuilder", "EvidenceBuildResult"]
