from __future__ import annotations

from dataclasses import dataclass, field

from sabiai.domain.models import Bookmaker


@dataclass
class BookmakerRegistry:
    """Canonical bookmaker names and aliases.

    Capabilities are deliberately conservative: an adapter must prove a capability before it
    is enabled here. Canonical bookmakers use stable IDs so saved history remains consistent
    across processes and deployments.
    """

    _items: dict[str, Bookmaker] = field(default_factory=dict)
    _aliases: dict[str, str] = field(default_factory=dict)

    def register(self, bookmaker: Bookmaker) -> None:
        self._items[bookmaker.slug] = bookmaker
        for alias in {bookmaker.name, bookmaker.slug, *bookmaker.aliases}:
            self._aliases[self._norm(alias)] = bookmaker.slug

    def resolve(self, value: str) -> Bookmaker | None:
        slug = self._aliases.get(self._norm(value))
        return self._items.get(slug) if slug else None

    def all(self) -> list[Bookmaker]:
        return list(self._items.values())

    @staticmethod
    def _norm(value: str) -> str:
        return "".join(ch for ch in value.casefold() if ch.isalnum())


def default_bookmakers() -> BookmakerRegistry:
    registry = BookmakerRegistry()
    registry.register(
        Bookmaker(
            id="bookmaker_sportybet",
            name="SportyBet",
            slug="sportybet",
            aliases={"Sporty Bet"},
        )
    )
    registry.register(
        Bookmaker(
            id="bookmaker_bet9ja",
            name="Bet9ja",
            slug="bet9ja",
            aliases={"Bet 9ja"},
        )
    )
    registry.register(
        Bookmaker(
            id="bookmaker_1xbet",
            name="1xBet",
            slug="1xbet",
            aliases={"1 x bet", "1X Bet"},
        )
    )
    registry.register(
        Bookmaker(
            id="bookmaker_stake",
            name="Stake",
            slug="stake",
        )
    )
    return registry
