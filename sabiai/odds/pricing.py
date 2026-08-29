from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import Any, Iterable, Mapping


def implied_probability(decimal_odds: float) -> float:
    odds = float(decimal_odds)
    if odds <= 1:
        raise ValueError("decimal_odds must be greater than 1.0")
    return 1.0 / odds


def market_margin(decimal_odds: Iterable[float]) -> float:
    probabilities = [implied_probability(value) for value in decimal_odds]
    if len(probabilities) < 2:
        raise ValueError("At least two outcomes are required to calculate market margin.")
    return sum(probabilities) - 1.0


def no_vig_probabilities(prices: Mapping[str, float]) -> dict[str, float]:
    if len(prices) < 2:
        raise ValueError("At least two outcomes are required to remove bookmaker margin.")
    implied = {str(label): implied_probability(float(odds)) for label, odds in prices.items()}
    total = sum(implied.values())
    if total <= 0:
        raise ValueError("Invalid implied-probability total.")
    return {label: value / total for label, value in implied.items()}


def fair_odds(probability: float) -> float:
    value = float(probability)
    if not 0 < value < 1:
        raise ValueError("probability must be between 0 and 1")
    return 1.0 / value


def expected_value_pct(probability: float, decimal_odds: float) -> float:
    p = float(probability)
    if not 0 <= p <= 1:
        raise ValueError("probability must be between 0 and 1")
    odds = float(decimal_odds)
    if odds <= 1:
        raise ValueError("decimal_odds must be greater than 1.0")
    return ((p * odds) - 1.0) * 100.0


def minimum_decimal_odds(probability: float, *, minimum_ev_pct: float = 0.0) -> float:
    p = float(probability)
    if not 0 < p <= 1:
        raise ValueError("probability must be greater than 0 and at most 1")
    required_return = 1.0 + (float(minimum_ev_pct) / 100.0)
    return required_return / p


def _norm(value: object) -> str:
    return "".join(ch for ch in str(value or "").casefold() if ch.isalnum())


def market_group_identity(row: Mapping[str, Any]) -> tuple[str, str, str, str, str]:
    """Market identity without outcome/selection.

    Equivalent outcomes must share family/metric/period/participant/line. Selection side or
    team/player name is intentionally excluded so the whole market can be de-vigged together.
    """
    return (
        str(row.get("family") or "other").casefold(),
        _norm(row.get("metric")),
        _norm(row.get("period")),
        _norm(row.get("participant")),
        str(row.get("line") if row.get("line") is not None else ""),
    )


def selection_identity(row: Mapping[str, Any]) -> str:
    side = _norm(row.get("side"))
    label = _norm(row.get("selection_label") or row.get("selection"))
    return side or label


@dataclass(frozen=True, slots=True)
class FairPrice:
    market_identity: tuple[str, str, str, str, str]
    selection: str
    fair_probability: float
    fair_decimal_odds: float
    contributing_books: int
    median_observed_odds: float
    best_observed_odds: float
    best_bookmaker: str
    median_book_margin_pct: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "market_identity": list(self.market_identity),
            "selection": self.selection,
            "fair_probability_pct": round(self.fair_probability * 100.0, 2),
            "fair_decimal_odds": round(self.fair_decimal_odds, 3),
            "contributing_books": self.contributing_books,
            "median_observed_odds": round(self.median_observed_odds, 3),
            "best_observed_odds": round(self.best_observed_odds, 3),
            "best_bookmaker": self.best_bookmaker,
            "median_book_margin_pct": round(self.median_book_margin_pct, 2),
        }


class ConsensusPricingEngine:
    """Derive a no-vig consensus baseline from exact equivalent bookmaker markets."""

    def fair_prices(self, offers: Iterable[Mapping[str, Any]]) -> list[FairPrice]:
        markets: dict[tuple[str, str, str, str, str], dict[str, list[Mapping[str, Any]]]] = {}
        for raw in offers:
            row = dict(raw)
            try:
                odds = float(row.get("decimal_odds"))
            except (TypeError, ValueError):
                continue
            selection = selection_identity(row)
            if odds <= 1 or not selection:
                continue
            market = market_group_identity(row)
            book = str(row.get("bookmaker") or row.get("source_name") or "unknown")
            markets.setdefault(market, {}).setdefault(book, []).append(row)

        output: list[FairPrice] = []
        for market_id, book_rows in markets.items():
            fair_by_selection: dict[str, list[float]] = {}
            observed_by_selection: dict[str, list[tuple[float, str]]] = {}
            margins: list[float] = []
            contributing_books: set[str] = set()
            for book, rows in book_rows.items():
                best_by_selection: dict[str, Mapping[str, Any]] = {}
                for row in rows:
                    selection = selection_identity(row)
                    current = best_by_selection.get(selection)
                    if current is None or float(row["decimal_odds"]) > float(current["decimal_odds"]):
                        best_by_selection[selection] = row
                if len(best_by_selection) < 2:
                    continue
                prices = {selection: float(row["decimal_odds"]) for selection, row in best_by_selection.items()}
                try:
                    fair = no_vig_probabilities(prices)
                    margins.append(market_margin(prices.values()) * 100.0)
                except ValueError:
                    continue
                contributing_books.add(book)
                for selection, probability in fair.items():
                    fair_by_selection.setdefault(selection, []).append(probability)
                    observed_by_selection.setdefault(selection, []).append((prices[selection], book))

            for selection, probabilities in fair_by_selection.items():
                observed = observed_by_selection.get(selection, [])
                if not observed:
                    continue
                p = float(median(probabilities))
                observed_prices = [price for price, _book in observed]
                best_price, best_book = max(observed, key=lambda pair: pair[0])
                output.append(
                    FairPrice(
                        market_identity=market_id,
                        selection=selection,
                        fair_probability=p,
                        fair_decimal_odds=fair_odds(p),
                        contributing_books=len(contributing_books),
                        median_observed_odds=float(median(observed_prices)),
                        best_observed_odds=float(best_price),
                        best_bookmaker=best_book,
                        median_book_margin_pct=float(median(margins)) if margins else 0.0,
                    )
                )
        output.sort(key=lambda row: (row.market_identity, row.selection))
        return output

    def lookup(self, offers: Iterable[Mapping[str, Any]]) -> dict[tuple[tuple[str, str, str, str, str], str], FairPrice]:
        return {(row.market_identity, row.selection): row for row in self.fair_prices(offers)}


@dataclass(frozen=True, slots=True)
class ValueAssessment:
    estimated_probability_pct: float
    action_decimal_odds: float
    raw_implied_probability_pct: float
    expected_value_pct: float
    minimum_break_even_odds: float
    consensus_probability_pct: float | None = None
    consensus_fair_odds: float | None = None
    probability_vs_consensus_pct: float | None = None

    def as_dict(self) -> dict[str, float | None]:
        return {
            "estimated_probability_pct": round(self.estimated_probability_pct, 2),
            "action_decimal_odds": round(self.action_decimal_odds, 3),
            "raw_implied_probability_pct": round(self.raw_implied_probability_pct, 2),
            "expected_value_pct": round(self.expected_value_pct, 2),
            "minimum_break_even_odds": round(self.minimum_break_even_odds, 3),
            "consensus_probability_pct": None if self.consensus_probability_pct is None else round(self.consensus_probability_pct, 2),
            "consensus_fair_odds": None if self.consensus_fair_odds is None else round(self.consensus_fair_odds, 3),
            "probability_vs_consensus_pct": None if self.probability_vs_consensus_pct is None else round(self.probability_vs_consensus_pct, 2),
        }


def assess_value(
    estimated_probability_pct: float,
    action_decimal_odds: float,
    *,
    consensus_probability_pct: float | None = None,
) -> ValueAssessment:
    estimated = float(estimated_probability_pct)
    if not 0 <= estimated <= 100:
        raise ValueError("estimated_probability_pct must be between 0 and 100")
    p = estimated / 100.0
    consensus = None if consensus_probability_pct is None else float(consensus_probability_pct)
    if consensus is not None and not 0 <= consensus <= 100:
        raise ValueError("consensus_probability_pct must be between 0 and 100")
    return ValueAssessment(
        estimated_probability_pct=estimated,
        action_decimal_odds=float(action_decimal_odds),
        raw_implied_probability_pct=implied_probability(float(action_decimal_odds)) * 100.0,
        expected_value_pct=expected_value_pct(p, float(action_decimal_odds)),
        minimum_break_even_odds=minimum_decimal_odds(p) if p > 0 else float("inf"),
        consensus_probability_pct=consensus,
        consensus_fair_odds=(fair_odds(consensus / 100.0) if consensus not in (None, 0.0, 100.0) else None),
        probability_vs_consensus_pct=(estimated - consensus if consensus is not None else None),
    )


__all__ = [
    "ConsensusPricingEngine",
    "FairPrice",
    "ValueAssessment",
    "assess_value",
    "expected_value_pct",
    "fair_odds",
    "implied_probability",
    "market_group_identity",
    "market_margin",
    "minimum_decimal_odds",
    "no_vig_probabilities",
    "selection_identity",
]
