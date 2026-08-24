from __future__ import annotations

from dataclasses import dataclass, field
import re
import unicodedata


def slugify(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(ch for ch in value if not unicodedata.combining(ch)).casefold()
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return value or "unknown-sport"


@dataclass(frozen=True, slots=True)
class SportProfile:
    name: str
    slug: str
    aliases: tuple[str, ...] = ()
    participant_shape: str = "team_or_individual"
    event_parts: tuple[str, ...] = ()
    common_metrics: tuple[str, ...] = ()
    research_topics: tuple[str, ...] = ()
    draw_possible: bool | None = None
    needs_discovery: bool = False


@dataclass
class SportRegistry:
    _profiles: dict[str, SportProfile] = field(default_factory=dict)
    _aliases: dict[str, str] = field(default_factory=dict)

    def register(self, profile: SportProfile) -> None:
        self._profiles[profile.slug] = profile
        for alias in {profile.name, profile.slug, *profile.aliases}:
            self._aliases[slugify(alias)] = profile.slug

    def resolve(self, value: str) -> SportProfile:
        key = slugify(value)
        slug = self._aliases.get(key)
        if slug:
            return self._profiles[slug]
        # Unknown sports are discoverable, not unsupported.
        return SportProfile(
            name=(value or "Unknown sport").strip() or "Unknown sport",
            slug=key,
            research_topics=(
                "learn the sport and competition rules",
                "identify how the event is scored and settled",
                "find official/public data sources",
                "identify the market meaning before comparing prices",
            ),
            needs_discovery=True,
        )

    def all(self) -> list[SportProfile]:
        return sorted(self._profiles.values(), key=lambda profile: profile.name.casefold())


def _p(name, slug, *, aliases=(), participant="team_or_individual", parts=(), metrics=(), topics=(), draw=None):
    return SportProfile(name, slug, tuple(aliases), participant, tuple(parts), tuple(metrics), tuple(topics), draw)


def default_sports() -> SportRegistry:
    registry = SportRegistry()
    profiles = [
        _p("Football", "football", aliases=("soccer",), participant="team", parts=("first half", "second half", "extra time", "penalties"), metrics=("goals", "corners", "cards", "shots", "shots on target", "fouls", "offsides"), topics=("home and away form", "team availability", "expected lineups", "scoring and conceding form", "match context"), draw=True),
        _p("Basketball", "basketball", participant="team", parts=("quarters", "halves", "overtime"), metrics=("points", "rebounds", "assists", "three-pointers", "turnovers", "blocks", "steals"), topics=("recent form", "home and away form", "starters and absences", "minutes and roles", "rest and travel", "pace and scoring profile"), draw=False),
        _p("Volleyball", "volleyball", participant="team", parts=("sets",), metrics=("sets", "points", "aces", "blocks"), topics=("recent match form", "sets won and lost", "straight-set results", "team availability", "serving and receiving where available"), draw=False),
        _p("Tennis", "tennis", participant="individual_or_pair", parts=("sets", "games"), metrics=("sets", "games", "aces", "double faults", "break points"), topics=("recent form", "surface", "fitness and availability", "serve and return form", "head-to-head when useful"), draw=False),
        _p("Table Tennis", "table-tennis", aliases=("ping pong",), participant="individual_or_pair", parts=("sets",), metrics=("sets", "points"), topics=("recent match form", "set performance", "head-to-head when useful", "competition format"), draw=False),
        _p("Baseball", "baseball", participant="team", parts=("innings", "extra innings"), metrics=("runs", "hits", "strikeouts", "walks", "home runs"), topics=("starting pitchers", "bullpen availability", "recent batting form", "venue and weather where relevant", "travel and rest"), draw=None),
        _p("Ice Hockey", "ice-hockey", aliases=("hockey",), participant="team", parts=("periods", "overtime", "shootout"), metrics=("goals", "shots", "saves", "penalties"), topics=("goalkeeper status", "recent form", "home and away form", "team availability", "rest and travel"), draw=None),
        _p("Cricket", "cricket", participant="team", parts=("innings",), metrics=("runs", "wickets", "boundaries", "overs"), topics=("match format", "venue and pitch", "weather", "batting and bowling roles", "team availability", "recent form"), draw=None),
        _p("Esports", "esports", aliases=("e-sports",), participant="team_or_individual", parts=("maps", "rounds"), metrics=("maps", "rounds", "kills"), topics=("game title", "patch or version", "roster and stand-ins", "map pool and veto", "match format", "recent opponent-quality-adjusted form"), draw=None),
        _p("Golf", "golf", participant="field", parts=("rounds", "holes"), metrics=("score", "birdies", "bogeys"), topics=("course fit", "recent form", "weather and tee-time wave", "course history when useful", "player availability"), draw=None),
        _p("Handball", "handball", participant="team", parts=("halves",), metrics=("goals", "saves", "penalties"), topics=("recent form", "home and away form", "team availability", "scoring and conceding form"), draw=True),
        _p("Rugby", "rugby", participant="team", parts=("halves",), metrics=("points", "tries", "penalties"), topics=("recent form", "team selection", "injuries", "venue", "rest and travel"), draw=True),
        _p("Darts", "darts", participant="individual_or_team", parts=("legs", "sets"), metrics=("legs", "sets", "180s", "checkout"), topics=("recent match form", "format", "scoring averages where available", "checkout performance"), draw=False),
        _p("Snooker", "snooker", participant="individual", parts=("frames",), metrics=("frames", "breaks"), topics=("recent form", "frame performance", "tournament format", "head-to-head when useful"), draw=False),
        _p("Badminton", "badminton", participant="individual_or_pair", parts=("games",), metrics=("games", "points"), topics=("recent form", "fitness", "game performance", "head-to-head when useful"), draw=False),
        _p("MMA", "mma", aliases=("mixed martial arts",), participant="individual", parts=("rounds",), metrics=("rounds", "significant strikes", "takedowns"), topics=("recent fights", "style matchup", "weight and camp news", "injuries or late changes", "fight format"), draw=None),
        _p("Boxing", "boxing", participant="individual", parts=("rounds",), metrics=("rounds", "knockdowns"), topics=("recent fights", "style matchup", "weight and camp news", "injuries", "scheduled rounds"), draw=None),
        _p("Motorsport", "motorsport", aliases=("motor racing",), participant="field", parts=("sessions", "laps"), metrics=("position", "laps", "pit stops"), topics=("series and circuit", "qualifying", "weather", "car/team form", "grid penalties", "reliability"), draw=False),
        _p("Cycling", "cycling", participant="field", parts=("stages",), metrics=("time", "position", "points"), topics=("race profile", "rider form", "team role", "weather", "terrain", "recent workload"), draw=False),
        _p("Futsal", "futsal", participant="team", parts=("halves",), metrics=("goals", "shots"), topics=("recent form", "team availability", "scoring and conceding form", "competition context"), draw=True),
        _p("Water Polo", "water-polo", participant="team", parts=("quarters",), metrics=("goals",), topics=("recent form", "team availability", "scoring and conceding form"), draw=None),
        _p("Beach Volleyball", "beach-volleyball", participant="pair", parts=("sets",), metrics=("sets", "points"), topics=("pair form", "set performance", "conditions", "head-to-head when useful"), draw=False),
        _p("Padel", "padel", participant="pair", parts=("sets", "games"), metrics=("sets", "games"), topics=("pair form", "surface/venue where relevant", "recent match form", "head-to-head when useful"), draw=False),
        _p("Floorball", "floorball", participant="team", parts=("periods",), metrics=("goals", "shots"), topics=("recent form", "team availability", "scoring and conceding form"), draw=None),
        _p("Aussie Rules", "aussie-rules", aliases=("australian rules football", "afl"), participant="team", parts=("quarters",), metrics=("points", "goals", "behinds"), topics=("recent form", "venue", "team availability", "rest and travel"), draw=None),
    ]
    for profile in profiles:
        registry.register(profile)
    return registry
