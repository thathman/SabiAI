from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
from typing import Any, Iterable


TEAM_MARKET_MINIMUM = ("winner", "handicap", "total")
SPORT_MARKET_EXPECTATIONS: dict[str, tuple[str, ...]] = {
    "golf": ("outright", "placement", "matchup"),
    "motorsport": ("outright", "placement", "matchup"),
    "cycling": ("outright", "placement", "matchup"),
    "horse_racing": ("outright", "placement"),
    "greyhound_racing": ("outright", "placement"),
    "mma": ("winner", "method", "total_rounds"),
    "boxing": ("winner", "method", "total_rounds"),
    "esports": ("winner", "handicap", "total"),
}


def expected_market_families(sport: str) -> tuple[str, ...]:
    return SPORT_MARKET_EXPECTATIONS.get(str(sport or "").casefold(), TEAM_MARKET_MINIMUM)


def _slug(value: object) -> str:
    text = str(value or "").strip().casefold()
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")


def _period(value: str) -> str | None:
    key = _slug(value)
    checks = (
        ("first_half", "first half"),
        ("second_half", "second half"),
        ("1st_half", "first half"),
        ("2nd_half", "second half"),
        ("first_quarter", "first quarter"),
        ("second_quarter", "second quarter"),
        ("third_quarter", "third quarter"),
        ("fourth_quarter", "fourth quarter"),
        ("1st_quarter", "first quarter"),
        ("2nd_quarter", "second quarter"),
        ("3rd_quarter", "third quarter"),
        ("4th_quarter", "fourth quarter"),
        ("first_period", "first period"),
        ("second_period", "second period"),
        ("third_period", "third period"),
        ("1st_period", "first period"),
        ("2nd_period", "second period"),
        ("3rd_period", "third period"),
        ("first_set", "first set"),
        ("second_set", "second set"),
        ("third_set", "third set"),
        ("map_1", "map 1"),
        ("map_2", "map 2"),
        ("map_3", "map 3"),
    )
    for token, label in checks:
        if token in key:
            return label
    return None


def classify_market(source_key: object, label: object = None, *, sport: str = "") -> dict[str, Any]:
    raw = " ".join(part for part in (str(source_key or ""), str(label or "")) if part).strip()
    key = _slug(raw)
    period = _period(raw)
    race_field = str(sport or "").casefold() in {"golf", "motorsport", "cycling", "horse_racing", "greyhound_racing"}

    if any(token in key for token in ("top_5", "top5", "top_10", "top10", "top_20", "top20", "podium", "placed", "place_only")):
        family = "placement"
    elif any(token in key for token in ("make_cut", "to_make_the_cut", "make_the_cut")):
        family = "make_cut"
    elif any(token in key for token in ("draw_no_bet", "dnb")):
        family = "draw_no_bet"
    elif any(token in key for token in ("both_teams_to_score", "btts")):
        family = "btts"
    elif any(token in key for token in ("correct_score", "exact_score")):
        family = "correct_score"
    elif any(token in key for token in ("team_total", "team_totals")):
        family = "team_total"
    elif any(token in key for token in ("asian_handicap", "spread", "spreads", "handicap", "puck_line", "run_line")):
        family = "handicap"
    elif any(token in key for token in ("total_rounds", "rounds_over_under")):
        family = "total_rounds"
    elif any(token in key for token in ("total", "totals", "over_under", "overunder")):
        family = "total"
    elif any(token in key for token in ("method_of_victory", "winning_method", "method")):
        family = "method"
    elif any(token in key for token in ("matchup", "match_bet", "head_to_head_group")):
        family = "matchup"
    elif any(token in key for token in ("outright", "futures", "tournament_winner", "race_winner")):
        family = "outright"
    elif any(token in key for token in ("h2h", "match_odds", "moneyline", "money_line", "winner", "to_win")):
        family = "outright" if race_field else "winner"
    elif "corner" in key:
        family = "corners"
    elif any(token in key for token in ("card", "booking")):
        family = "cards"
    elif any(token in key for token in ("player_", "shots", "rebounds", "assists", "points", "goalscorer", "touchdown", "strikeouts")):
        family = "player_prop"
    elif "set" in key:
        family = "set_market"
    elif "map" in key:
        family = "map_market"
    else:
        family = "other"

    metric = None
    for token in (
        "goals", "points", "games", "sets", "maps", "corners", "cards", "rebounds", "assists",
        "shots", "shots_on_target", "strikeouts", "touchdowns", "runs", "wickets", "legs", "frames",
    ):
        if token in key:
            metric = token.replace("_", " ")
            break
    return {"family": family, "metric": metric, "period": period, "market_label": str(label or source_key or family)}


def _side(label: object) -> str | None:
    text = str(label or "").strip()
    key = text.casefold()
    if key.startswith("over"):
        return "over"
    if key.startswith("under"):
        return "under"
    if key in {"yes", "no", "draw", "tie"}:
        return key
    return None


@dataclass
class MarketInventoryNormalizer:
    source_name: str

    def the_odds_api(self, event: dict[str, Any], *, event_id: str, observed_at: str | None = None) -> tuple[list[dict], list[dict]]:
        catalog: list[dict] = []
        offers: list[dict] = []
        sport = str(event.get("sport_key") or event.get("sport_title") or "")
        for book in event.get("bookmakers") or []:
            if not isinstance(book, dict):
                continue
            bookmaker = str(book.get("title") or book.get("key") or self.source_name)
            last_update = book.get("last_update")
            for market in book.get("markets") or []:
                if not isinstance(market, dict):
                    continue
                market_key = str(market.get("key") or "other")
                parsed = classify_market(market_key, market_key, sport=sport)
                market_row = {
                    "source_name": self.source_name,
                    "bookmaker": bookmaker,
                    "source_market_key": market_key,
                    "source_market_id": market.get("sid") or market.get("id"),
                    **parsed,
                    "metadata": {"event_id": event_id, "provider_sport_key": event.get("sport_key")},
                }
                catalog.append(market_row)
                for outcome in market.get("outcomes") or []:
                    if not isinstance(outcome, dict):
                        continue
                    try:
                        price = float(outcome.get("price"))
                    except (TypeError, ValueError):
                        continue
                    if price <= 1:
                        continue
                    label = str(outcome.get("name") or outcome.get("description") or "Selection")
                    participant = outcome.get("description")
                    point = outcome.get("point")
                    offers.append({
                        **market_row,
                        "source_outcome_id": outcome.get("sid") or outcome.get("id"),
                        "participant": participant or market_row.get("participant"),
                        "side": _side(label),
                        "line": point,
                        "selection_label": label,
                        "decimal_odds": price,
                        "observed_at": observed_at or last_update or datetime.now(timezone.utc).isoformat(),
                        "source_last_update": last_update,
                        "metadata": {
                            **market_row["metadata"],
                            "outcome_link": outcome.get("link"),
                            "bookmaker_event_link": book.get("link"),
                        },
                    })
        return catalog, offers

    def betfair(self, payload: dict[str, Any], *, event_ids: dict[str, str] | None = None) -> tuple[list[dict], list[dict]]:
        event_ids = event_ids or {}
        catalog: list[dict] = []
        offers: list[dict] = []
        books = {
            str(row.get("marketId")): row
            for row in (payload.get("books") or [])
            if isinstance(row, dict) and row.get("marketId")
        }
        for market in payload.get("catalogue") or []:
            if not isinstance(market, dict):
                continue
            provider_event = market.get("event") if isinstance(market.get("event"), dict) else {}
            provider_event_id = str(provider_event.get("id") or "")
            canonical_event_id = event_ids.get(provider_event_id)
            if not canonical_event_id:
                continue
            description = market.get("description") if isinstance(market.get("description"), dict) else {}
            market_type = str(description.get("marketType") or market.get("marketName") or "other")
            market_name = str(market.get("marketName") or market_type)
            sport_name = str((market.get("eventType") or {}).get("name") if isinstance(market.get("eventType"), dict) else "")
            parsed = classify_market(market_type, market_name, sport=sport_name)
            base = {
                "source_name": self.source_name,
                "bookmaker": "Betfair Exchange",
                "source_market_key": market_type,
                "source_market_id": market.get("marketId"),
                **parsed,
                "metadata": {
                    "provider_event_id": provider_event_id,
                    "competition": (market.get("competition") or {}).get("name") if isinstance(market.get("competition"), dict) else None,
                },
            }
            catalog.append(base)
            runner_prices = {}
            book = books.get(str(market.get("marketId")))
            if isinstance(book, dict):
                for runner in book.get("runners") or []:
                    if not isinstance(runner, dict):
                        continue
                    backs = ((runner.get("ex") or {}).get("availableToBack") or []) if isinstance(runner.get("ex"), dict) else []
                    best = next((item for item in backs if isinstance(item, dict) and item.get("price")), None)
                    if best:
                        runner_prices[str(runner.get("selectionId"))] = best
            for runner in market.get("runners") or []:
                if not isinstance(runner, dict):
                    continue
                best = runner_prices.get(str(runner.get("selectionId")))
                if not best:
                    continue
                try:
                    price = float(best.get("price"))
                except (TypeError, ValueError):
                    continue
                if price <= 1:
                    continue
                label = str(runner.get("runnerName") or runner.get("selectionId") or "Selection")
                offers.append({
                    **base,
                    "source_outcome_id": runner.get("selectionId"),
                    "participant": label if parsed["family"] in {"outright", "placement", "matchup", "winner"} else None,
                    "side": _side(label),
                    "line": runner.get("handicap"),
                    "selection_label": label,
                    "decimal_odds": price,
                    "observed_at": datetime.now(timezone.utc).isoformat(),
                    "metadata": {**base["metadata"], "available_size": best.get("size")},
                })
        return catalog, offers

    def embedded(self, event: dict[str, Any], *, event_id: str) -> tuple[list[dict], list[dict]]:
        odds = event.get("odds") or []
        if not isinstance(odds, list):
            return [], []
        catalog: list[dict] = []
        offers: list[dict] = []
        home = str(event.get("home") or "").casefold()
        away = str(event.get("away") or "").casefold()
        for raw in odds:
            if not isinstance(raw, dict):
                continue
            label = str(raw.get("label") or raw.get("name") or "Selection")
            try:
                price = float(raw.get("decimal_odds") or raw.get("price"))
            except (TypeError, ValueError):
                continue
            if price <= 1:
                continue
            supplied_market = raw.get("market") or raw.get("market_key")
            if supplied_market:
                parsed = classify_market(supplied_market, supplied_market, sport=str(event.get("sport") or ""))
            else:
                key = label.casefold()
                family = "winner" if key in {home, away, "home", "away", "draw", "tie"} else "other"
                parsed = {"family": family, "metric": None, "period": None, "market_label": family}
            base = {
                "source_name": self.source_name,
                "bookmaker": raw.get("bookmaker") or self.source_name,
                "source_market_key": raw.get("market_key") or parsed["family"],
                "source_market_id": raw.get("market_id"),
                **parsed,
                "line": raw.get("line"),
                "participant": raw.get("participant"),
                "metadata": {"event_id": event_id, "embedded": True},
            }
            catalog.append(base)
            offers.append({
                **base,
                "source_outcome_id": raw.get("outcome_id"),
                "side": raw.get("side") or _side(label),
                "selection_label": label,
                "decimal_odds": price,
                "observed_at": raw.get("observed_at") or datetime.now(timezone.utc).isoformat(),
            })
        return catalog, offers


def market_family_gap(sport: str, available: Iterable[str]) -> list[str]:
    present = {str(item).casefold() for item in available}
    return [family for family in expected_market_families(sport) if family not in present]
