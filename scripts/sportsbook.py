#!/usr/bin/env python3
"""sportsbook.py — Sportsbook API2 on RapidAPI + OddsAPI.

Sportsbook API2: sportsbook-api2.p.rapidapi.com
  - 150 calls/day
  - Real-time arbitrage opportunities with bookmaker odds
  - Sports/coverage vary by day (whatever has live betting markets)

OddsAPI: odds-api1.p.rapidapi.com (key: YOUR_ODDSAPI_KEY_HERE)
  - Dedicated odds feed

Use for:
  • Finding value bets and arbitrage opportunities
  • Getting real bookmaker odds for sports TheRundown doesn't cover
  • Cross-referencing odds against our model
"""

import json, os, re, sqlite3, time, urllib.request, unicodedata
from datetime import datetime, timezone, timedelta
from collections import defaultdict

RAPIDAPI_KEY = "YOUR_RAPIDAPI_KEY_HERE"
SPORTSBOOK_HOST = "sportsbook-api2.p.rapidapi.com"
ODDSAPI_HOST    = "odds-api1.p.rapidapi.com"
ODDSAPI_KEY     = "YOUR_ODDSAPI_KEY_HERE"

CACHE_DB = "~.openclaw/workspace/data/sportsbook_cache.db"

CACHE_TTL = {
    "arbitrage": 300,      # 5 min — arbs are live
    "odds":      600,      # 10 min — odds change
}

# Sport slug mapping (Sportsbook API2 uses uppercase)
SPORT_MAP = {
    "baseball":    "BASEBALL",
    "mlb":         "BASEBALL",
    "basketball":  "BASKETBALL",
    "nba":         "BASKETBALL",
    "football":    "SOCCER",
    "soccer":      "SOCCER",
    "americanfootball": "AMERICAN_FOOTBALL",
    "nfl":         "AMERICAN_FOOTBALL",
    "hockey":      "ICE_HOCKEY",
    "nhl":         "ICE_HOCKEY",
    "tennis":      "TENNIS",
    "mma":         "MMA",
    "boxing":      "BOXING",
}

MARKET_LABELS = {
    "MONEYLINE":    "1X2",
    "POINT_SPREAD": "Handicap",
    "TOTAL":        "O/U",
}


def _init_cache():
    os.makedirs(os.path.dirname(CACHE_DB), exist_ok=True)
    c = sqlite3.connect(CACHE_DB)
    c.execute("""CREATE TABLE IF NOT EXISTS cache (
        key TEXT PRIMARY KEY, data TEXT NOT NULL, stored_at INTEGER NOT NULL
    )""")
    c.commit(); c.close()


def _cache_get(key, ttl):
    try:
        c = sqlite3.connect(CACHE_DB)
        row = c.execute("SELECT data, stored_at FROM cache WHERE key=?", (key,)).fetchone()
        c.close()
        if row and (time.time() - row[1]) < ttl:
            return json.loads(row[0])
    except Exception: pass
    return None


def _cache_set(key, data):
    try:
        c = sqlite3.connect(CACHE_DB)
        c.execute("INSERT OR REPLACE INTO cache VALUES (?,?,?)",
                  (key, json.dumps(data), int(time.time())))
        c.commit(); c.close()
    except Exception: pass


def _rapid(host, path, key=None, params=''):
    k = key or RAPIDAPI_KEY
    url = f"https://{host}/{path}" + (f"?{params}" if params else "")
    req = urllib.request.Request(url, headers={
        "x-rapidapi-key": k, "x-rapidapi-host": host, "User-Agent": "Mozilla/5.0",
    })
    try:
        with urllib.request.urlopen(req, timeout=12) as r:
            return json.loads(r.read())
    except Exception:
        return None


def _norm(s):
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9 ]", "", s.lower()).strip()


def _match(a, b):
    na, nb = _norm(a), _norm(b)
    if na == nb: return True
    if na in nb or nb in na: return True
    wa, wb = set(na.split()), set(nb.split())
    return bool(wa and wb and len(wa & wb) / max(len(wa), len(wb)) >= 0.5)


def init():
    _init_cache()


# ── Sportsbook API2 ───────────────────────────────────────────────────────────

def arbitrage_opportunities() -> list:
    """
    All current arbitrage opportunities. Returns list of parsed dicts:
    { event, sport, market_type, market_label, home, away, outcomes, kickoff }

    Where each outcome: { team, payout (decimal odds), modifier, bookmaker }
    """
    cache_key = "arb:current"
    cached = _cache_get(cache_key, CACHE_TTL["arbitrage"])
    if cached is not None:
        return cached

    data = _rapid(SPORTSBOOK_HOST, "v0/advantages/", params="type=ARBITRAGE")
    if not data:
        return []

    results = []
    for adv in data.get("advantages", []):
        market = adv.get("market", {})
        event  = market.get("event", {})
        participants = event.get("participants", [])

        if len(participants) < 2:
            continue

        home = participants[0].get("name", "")
        away = participants[1].get("name", "")
        sport = participants[0].get("sport", "UNKNOWN")
        kickoff = event.get("startTime", "")
        mtype = market.get("type", "")

        outcomes = []
        for o in adv.get("outcomes", []):
            outcomes.append({
                "team":      o.get("participant", {}).get("name", ""),
                "payout":    o.get("payout"),      # decimal odds
                "modifier":  o.get("modifier"),    # for spreads: line value
                "bookmaker": o.get("source", ""),
                "type":      o.get("type", ""),
            })

        # Calculate arb profit % (if payout exists)
        if len(outcomes) == 2 and all(o.get("payout") for o in outcomes):
            p1 = outcomes[0]["payout"]; p2 = outcomes[1]["payout"]
            arb_pct = round((1 - (1/p1 + 1/p2)) * 100, 2) if p1 and p2 else 0
        else:
            arb_pct = 0

        results.append({
            "event":        event.get("name", f"{home} vs {away}"),
            "home":         home,
            "away":         away,
            "sport":        sport,
            "competition":  event.get("competitionInstance", {}).get("competition", {}).get("name", ""),
            "market_type":  mtype,
            "market_label": MARKET_LABELS.get(mtype, mtype),
            "kickoff":      kickoff,
            "outcomes":     outcomes,
            "arb_profit_pct": arb_pct,
            "found_at":     adv.get("lastFoundAt", ""),
        })

    _cache_set(cache_key, results)
    return results


def get_odds_for_event(home: str, away: str, sport: str = None) -> list:
    """
    Find current odds for a specific match from the arbitrage feed.
    Returns list of outcomes from all bookmakers.
    """
    arbs = arbitrage_opportunities()
    matches = []
    for arb in arbs:
        if _match(home, arb["home"]) and _match(away, arb["away"]):
            if sport and not _match(sport, arb["sport"]):
                continue
            matches.append(arb)
    return matches


def best_odds(home: str, away: str, sport: str = None) -> dict | None:
    """
    Find the best available odds for home/draw/away from the arb feed.
    Returns { home_best_odds, home_bookie, away_best_odds, away_bookie, market }
    """
    matches = get_odds_for_event(home, away, sport)
    if not matches:
        return None

    # Find best moneyline
    ml = [m for m in matches if m["market_type"] == "MONEYLINE"]
    if ml:
        for arb in ml:
            home_out = next((o for o in arb["outcomes"] if _match(home, o["team"])), None)
            away_out = next((o for o in arb["outcomes"] if _match(away, o["team"])), None)
            if home_out and away_out:
                return {
                    "home_odds":   home_out["payout"],
                    "home_bookie": home_out["bookmaker"],
                    "away_odds":   away_out["payout"],
                    "away_bookie": away_out["bookmaker"],
                    "market":      "1X2",
                    "arb_pct":     arb["arb_profit_pct"],
                }
    return None


def sports_in_feed() -> dict:
    """Return count of opportunities per sport currently in the feed."""
    from collections import Counter
    arbs = arbitrage_opportunities()
    return dict(Counter(a["sport"] for a in arbs))


def format_arb_for_display(arb: dict) -> str:
    """Format an arbitrage opportunity as a plain-English string."""
    home = arb.get("home", ""); away = arb.get("away", "")
    mkt = arb.get("market_label", arb.get("market_type", ""))
    comp = arb.get("competition", ""); sport = arb.get("sport", "")
    kick = arb.get("kickoff", "")[:16].replace("T", " ")
    profit = arb.get("arb_profit_pct", 0)
    outcomes = arb.get("outcomes", [])

    lines = [f"{home} vs {away} | {comp} ({sport}) | {kick} UTC"]
    lines.append(f"Market: {mkt} | Guaranteed profit: {profit:+.1f}%")
    for o in outcomes:
        lines.append(f"  {o.get('team','?')} @ {o.get('payout','?')} ({o.get('bookmaker','?')}{' '+str(o.get('modifier','')) if o.get('modifier') else ''})")
    return "\n".join(lines)


# ── OddsAPI ───────────────────────────────────────────────────────────────────

def oddsapi_events(sport_key: str = "football") -> list:
    """
    Get events with odds from OddsAPI.
    API key: YOUR_ODDSAPI_KEY_HERE
    """
    cache_key = f"oddsapi:{sport_key}"
    cached = _cache_get(cache_key, CACHE_TTL["odds"])
    if cached is not None:
        return cached

    data = _rapid(ODDSAPI_HOST, f"sports/{sport_key}/odds",
                  key=ODDSAPI_KEY,
                  params="regions=eu&markets=h2h,spreads,totals&oddsFormat=decimal")
    if not data:
        return []

    # Parse into standard format
    results = []
    for event in (data if isinstance(data, list) else data.get("data", [])):
        home = event.get("home_team", ""); away = event.get("away_team", "")
        commence = event.get("commence_time", "")
        bookmakers = event.get("bookmakers", [])

        # Collect best odds per outcome
        best = defaultdict(lambda: {"odds": 0, "bookmaker": ""})
        for bk in bookmakers:
            for market in bk.get("markets", []):
                for outcome in market.get("outcomes", []):
                    name = outcome.get("name", "")
                    price = outcome.get("price", 0)
                    if price > best[name]["odds"]:
                        best[name] = {"odds": price, "bookmaker": bk.get("key", "")}

        if best:
            results.append({
                "id":       event.get("id", ""),
                "sport":    sport_key,
                "home":     home,
                "away":     away,
                "kickoff":  commence,
                "best_odds": dict(best),
                "n_books":  len(bookmakers),
            })

    _cache_set(cache_key, results)
    return results
