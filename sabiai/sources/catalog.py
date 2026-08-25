from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from sabiai.config import Settings

from .football_data import FootballDataAdapter
from .registry import Source, SourceCost, SourceKind, SourceRegistry
from .service import Fetcher
from .thesportsdb import TheSportsDBAdapter


@dataclass(frozen=True)
class SourceBundle:
    registry: SourceRegistry
    fetchers: Mapping[str, Fetcher]


def default_source_bundle(settings: Settings) -> SourceBundle:
    """Build the default source set without requiring a paid provider.

    OpenClaw Browser/Search are registered as later free fallbacks, but their actual fetchers
    are supplied by OpenClaw when it orchestrates those actions. Built-in Python adapters are
    only for sources that are safe to call directly from the Sabi Boy runtime.
    """

    registry = SourceRegistry()
    fetchers: dict[str, Fetcher] = {}

    sportsdb = TheSportsDBAdapter(api_key=settings.thesportsdb_key)
    registry.register(sportsdb.source)
    fetchers[sportsdb.name] = sportsdb.fetch

    if settings.football_data_token:
        football_data = FootballDataAdapter(token=settings.football_data_token)
        registry.register(football_data.source)
        fetchers[football_data.name] = football_data.fetch

    registry.register(
        Source(
            name="OpenClaw Browser",
            kind=SourceKind.BROWSER,
            cost=SourceCost.FREE,
            capabilities=set(),
            priority_bias=0,
            notes="Interactive public-web fallback executed by OpenClaw, not by the Python source client.",
        )
    )
    registry.register(
        Source(
            name="OpenClaw Search",
            kind=SourceKind.SEARCH,
            cost=SourceCost.FREE,
            capabilities=set(),
            priority_bias=0,
            notes="General source-discovery fallback executed by OpenClaw after direct public sources are insufficient.",
        )
    )

    return SourceBundle(registry=registry, fetchers=fetchers)
