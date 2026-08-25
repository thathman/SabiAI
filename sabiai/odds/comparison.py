from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from .arbitrage import PriceQuote


@dataclass(frozen=True, slots=True)
class ComparedPrice:
    bookmaker: str
    odds: Decimal
    captured_at: datetime
    age_seconds: int


@dataclass(frozen=True, slots=True)
class SelectionPriceComparison:
    selection_key: str
    selection_label: str
    best_bookmaker: str
    best_odds: Decimal
    prices: tuple[ComparedPrice, ...]
    price_gap: Decimal


@dataclass(slots=True)
class PriceComparisonResult:
    event_key: str
    market_key: str
    selections: list[SelectionPriceComparison] = field(default_factory=list)
    rejected_stale: int = 0
    rejected_rule_mismatch: int = 0
    rule_key: tuple | None = None


class PriceComparisonService:
    """Compare decimal prices across bookmakers for one normalized market.

    Unlike arbitrage, this does not need every possible outcome. It answers the simpler user
    question: for each requested selection, which compatible bookmaker currently has the best
    decimal price?
    """

    def compare(
        self,
        quotes: list[PriceQuote],
        *,
        max_age_seconds: int = 180,
        now: datetime | None = None,
    ) -> PriceComparisonResult:
        if max_age_seconds < 0:
            raise ValueError("max_age_seconds cannot be negative.")
        if not quotes:
            return PriceComparisonResult("", "")
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        now = now.astimezone(timezone.utc)

        event_keys = {quote.event_key for quote in quotes}
        market_keys = {quote.market_key for quote in quotes}
        if len(event_keys) != 1 or len(market_keys) != 1:
            raise ValueError("Price comparison needs one normalized event and market.")
        event_key = next(iter(event_keys))
        market_key = next(iter(market_keys))

        fresh: list[tuple[PriceQuote, int]] = []
        stale = 0
        for quote in quotes:
            age = int((now - quote.captured_at).total_seconds())
            if age < 0 or age > max_age_seconds:
                stale += 1
                continue
            fresh.append((quote, age))
        result = PriceComparisonResult(event_key, market_key, rejected_stale=stale)
        if not fresh:
            return result

        # Prefer the rule fingerprint with the broadest bookmaker/selection coverage. Prices
        # from incompatible regulation/overtime/void/line rules are never mixed together.
        rule_groups: dict[tuple, list[tuple[PriceQuote, int]]] = {}
        for item in fresh:
            rule_groups.setdefault(item[0].rules.key, []).append(item)
        selected_rule, compatible = max(
            rule_groups.items(),
            key=lambda item: (
                len({row[0].selection_key for row in item[1]}),
                len({row[0].bookmaker for row in item[1]}),
                len(item[1]),
            ),
        )
        result.rule_key = selected_rule
        result.rejected_rule_mismatch = len(fresh) - len(compatible)

        groups: dict[str, list[tuple[PriceQuote, int]]] = {}
        for quote, age in compatible:
            groups.setdefault(quote.selection_key, []).append((quote, age))

        for selection_key, rows in sorted(groups.items()):
            # Keep only the newest occurrence from each bookmaker, then sort by price.
            newest_by_book: dict[str, tuple[PriceQuote, int]] = {}
            for row in rows:
                quote = row[0]
                current = newest_by_book.get(quote.bookmaker)
                if current is None or quote.captured_at > current[0].captured_at:
                    newest_by_book[quote.bookmaker] = row
            ordered = sorted(
                newest_by_book.values(),
                key=lambda row: (-row[0].odds, row[0].bookmaker.casefold()),
            )
            best = ordered[0][0]
            worst_odds = min(row[0].odds for row in ordered)
            result.selections.append(
                SelectionPriceComparison(
                    selection_key=selection_key,
                    selection_label=best.selection_label,
                    best_bookmaker=best.bookmaker,
                    best_odds=best.odds,
                    prices=tuple(
                        ComparedPrice(
                            bookmaker=quote.bookmaker,
                            odds=quote.odds,
                            captured_at=quote.captured_at,
                            age_seconds=age,
                        )
                        for quote, age in ordered
                    ),
                    price_gap=(best.odds - worst_odds).quantize(Decimal("0.001")),
                )
            )
        return result
