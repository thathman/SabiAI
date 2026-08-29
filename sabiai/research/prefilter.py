from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from statistics import median
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from sabiai.storage import CoverageStore

from .market_inventory import expected_market_families, market_family_gap


ACTION_BOOKS = ("SportyBet", "Bet9ja")


def canonical_action_book(value: object) -> str | None:
    text = "".join(ch for ch in str(value or "").casefold() if ch.isalnum())
    if "sportybet" in text:
        return "SportyBet"
    if "bet9ja" in text:
        return "Bet9ja"
    return None


def _norm(value: object) -> str:
    return "".join(ch for ch in str(value or "").casefold() if ch.isalnum())


def _offer_identity(row: dict[str, Any]) -> tuple:
    return (
        str(row.get("family") or "other").casefold(),
        _norm(row.get("metric")),
        _norm(row.get("period")),
        _norm(row.get("participant")),
        _norm(row.get("side")),
        str(row.get("line") if row.get("line") is not None else ""),
        _norm(row.get("selection_label")),
    )


def market_consensus(offers: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple, list[dict[str, Any]]] = defaultdict(list)
    for row in offers:
        if not isinstance(row, dict):
            continue
        try:
            price = float(row.get("decimal_odds"))
        except (TypeError, ValueError):
            continue
        if price <= 1:
            continue
        groups[_offer_identity(row)].append(row)

    output: list[dict[str, Any]] = []
    for key, rows in groups.items():
        by_book: dict[str, dict[str, Any]] = {}
        for row in rows:
            book = str(row.get("bookmaker") or row.get("source_name") or "unknown")
            existing = by_book.get(book)
            if existing is None or float(row["decimal_odds"]) > float(existing["decimal_odds"]):
                by_book[book] = row
        rows = list(by_book.values())
        prices = [float(row["decimal_odds"]) for row in rows]
        if not prices:
            continue
        med = float(median(prices))
        best = max(rows, key=lambda row: float(row["decimal_odds"]))
        best_price = float(best["decimal_odds"])
        disagreement = ((best_price / med) - 1.0) * 100.0 if med > 0 else 0.0
        output.append({
            "family": key[0],
            "metric": best.get("metric"),
            "period": best.get("period"),
            "participant": best.get("participant"),
            "side": best.get("side"),
            "line": best.get("line"),
            "selection": best.get("selection_label"),
            "bookmakers": len(rows),
            "median_odds": round(med, 3),
            "best_odds": round(best_price, 3),
            "best_bookmaker": str(best.get("bookmaker") or best.get("source_name") or "unknown"),
            "price_disagreement_pct": round(max(0.0, disagreement), 2),
        })
    output.sort(
        key=lambda row: (
            -float(row["price_disagreement_pct"]),
            -int(row["bookmakers"]),
            str(row["family"]),
            str(row["selection"]),
        )
    )
    return output


@dataclass
class CoveragePrefilter:
    """Turn a broad sensor universe into a bounded action-book research universe.

    All fresh bookmaker/sensor prices can influence consensus and priority. Only SportyBet or
    Bet9ja offers are exposed in `odds`, which is the field consumed by automatic research and
    recording. This prevents a sensor-only price from silently becoming a playable pick.
    """

    settings: Any
    store: CoverageStore

    def select(
        self,
        day: str,
        *,
        limit: int | None = None,
        actionable_only: bool = True,
    ) -> list[dict[str, Any]]:
        limit = max(1, int(limit or getattr(self.settings, "prefilter_max_events", 300)))
        zone = self._zone()
        local_day = date.fromisoformat(day)
        start_local = datetime.combine(local_day, datetime.min.time(), zone)
        rows = self.store.radar(
            now=start_local.astimezone(timezone.utc),
            horizon_hours=26,
            limit=max(5000, limit * 5),
        )
        candidates: list[dict[str, Any]] = []
        max_age = max(900, int(getattr(self.settings, "market_refresh_seconds", 1800)) * 4)
        for row in rows:
            starts = self._time(row.get("starts_at"))
            if starts is None or starts.astimezone(zone).date() != local_day:
                continue
            inventory = self.store.market_inventory(str(row["id"]), max_age_seconds=max_age)
            offers = inventory.get("offers") or []
            if not offers:
                continue
            consensus = market_consensus(offers)
            action_offers = [
                offer for offer in offers
                if canonical_action_book(offer.get("bookmaker") or offer.get("source_name"))
            ]
            if actionable_only and not action_offers:
                continue
            sport = str(row.get("sport") or "unknown")
            chosen_book = self._choose_action_book(action_offers, consensus, sport=sport)
            chosen = [
                offer for offer in action_offers
                if canonical_action_book(offer.get("bookmaker") or offer.get("source_name")) == chosen_book
            ] if chosen_book else []
            families = sorted({str(item.get("family") or "other") for item in offers})
            missing = market_family_gap(sport, families)
            event = dict(row)
            event["event"] = event.pop("event_name")
            event["event_id"] = row["id"]
            event["coverage_event_id"] = row["id"]
            event["source"] = chosen_book or "Market sensors"
            event["odds"] = self._compact_action_odds(chosen)
            event["market_consensus"] = consensus[:10]
            event["market_families"] = families
            event["missing_minimum_markets"] = missing
            event["action_book"] = chosen_book
            event["action_price_available"] = bool(chosen)
            event["market_disagreement_pct"] = max(
                (float(item.get("price_disagreement_pct") or 0) for item in consensus),
                default=0.0,
            )
            event["_coverage_score"] = self._score(event, inventory, consensus)
            candidates.append(event)

        return self._balanced(candidates, limit)

    def _choose_action_book(
        self,
        offers: list[dict[str, Any]],
        consensus: list[dict[str, Any]],
        *,
        sport: str,
    ) -> str | None:
        if not offers:
            return None
        expected = set(expected_market_families(sport))
        rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for offer in offers:
            book = canonical_action_book(offer.get("bookmaker") or offer.get("source_name"))
            if book:
                rows[book].append(offer)
        consensus_lookup = {
            _offer_identity({
                "family": row.get("family"),
                "metric": row.get("metric"),
                "period": row.get("period"),
                "participant": row.get("participant"),
                "side": row.get("side"),
                "line": row.get("line"),
                "selection_label": row.get("selection"),
            }): row
            for row in consensus
        }
        ranked = []
        for book, book_offers in rows.items():
            families = {str(row.get("family") or "other") for row in book_offers}
            minimum_hits = len(families & expected) if expected else 0
            price_bonus = 0.0
            for offer in book_offers:
                reference = consensus_lookup.get(_offer_identity(offer))
                if reference and float(reference.get("median_odds") or 0) > 1:
                    price_bonus += max(
                        0.0,
                        (float(offer["decimal_odds"]) / float(reference["median_odds"]) - 1.0) * 100.0,
                    )
            ranked.append((minimum_hits, len(families), len(book_offers), price_bonus, book))
        ranked.sort(reverse=True)
        return ranked[0][-1] if ranked else None

    @staticmethod
    def _compact_action_odds(offers: list[dict[str, Any]]) -> list[dict[str, Any]]:
        priority = {"winner": 0, "handicap": 1, "total": 2, "draw_no_bet": 3, "team_total": 4}
        rows = sorted(
            offers,
            key=lambda row: (
                priority.get(str(row.get("family") or "other"), 20),
                str(row.get("family") or ""),
                str(row.get("selection_label") or ""),
                -float(row.get("decimal_odds") or 0),
            ),
        )
        result = []
        seen = set()
        for offer in rows:
            key = _offer_identity(offer)
            if key in seen:
                continue
            seen.add(key)
            result.append({
                "label": offer.get("selection_label"),
                "decimal_odds": float(offer["decimal_odds"]),
                "market": offer.get("family"),
                "line": offer.get("line"),
                "period": offer.get("period"),
                "participant": offer.get("participant"),
                "bookmaker": canonical_action_book(offer.get("bookmaker") or offer.get("source_name")),
                "observed_at": offer.get("observed_at"),
            })
            if len(result) >= 18:
                break
        return result

    def _score(
        self,
        event: dict[str, Any],
        inventory: dict[str, Any],
        consensus: list[dict[str, Any]],
    ) -> float:
        families = set(event.get("market_families") or [])
        expected = set(expected_market_families(str(event.get("sport") or "")))
        books = {
            str(row.get("bookmaker") or row.get("source_name") or "")
            for row in (inventory.get("offers") or [])
            if str(row.get("bookmaker") or row.get("source_name") or "")
        }
        coverage_ratio = (len(families & expected) / len(expected)) if expected else 0.0
        disagreement = max(
            (float(row.get("price_disagreement_pct") or 0) for row in consensus),
            default=0.0,
        )
        score = 20.0
        score += min(len(families) * 4.0, 28.0)
        score += min(len(books) * 2.0, 14.0)
        score += min(len(inventory.get("sources") or []) * 3.0, 12.0)
        score += coverage_ratio * 12.0
        score += min(disagreement, 14.0)
        if event.get("action_price_available"):
            score += 10.0
        return score

    def _balanced(self, candidates: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
        candidates.sort(
            key=lambda row: (
                -float(row.get("_coverage_score") or 0),
                str(row.get("starts_at") or ""),
                str(row.get("event") or ""),
            )
        )
        min_per_sport = max(1, int(getattr(self.settings, "research_min_events_per_active_sport", 2)))
        max_per_sport = max(
            min_per_sport,
            int(getattr(self.settings, "research_max_events_per_sport", 40)),
        )
        by_sport: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in candidates:
            by_sport[str(row.get("sport") or "unknown")].append(row)
        selected: list[dict[str, Any]] = []
        selected_ids: set[str] = set()
        counts: dict[str, int] = defaultdict(int)

        for round_index in range(min_per_sport):
            for sport in sorted(by_sport):
                if len(selected) >= limit:
                    break
                rows = by_sport[sport]
                if round_index >= len(rows):
                    continue
                row = rows[round_index]
                selected.append(row)
                selected_ids.add(str(row.get("id") or row.get("event_id") or id(row)))
                counts[sport] += 1

        for row in candidates:
            if len(selected) >= limit:
                break
            sport = str(row.get("sport") or "unknown")
            identifier = str(row.get("id") or row.get("event_id") or id(row))
            if identifier in selected_ids or counts[sport] >= max_per_sport:
                continue
            selected.append(row)
            selected_ids.add(identifier)
            counts[sport] += 1

        for row in selected:
            row.pop("_coverage_score", None)
        return selected

    def _zone(self):
        try:
            return ZoneInfo(getattr(self.settings, "timezone", "Africa/Lagos"))
        except Exception:
            return timezone.utc

    @staticmethod
    def _time(value: object) -> datetime | None:
        if value is None or not str(value).strip():
            return None
        text = str(value).strip()
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
