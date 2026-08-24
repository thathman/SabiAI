from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field


def normalize_name(value: str) -> str:
    """Normalize names for matching without changing the user-facing spelling."""
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.casefold()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


@dataclass
class AliasResolver:
    """Resolve source/bookmaker naming differences to one canonical id."""

    _aliases: dict[str, str] = field(default_factory=dict)

    def add(self, canonical_id: str, *names: str) -> None:
        for name in names:
            key = normalize_name(name)
            if key:
                self._aliases[key] = canonical_id

    def resolve(self, name: str) -> str | None:
        return self._aliases.get(normalize_name(name))

    def require(self, name: str) -> str:
        result = self.resolve(name)
        if result is None:
            raise KeyError(f"No canonical match for {name!r}.")
        return result
