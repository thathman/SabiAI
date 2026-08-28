from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable


class CrossSportDecisionPass:
    """Rank fresh candidates while preserving sport and competition breadth."""

    def __init__(self, *, max_recommendations: int = 18, max_per_sport: int = 3, max_per_scope: int = 2,
                 minimum_confidence: float = 55.0, minimum_edge: float = 1.0):
        self.max_recommendations = max(1, int(max_recommendations))
        self.max_per_sport = max(1, int(max_per_sport))
        self.max_per_scope = max(1, int(max_per_scope))
        self.minimum_confidence = float(minimum_confidence)
        self.minimum_edge = float(minimum_edge)

    def select(self, recommendations: Iterable[dict[str, Any]]) -> dict[str, Any]:
        rows: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str]] = set()
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
            implied = 100.0 / odds
            estimated = _number(item.get("estimated_probability_pct")) or confidence
            edge = estimated - implied
            row = dict(item)
            row["implied_probability_pct"] = round(implied, 2)
            row["estimated_probability_pct"] = round(estimated, 2)
            row["value_edge_pct"] = round(edge, 2)
            key = (str(row.get("event") or "").casefold(), str(row.get("market") or "").casefold(), str(row.get("pick") or "").casefold())
            if key in seen:
                continue
            seen.add(key)
            rows.append(row)
        rows.sort(key=_rank_key)
        qualified = [row for row in rows if row["confidence_pct"] >= self.minimum_confidence and row["value_edge_pct"] >= self.minimum_edge]
        selected: list[dict[str, Any]] = []
        sport_counts: defaultdict[str, int] = defaultdict(int)
        scope_counts: defaultdict[tuple[str, str, str], int] = defaultdict(int)
        # Round-robin by sport first. A large football slate cannot crowd out
        # smaller sports that produced a qualifying edge.
        buckets: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in qualified:
            buckets[str(row.get("sport") or "Unresolved")].append(row)
        while len(selected) < self.max_recommendations and buckets:
            progressed = False
            for sport in sorted(list(buckets)):
                bucket = buckets[sport]
                while bucket:
                    row = bucket.pop(0)
                    scope = (sport, str(row.get("country") or "Unresolved"), str(row.get("competition") or "Unresolved"))
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
        return {"recommendations": selected, "all_recommendations": rows, "coverage": coverage}

    @staticmethod
    def _coverage(all_rows: list[dict[str, Any]], selected: list[dict[str, Any]]) -> dict[str, Any]:
        scopes: defaultdict[tuple[str, str, str, str], dict[str, Any]] = defaultdict(lambda: {"events": 0, "candidates": 0, "selected": 0})
        seen_events: set[tuple[str, str, str, str, str]] = set()
        for row in all_rows:
            key = tuple(str(row.get(field) or "Unresolved") for field in ("sport", "country", "competition", "division"))
            scopes[key]["candidates"] += 1
            event_key = (*key, str(row.get("event") or ""))
            if event_key not in seen_events:
                scopes[key]["events"] += 1
                seen_events.add(event_key)
        for row in selected:
            key = tuple(str(row.get(field) or "Unresolved") for field in ("sport", "country", "competition", "division"))
            scopes[key]["selected"] += 1
        return {"candidate_count": len(all_rows), "selected_count": len(selected), "sports": sorted({str(row.get("sport") or "Unresolved") for row in all_rows}),
                "scopes": [{"sport": key[0], "country": key[1], "competition": key[2], "division": key[3], **value} for key, value in sorted(scopes.items())]}


def _number(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if 0 <= number <= 100 else None


def _rank_key(row: dict[str, Any]) -> tuple[float, float, float, str]:
    return (-float(row.get("value_edge_pct") or 0), -float(row.get("confidence_pct") or 0), float(row.get("decimal_odds") or 99), str(row.get("event") or ""))
