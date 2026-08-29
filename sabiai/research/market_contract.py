from __future__ import annotations

from typing import Iterable

from sabiai.sports import sport_engine_profile


def expected_market_families(sport: str) -> tuple[str, ...]:
    """Canonical minimum market contract for the sport."""
    return sport_engine_profile(sport).minimum_market_families


def market_family_gap(sport: str, available: Iterable[str]) -> list[str]:
    present = {str(item).casefold() for item in available}
    return [family for family in expected_market_families(sport) if family not in present]


__all__ = ["expected_market_families", "market_family_gap"]
