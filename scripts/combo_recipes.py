#!/usr/bin/env python3
"""combo_recipes.py - build low-odds SabiAI chain accumulator recipes."""

import argparse
import itertools
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone

DB_PATH = "/home/hendrix/.openclaw/workspace/data/bets.db"
CHAIN_MARKETS = {"double chance", "handicap"}
SAFE_ODDS_MIN = 1.10
SAFE_ODDS_MAX = 1.50
TARGET_ODDS_MIN = 1.50
TARGET_ODDS_MAX = 2.50


def _as_float(value):
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _prob_fraction(bet):
    prob = _as_float(bet.get("our_prob"))
    if prob is None:
        prob = _as_float(bet.get("confidence_pct"))
    if prob is None:
        return None
    return prob / 100.0 if prob > 1 else prob


def _confidence_pct(bet):
    prob = _prob_fraction(bet)
    return round(prob * 100, 1) if prob is not None else None


def _safe_odds(odds):
    return odds is not None and SAFE_ODDS_MIN <= odds <= SAFE_ODDS_MAX


def _leg_key(bet):
    return (
        bet.get("match", ""),
        bet.get("market", ""),
        bet.get("pick", ""),
        bet.get("bookmaker", ""),
    )


def load_bets_from_db(date_str=None, db_path=DB_PATH):
    """Load scanner picks for a scan date from bets.db."""
    date_str = date_str or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if not os.path.exists(db_path):
        return []
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("""
            SELECT id, bet_id, scan_date, sport, match, kickoff, market, pick,
                   odds, bookmaker, ev, our_prob, kelly, model,
                   confidence_pct, plain_rationale
              FROM bets
             WHERE scan_date = ?
             ORDER BY confidence_pct DESC, our_prob DESC, odds ASC
        """, (date_str,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def load_bets_from_json(path):
    """Load picks from a JSON file or stdin when path is '-'."""
    raw = sys.stdin.read() if path == "-" else open(path, encoding="utf-8").read()
    data = json.loads(raw)
    if isinstance(data, dict):
        for key in ("bets", "picks", "legs"):
            if isinstance(data.get(key), list):
                return data[key]
    if isinstance(data, list):
        return data
    raise ValueError("JSON input must be a list or an object with bets/picks/legs")


def eligible_legs(bets):
    """Return chain-ready legs, with 1X2 fallback if DC/handicap depth is thin."""
    seen = set()
    chain = []
    fallback = []
    for bet in bets:
        if not isinstance(bet, dict):
            continue
        market = (bet.get("market") or "").strip()
        market_l = market.lower()
        odds = _as_float(bet.get("odds"))
        prob = _prob_fraction(bet)
        if not _safe_odds(odds) or prob is None:
            continue
        key = _leg_key(bet)
        if key in seen:
            continue
        seen.add(key)
        leg = dict(bet)
        leg["odds"] = round(odds, 4)
        leg["_prob"] = prob
        leg["_confidence_pct"] = _confidence_pct(leg)
        leg["_reliability"] = prob * odds
        if market_l in CHAIN_MARKETS:
            chain.append(leg)
        elif market_l == "1x2" and (leg["_confidence_pct"] or 0) >= 65:
            fallback.append(leg)
    chain.sort(key=lambda b: (b["_reliability"], b["_prob"], -b["odds"]), reverse=True)
    fallback.sort(key=lambda b: (b["_reliability"], b["_prob"], -b["odds"]), reverse=True)
    return chain if len(chain) >= 2 else chain + fallback


def _combo_from_legs(legs):
    combined_odds = 1.0
    combined_prob = 1.0
    for leg in legs:
        combined_odds *= leg["odds"]
        combined_prob *= leg["_prob"]
    return {
        "legs": [
            {
                "sport": leg.get("sport", ""),
                "match": leg.get("match", ""),
                "kickoff": leg.get("kickoff", ""),
                "market": leg.get("market", ""),
                "pick": leg.get("pick", ""),
                "odds": round(leg["odds"], 2),
                "confidence_pct": leg.get("_confidence_pct"),
                "bookmaker": leg.get("bookmaker", ""),
                "rationale": leg.get("plain_rationale", ""),
            }
            for leg in legs
        ],
        "combined_odds": round(combined_odds, 2),
        "estimated_hit_rate_pct": round(combined_prob * 100, 1),
        "reliability_score": round(combined_prob * combined_odds, 4),
    }


def generate_recipes(bets, max_combos=3):
    """Generate 2-3 leg accumulator recipes targeting 1.50-2.50 combined odds.

    Accepts a list of bet dicts OR a date string (YYYY-MM-DD) which will be
    resolved via load_bets_from_db.
    """
    if isinstance(bets, str):
        bets = load_bets_from_db(bets)
    legs = eligible_legs(bets)
    combos = []
    for size in (2, 3):
        for group in itertools.combinations(legs, size):
            matches = [g.get("match", "") for g in group]
            if len(set(matches)) != len(matches):
                continue
            combo = _combo_from_legs(group)
            if TARGET_ODDS_MIN <= combo["combined_odds"] <= TARGET_ODDS_MAX:
                combo["_target_distance"] = abs(combo["combined_odds"] - 2.0)
                combos.append(combo)
    combos.sort(key=lambda c: (c["reliability_score"], -c["_target_distance"]), reverse=True)
    for combo in combos:
        combo.pop("_target_distance", None)
    return combos[:max_combos]


def format_recipes(recipes, date_str):
    lines = [f"Chain combo recipes - {date_str}"]
    if not recipes:
        lines.append("No 2-3 leg chain combo fits the 1.50-2.50 odds target today.")
        return "\n".join(lines)
    for idx, recipe in enumerate(recipes, 1):
        lines.append("")
        lines.append(
            f"Combo {idx}: {len(recipe['legs'])} legs @ {recipe['combined_odds']:.2f} total "
            f"({recipe['estimated_hit_rate_pct']:.1f}% estimated hit rate)"
        )
        for leg in recipe["legs"]:
            conf = leg.get("confidence_pct")
            conf_s = f"{conf:.1f}%" if isinstance(conf, (int, float)) else "unrated"
            lines.append(
                f"- {leg['match']}: {leg['market']} - {leg['pick']} "
                f"@ {leg['odds']:.2f} ({conf_s})"
            )
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    parser.add_argument("--json", action="store_true", help="Output JSON only")
    parser.add_argument("--max-combos", type=int, default=3)
    parser.add_argument("--input", help="Read bets from JSON file, or '-' for stdin")
    parser.add_argument("--db", default=DB_PATH)
    args = parser.parse_args()

    bets = load_bets_from_json(args.input) if args.input else load_bets_from_db(args.date, args.db)
    recipes = generate_recipes(bets, max_combos=args.max_combos)
    payload = {"date": args.date, "recipes": recipes}
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(format_recipes(recipes, args.date))


if __name__ == "__main__":
    main()
