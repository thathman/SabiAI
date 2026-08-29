from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable

from sabiai.odds import expected_value_pct, implied_probability, minimum_decimal_odds


class CrossSportDecisionPass:
    """Rank exact price-bound candidates while preserving sport/competition breadth."""

    def __init__(
        self,
        *,
        max_recommendations: int = 18,
        max_per_sport: int = 3,
        max_per_scope: int = 2,
        minimum_confidence: float = 55.0,
        minimum_edge: float = 1.0,
        minimum_expected_value_pct: float = 1.0,
    ):
        self.max_recommendations = max(1, int(max_recommendations))
        self.max_per_sport = max(1, int(max_per_sport))
        self.max_per_scope = max(1, int(max_per_scope))
        self.minimum_confidence = float(minimum_confidence)
        self.minimum_edge = float(minimum_edge)
        self.minimum_expected_value_pct = float(minimum_expected_value_pct)

    def select(self, recommendations: Iterable[dict[str, Any]]) -> dict[str, Any]:
        rows: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str, str]] = set()
        for item in recommendations:
            if not isinstance(item, dict):
                continue
            try:
                odds = float(item.get("decimal_odds"))
                confidence = float(item.get("confidence_pct"))
            except (TypeError, ValueError):
                continue
            if odds <= 1 or not 0 <= confidence <= 100:
                continue
            estimated = _number(item.get("estimated_probability_pct"))
            if estimated is None:
                estimated = confidence
            implied = implied_probability(odds) * 100.0
            edge = estimated - implied
            try:
                ev = float(item.get("expected_value_pct"))
            except (TypeError, ValueError):
                ev = expected_value_pct(estimated / 100.0, odds)
            break_even = minimum_decimal_odds(estimated / 100.0) if estimated > 0 else float("inf")
            row = dict(item)
            row["implied_probability_pct"] = round(implied, 2)
            row["estimated_probability_pct"] = round(estimated, 2)
            row["value_edge_pct"] = round(edge, 2)
            row["expected_value_pct"] = round(ev, 2)
            row["minimum_break_even_odds"] = round(break_even, 3) if break_even != float("inf") else None
            row["decision_state"] = self._decision_state(
                confidence=confidence,
                edge=edge,
                ev=ev,
            )
            key = (
                str(row.get("event") or "").casefold(),
                str(row.get("market") or "").casefold(),
                str(row.get("pick") or "").casefold(),
                str(row.get("bookmaker") or "").casefold(),
            )
            if key in seen:
                continue
            seen.add(key)
            rows.append(row)
        rows.sort(key=_rank_key)
        qualified = [row for row in rows if row["decision_state"] == "BET"]
        selected: list[dict[str, Any]] = []
        sport_counts: defaultdict[str, int] = defaultdict(int)
        scope_counts: defaultdict[tuple[str, str, str], int] = defaultdict(int)
        buckets: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in qualified:
            buckets[str(row.get("sport") or "Unresolved")].append(row)
        while len(selected) < self.max_recommendations and buckets:
            progressed = False
            for sport in sorted(list(buckets)):
                bucket = buckets[sport]
                while bucket:
                    row = bucket.pop(0)
                    scope = (
                        sport,
                        str(row.get("country") or "Unresolved"),
                        str(row.get("competition") or "Unresolved"),
                    )
                    if sport_counts[sport] >= self.max_per_sport or scope_counts[scope] >= self.max_per_scope:
                        continue
                    selected.append(row)
                    sport_counts[sport] += 1
                    scope_counts[scope] += 1
                    progressed = True
                    break
                if not bucket:
                    buckets.pop(sport, None)
                if len(selected) >= self.max_recommendations:
                    break
            if not progressed:
                break
        coverage = self._coverage(rows, selected)
        coverage["decision_states"] = {
            state: sum(1 for row in rows if row.get("decision_state") == state)
            for state in ("BET", "BET IF PRICE", "WATCH", "PASS")
        }
        return {"recommendations": selected, "all_recommendations": rows, "coverage": coverage}

    def _decision_state(self, *, confidence: float, edge: float, ev: float) -> str:
        if (
            confidence >= self.minimum_confidence
            and edge >= self.minimum_edge
            and ev >= self.minimum_expected_value_pct
        ):
            return "BET"
        # A high-confidence candidate whose current price is below its break-even
        # threshold is still useful context, but must wait for a better quote.
        if confidence >= self.minimum_confidence and (edge >= self.minimum_edge or ev < self.minimum_expected_value_pct):
            return "BET IF PRICE"
        if confidence >= max(0.0, self.minimum_confidence - 5.0) and ev >= -3.0:
            return "WATCH"
        return "PASS"

    @staticmethod
    def _coverage(all_rows: list[dict[str, Any]], selected: list[dict[str, Any]]) -> dict[str, Any]:
        scopes: defaultdict[tuple[str, str, str, str], dict[str, Any]] = defaultdict(
            lambda: {"events": 0, "candidates": 0, "selected": 0}
        )
        seen_events: set[tuple[str, str, str, str, str]] = set()
        for row in all_rows:
            key = tuple(
                str(row.get(field) or "Unresolved")
                for field in ("sport", "country", "competition", "division")
            )
            scopes[key]["candidates"] += 1
            event_key = (*key, str(row.get("event") or ""))
            if event_key not in seen_events:
                scopes[key]["events"] += 1
                seen_events.add(event_key)
        for row in selected:
            key = tuple(
                str(row.get(field) or "Unresolved")
                for field in ("sport", "country", "competition", "division")
            )
            scopes[key]["selected"] += 1
        return {
            "candidate_count": len(all_rows),
            "selected_count": len(selected),
            "sports": sorted({str(row.get("sport") or "Unresolved") for row in all_rows}),
            "scopes": [
                {
                    "sport": key[0],
                    "country": key[1],
                    "competition": key[2],
                    "division": key[3],
                    **value,
                }
                for key, value in sorted(scopes.items())
            ],
        }


def _number(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if 0 <= number <= 100 else None


def _rank_key(row: dict[str, Any]) -> tuple[float, float, float, float, str]:
    return (
        -float(row.get("expected_value_pct") or 0),
        -float(row.get("value_edge_pct") or 0),
        -float(row.get("confidence_pct") or 0),
        float(row.get("decimal_odds") or 99),
        str(row.get("event") or ""),
    )
