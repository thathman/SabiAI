from __future__ import annotations

from sabiai.sources import SourceBundle
from sabiai.storage import CoverageStore, SabiDatabase

from .discovery import CoverageDiscoveryEngine as BaseCoverageDiscoveryEngine, DiscoveryResult


class CoverageDiscoveryEngine(BaseCoverageDiscoveryEngine):
    """Runtime V2.4 discovery engine using the hardened provider-ID/fresh-price store."""

    def __init__(self, settings, database: SabiDatabase, bundle: SourceBundle | None = None):
        super().__init__(settings, database, bundle=bundle)
        self.store = CoverageStore(database)


__all__ = ["CoverageDiscoveryEngine", "DiscoveryResult"]
