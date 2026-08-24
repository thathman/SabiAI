from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from sabiai.domain.models import decimal_odds


@dataclass(frozen=True, slots=True)
class SettlementRules:
    """The minimum rule fingerprint needed before prices can be treated as equivalent."""

    period: str = "full_event"
    includes_overtime: bool | None = None
    void_rule: str = "standard"
    line_key: str | None = None

    @property
    def key(self) -> tuple:
        return (self.period, self.includes_overtime, self.void_rule, self.line_key)


@dataclass(frozen=True, slots=True)
class PriceQuote:
    event_key: str
    market_key: str
    selection_key: str
    selection_label: str
    bookmaker: str
    odds: Decimal
    captured_at: datetime
    rules: SettlementRules = SettlementRules()

    def __post_init__(self) -> None:
        object.__setattr__(self, "odds", decimal_odds(self.odds))
        if self.captured_at.tzinfo is None:
            object.__setattr__(self, "captured_at", self.captured_at.replace(tzinfo=timezone.utc))


@dataclass(frozen=True, slots=True)
class StakeAllocation:
    selection_label: str
    bookmaker: str
    odds: Decimal
    stake: Decimal
    expected_return: Decimal


@dataclass(frozen=True, slots=True)
class ArbitrageResult:
    found: bool
    reason: str
    event_key: str
    market_key: str
    implied_total_pct: Decimal | None = None
    profit_pct: Decimal | None = None
    quotes: tuple[PriceQuote, ...] = ()
    allocations: tuple[StakeAllocation, ...] = ()
    total_stake: Decimal | None = None
    locked_return: Decimal | None = None
    locked_profit: Decimal | None = None


class ArbitrageEngine:
    """Find true cross-book price arbitrage after market/rule normalization."""

    def find(
        self,
        quotes: list[PriceQuote],
        expected_selections: list[str],
        *,
        total_stake: Decimal | str | float | None = None,
        max_age_seconds: int = 90,
        now: datetime | None = None,
    ) -> ArbitrageResult:
        if len(expected_selections) < 2:
            raise ValueError("At least two complete outcomes are required.")
        if len(set(expected_selections)) != len(expected_selections):
            raise ValueError("Expected selections must be unique.")
        if max_age_seconds < 0:
            raise ValueError("max_age_seconds cannot be negative.")
        if not quotes:
            return ArbitrageResult(False, "No prices supplied.", "", "")

        now = now or datetime.now(timezone.utc)
        event_keys = {quote.event_key for quote in quotes}
        market_keys = {quote.market_key for quote in quotes}
        if len(event_keys) != 1 or len(market_keys) != 1:
            return ArbitrageResult(False, "Prices are not for one normalized event and market.", "", "")
        event_key = next(iter(event_keys))
        market_key = next(iter(market_keys))

        fresh = []
        for quote in quotes:
            age = (now - quote.captured_at).total_seconds()
            if 0 <= age <= max_age_seconds:
                fresh.append(quote)
        if not fresh:
            return ArbitrageResult(False, "All supplied prices are stale.", event_key, market_key)

        groups: dict[tuple, list[PriceQuote]] = {}
        for quote in fresh:
            groups.setdefault(quote.rules.key, []).append(quote)

        candidates: list[tuple[Decimal, tuple[PriceQuote, ...]]] = []
        for same_rules in groups.values():
            best: list[PriceQuote] = []
            for selection in expected_selections:
                available = [quote for quote in same_rules if quote.selection_key == selection]
                if not available:
                    break
                best.append(max(available, key=lambda quote: quote.odds))
            if len(best) != len(expected_selections):
                continue
            implied = sum((Decimal("1") / quote.odds for quote in best), Decimal("0"))
            candidates.append((implied, tuple(best)))

        if not candidates:
            return ArbitrageResult(
                False,
                "No complete set of fresh prices shares the same settlement rules.",
                event_key,
                market_key,
            )

        implied, best_quotes = min(candidates, key=lambda item: item[0])
        implied_pct = (implied * Decimal("100")).quantize(Decimal("0.001"))
        if implied >= Decimal("1"):
            return ArbitrageResult(
                False,
                "The best compatible prices do not create an arbitrage.",
                event_key,
                market_key,
                implied_total_pct=implied_pct,
                quotes=best_quotes,
            )

        profit_pct = ((Decimal("1") / implied - Decimal("1")) * Decimal("100")).quantize(Decimal("0.001"))
        allocations: tuple[StakeAllocation, ...] = ()
        stake_value = None
        locked_return = None
        locked_profit = None
        if total_stake is not None:
            stake_value = Decimal(str(total_stake)).quantize(Decimal("0.01"))
            if stake_value <= 0:
                raise ValueError("Total stake must be greater than zero.")
            rows = []
            allocated = Decimal("0")
            for index, quote in enumerate(best_quotes):
                if index == len(best_quotes) - 1:
                    stake = stake_value - allocated
                else:
                    stake = (stake_value * (Decimal("1") / quote.odds) / implied).quantize(Decimal("0.01"))
                    allocated += stake
                rows.append(
                    StakeAllocation(
                        selection_label=quote.selection_label,
                        bookmaker=quote.bookmaker,
                        odds=quote.odds,
                        stake=stake,
                        expected_return=(stake * quote.odds).quantize(Decimal("0.01")),
                    )
                )
            allocations = tuple(rows)
            locked_return = min(row.expected_return for row in allocations)
            locked_profit = (locked_return - stake_value).quantize(Decimal("0.01"))

        return ArbitrageResult(
            True,
            "Compatible fresh prices cover every outcome for less than 100% implied probability.",
            event_key,
            market_key,
            implied_total_pct=implied_pct,
            profit_pct=profit_pct,
            quotes=best_quotes,
            allocations=allocations,
            total_stake=stake_value,
            locked_return=locked_return,
            locked_profit=locked_profit,
        )
