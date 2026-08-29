from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable


_SLUG = re.compile(r"[^a-z0-9]+")


def canonical_sport_slug(value: object) -> str:
    key = _SLUG.sub("_", str(value or "").strip().casefold()).strip("_")
    aliases = {
        "soccer": "football",
        "tabletennis": "table_tennis",
        "ping_pong": "table_tennis",
        "hockey": "ice_hockey",
        "american_football": "american_football",
        "nfl": "american_football",
        "afl": "aussie_rules",
        "australian_rules_football": "aussie_rules",
        "mixed_martial_arts": "mma",
        "motor_racing": "motorsport",
        "rugby_union": "rugby",
    }
    return aliases.get(key, key or "unknown")


@dataclass(frozen=True, slots=True)
class EngineSportProfile:
    slug: str
    name: str
    event_shape: str
    discovery_horizon_hours: int
    minimum_market_families: tuple[str, ...]
    deep_market_families: tuple[str, ...]
    evidence_topics: tuple[str, ...]
    settlement_concerns: tuple[str, ...]
    primary_metrics: tuple[str, ...] = ()
    requires_weather: bool = False
    requires_surface_or_venue: bool = False
    requires_lineup_or_roster: bool = False
    draw_possible: bool | None = None
    needs_discovery: bool = False

    @property
    def all_market_families(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys((*self.minimum_market_families, *self.deep_market_families)))


def _profile(
    slug: str,
    name: str,
    *,
    event_shape: str = "team",
    horizon: int = 72,
    minimum: Iterable[str] = ("winner", "handicap", "total"),
    deep: Iterable[str] = (),
    evidence: Iterable[str] = (),
    settlement: Iterable[str] = (),
    metrics: Iterable[str] = (),
    weather: bool = False,
    venue: bool = False,
    roster: bool = False,
    draw: bool | None = None,
) -> EngineSportProfile:
    return EngineSportProfile(
        slug=slug,
        name=name,
        event_shape=event_shape,
        discovery_horizon_hours=horizon,
        minimum_market_families=tuple(minimum),
        deep_market_families=tuple(deep),
        evidence_topics=tuple(evidence),
        settlement_concerns=tuple(settlement),
        primary_metrics=tuple(metrics),
        requires_weather=weather,
        requires_surface_or_venue=venue,
        requires_lineup_or_roster=roster,
        draw_possible=draw,
    )


_PROFILES = (
    _profile("football", "Football", deep=("draw_no_bet", "btts", "team_total", "corners", "cards", "player_prop", "correct_score"), evidence=("recent form", "home/away form", "lineups and absences", "scoring/conceding profile", "rest and travel", "match context"), settlement=("regulation vs extra time", "abandonment", "postponement"), metrics=("goals", "corners", "cards", "shots", "shots on target"), roster=True, draw=True),
    _profile("basketball", "Basketball", deep=("team_total", "player_prop", "period_market"), evidence=("recent form", "starters and absences", "minutes and roles", "pace", "rest and travel"), settlement=("overtime inclusion", "shortened game", "player participation"), metrics=("points", "rebounds", "assists", "three-pointers", "turnovers"), roster=True, draw=False),
    _profile("volleyball", "Volleyball", deep=("set_market", "team_total"), evidence=("recent form", "sets won/lost", "team availability", "serving/receiving"), settlement=("match format", "retirement/withdrawal", "set handicap rules"), metrics=("sets", "points", "aces", "blocks"), roster=True, draw=False),
    _profile("tennis", "Tennis", event_shape="head_to_head", deep=("set_market", "team_total", "player_prop"), evidence=("recent form", "surface", "fitness", "serve/return profile", "head-to-head"), settlement=("retirement", "walkover", "match format", "completed set requirements"), metrics=("sets", "games", "aces", "double faults", "break points"), venue=True, draw=False),
    _profile("table_tennis", "Table Tennis", event_shape="head_to_head", deep=("set_market",), evidence=("recent form", "set performance", "head-to-head", "competition format"), settlement=("retirement", "match format"), metrics=("sets", "points"), draw=False),
    _profile("baseball", "Baseball", deep=("team_total", "player_prop", "period_market"), evidence=("starting pitchers", "bullpen availability", "batting form", "venue/weather", "travel/rest"), settlement=("extra innings inclusion", "listed pitcher rules", "shortened game", "postponement"), metrics=("runs", "hits", "strikeouts", "walks", "home runs"), weather=True, venue=True, roster=True),
    _profile("ice_hockey", "Ice Hockey", deep=("team_total", "player_prop", "period_market"), evidence=("goaltender status", "recent form", "team availability", "rest/travel"), settlement=("overtime/shootout inclusion", "regulation-only markets", "shortened game"), metrics=("goals", "shots", "saves", "penalties"), roster=True),
    _profile("cricket", "Cricket", deep=("team_total", "player_prop", "period_market"), evidence=("format", "pitch/venue", "weather", "batting/bowling roles", "team availability", "recent form"), settlement=("DLS/reduced overs", "no result", "super over inclusion", "player participation"), metrics=("runs", "wickets", "boundaries", "overs"), weather=True, venue=True, roster=True),
    _profile("esports", "Esports", deep=("map_market", "player_prop", "correct_score"), evidence=("game title", "patch/version", "roster/stand-ins", "map pool/veto", "match format", "opponent-adjusted form"), settlement=("map advantage", "forfeit", "roster substitution", "match format"), metrics=("maps", "rounds", "kills"), roster=True),
    _profile("golf", "Golf", event_shape="field", horizon=168, minimum=("outright", "placement", "matchup"), deep=("make_cut", "player_prop"), evidence=("course fit", "recent form", "weather/tee wave", "course history", "player availability"), settlement=("dead heat", "withdrawal", "cut rules", "reduced event"), metrics=("score", "birdies", "bogeys"), weather=True, venue=True),
    _profile("handball", "Handball", deep=("team_total", "period_market"), evidence=("recent form", "home/away form", "team availability", "scoring/conceding profile"), settlement=("extra time inclusion", "abandonment"), metrics=("goals", "saves", "penalties"), roster=True, draw=True),
    _profile("rugby", "Rugby", deep=("team_total", "player_prop", "period_market"), evidence=("recent form", "team selection", "injuries", "venue", "rest/travel"), settlement=("extra time inclusion", "draw markets", "abandonment"), metrics=("points", "tries", "penalties"), weather=True, venue=True, roster=True, draw=True),
    _profile("darts", "Darts", event_shape="head_to_head", deep=("set_market", "player_prop", "correct_score"), evidence=("recent form", "format", "scoring averages", "checkout performance"), settlement=("match format", "walkover/retirement"), metrics=("legs", "sets", "180s", "checkout"), draw=False),
    _profile("snooker", "Snooker", event_shape="head_to_head", deep=("set_market", "player_prop", "correct_score"), evidence=("recent form", "frame performance", "tournament format", "head-to-head"), settlement=("match format", "retirement/walkover"), metrics=("frames", "breaks"), draw=False),
    _profile("badminton", "Badminton", event_shape="head_to_head", deep=("set_market",), evidence=("recent form", "fitness", "game performance", "head-to-head"), settlement=("retirement", "walkover", "match format"), metrics=("games", "points"), draw=False),
    _profile("mma", "MMA", event_shape="fight", horizon=336, minimum=("winner", "method", "total_rounds"), deep=("player_prop",), evidence=("recent fights", "style matchup", "weight/camp news", "injuries/late changes", "fight format"), settlement=("draw/no contest", "round started/completed rules", "method classification"), metrics=("rounds", "significant strikes", "takedowns")),
    _profile("boxing", "Boxing", event_shape="fight", horizon=336, minimum=("winner", "method", "total_rounds"), deep=("player_prop",), evidence=("recent fights", "style matchup", "weight/camp news", "injuries", "scheduled rounds"), settlement=("draw/no contest", "round started/completed rules", "technical decision", "method classification"), metrics=("rounds", "knockdowns")),
    _profile("motorsport", "Motorsport", event_shape="race", horizon=168, minimum=("outright", "placement", "matchup"), deep=("player_prop",), evidence=("series/circuit", "qualifying", "weather", "car/team form", "grid penalties", "reliability"), settlement=("classification requirement", "dead heat", "DNS/DNF", "session-specific rules"), metrics=("position", "laps", "pit stops"), weather=True, venue=True),
    _profile("cycling", "Cycling", event_shape="race", horizon=168, minimum=("outright", "placement", "matchup"), deep=("player_prop",), evidence=("race profile", "rider form", "team role", "weather", "terrain", "recent workload"), settlement=("classification requirement", "dead heat", "DNS/DNF", "stage vs overall"), metrics=("time", "position", "points"), weather=True, venue=True),
    _profile("futsal", "Futsal", deep=("team_total", "period_market"), evidence=("recent form", "team availability", "scoring/conceding profile", "competition context"), settlement=("extra time inclusion", "abandonment"), metrics=("goals", "shots"), roster=True, draw=True),
    _profile("water_polo", "Water Polo", deep=("team_total", "period_market"), evidence=("recent form", "team availability", "scoring/conceding profile"), settlement=("overtime/penalties inclusion", "abandonment"), metrics=("goals",), roster=True),
    _profile("beach_volleyball", "Beach Volleyball", event_shape="head_to_head", deep=("set_market",), evidence=("pair form", "set performance", "conditions", "head-to-head"), settlement=("retirement", "match format"), metrics=("sets", "points"), weather=True, venue=True, draw=False),
    _profile("padel", "Padel", event_shape="head_to_head", deep=("set_market",), evidence=("pair form", "surface/venue", "recent form", "head-to-head"), settlement=("retirement", "walkover", "match format"), metrics=("sets", "games"), venue=True, draw=False),
    _profile("floorball", "Floorball", deep=("team_total", "period_market"), evidence=("recent form", "team availability", "scoring/conceding profile"), settlement=("overtime inclusion", "abandonment"), metrics=("goals", "shots"), roster=True),
    _profile("aussie_rules", "Aussie Rules", deep=("team_total", "player_prop", "period_market"), evidence=("recent form", "venue", "team availability", "rest/travel"), settlement=("draw/tie rules", "shortened game"), metrics=("points", "goals", "behinds"), weather=True, venue=True, roster=True),
    _profile("american_football", "American Football", deep=("team_total", "player_prop", "period_market"), evidence=("quarterback status", "injuries", "offensive/defensive efficiency", "rest/travel", "weather"), settlement=("overtime inclusion", "push rules", "shortened game", "player participation"), metrics=("points", "touchdowns", "passing yards", "rushing yards", "receiving yards"), weather=True, venue=True, roster=True, draw=False),
    _profile("horse_racing", "Horse Racing", event_shape="race", horizon=168, minimum=("outright", "placement"), deep=("matchup", "player_prop"), evidence=("form", "going/surface", "distance", "draw/track position", "weight/class", "jockey/trainer"), settlement=("dead heat", "non-runner", "rule 4/deductions", "place terms"), metrics=("position", "distance", "time"), weather=True, venue=True, draw=False),
    _profile("greyhound_racing", "Greyhound Racing", event_shape="race", horizon=168, minimum=("outright", "placement"), deep=("matchup",), evidence=("recent form", "trap/draw", "distance", "track", "grade"), settlement=("dead heat", "non-runner", "void race", "place terms"), metrics=("position", "time"), venue=True, draw=False),
    _profile("rugby_league", "Rugby League", deep=("team_total", "player_prop", "period_market"), evidence=("recent form", "team selection", "injuries", "venue", "rest/travel"), settlement=("golden point/extra time inclusion", "draw markets", "abandonment"), metrics=("points", "tries", "goals"), weather=True, venue=True, roster=True, draw=True),
    _profile("athletics", "Athletics", event_shape="field", horizon=168, minimum=("outright", "placement", "matchup"), deep=("player_prop",), evidence=("event discipline", "recent marks/times", "qualification status", "venue/conditions", "injury status"), settlement=("dead heat", "qualification/disqualification", "DNS/DNF", "heat vs final"), metrics=("time", "distance", "height", "position"), weather=True, venue=True, draw=False),
    _profile("winter_sports", "Winter Sports", event_shape="field", horizon=168, minimum=("outright", "placement", "matchup"), deep=("player_prop",), evidence=("discipline", "recent form", "course/venue", "weather/snow", "start order", "equipment/team context"), settlement=("dead heat", "DNS/DNF", "qualification", "discipline-specific format"), metrics=("time", "points", "distance", "position"), weather=True, venue=True, draw=False),
)

_PROFILES_BY_SLUG = {profile.slug: profile for profile in _PROFILES}


def sport_engine_profile(value: object) -> EngineSportProfile:
    slug = canonical_sport_slug(value)
    profile = _PROFILES_BY_SLUG.get(slug)
    if profile:
        return profile
    return EngineSportProfile(
        slug=slug,
        name=str(value or "Unknown sport").strip() or "Unknown sport",
        event_shape="unknown",
        discovery_horizon_hours=72,
        minimum_market_families=("winner",),
        deep_market_families=(),
        evidence_topics=(
            "learn the scoring and event format",
            "identify official/public sources",
            "identify bookmaker market meaning",
            "identify settlement rules",
        ),
        settlement_concerns=("bookmaker-specific rules must be verified",),
        needs_discovery=True,
    )


def engine_sport_profiles() -> tuple[EngineSportProfile, ...]:
    return tuple(sorted(_PROFILES, key=lambda item: item.name.casefold()))


__all__ = [
    "EngineSportProfile",
    "canonical_sport_slug",
    "engine_sport_profiles",
    "sport_engine_profile",
]
