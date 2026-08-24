#!/usr/bin/env python3
"""
espn_odds.py — ESPN public scoreboard API for multi-sport fixture + odds data.

ESPN's scoreboard API is completely public (no key needed).
Provides DraftKings moneyline odds for major sports events.

Sports covered:
  soccer/fifa.world   — FIFA World Cup 2026
  soccer/fifa.friendly — International Friendlies
  baseball/mlb        — MLB
  basketball/nba      — NBA
  hockey/nhl          — NHL
  tennis/atp          — ATP
  tennis/wta          — WTA
  mma/ufc             — UFC
  soccer/conmebol.america — Copa America
"""

import json, urllib.request, time, sqlite3, os
from datetime import datetime, timezone, timedelta

CACHE_DB = "~.openclaw/workspace/data/sofascore_cache.db"
ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports"

SPORT_PATHS = [
    ("soccer/fifa.world",       "⚽", "World Cup"),
    ("soccer/fifa.friendly",    "⚽", "Int Friendly"),
    ("soccer/conmebol.america", "⚽", "Copa América"),
    ("soccer/conmebol.copa",    "⚽", "Copa Libertadores"),
    ("soccer/uefa.champions",   "⚽", "Champions League"),
    ("soccer/uefa.europa",      "⚽", "Europa League"),
    ("baseball/mlb",            "⚾", "MLB"),
    ("basketball/nba",          "🏀", "NBA"),
    ("hockey/nhl",              "🏒", "NHL"),
    ("tennis/atp",              "🎾", "ATP Tennis"),
    ("tennis/wta",              "🎾", "WTA Tennis"),
    ("mma/ufc",                 "🥊", "UFC"),
    ("basketball/wnba",         "🏀", "WNBA"),
    ("soccer/fifa.world.women", "⚽", "Women's WC"),
]


def _init_cache():
    os.makedirs(os.path.dirname(CACHE_DB), exist_ok=True)
    c = sqlite3.connect(CACHE_DB)
    c.execute("""CREATE TABLE IF NOT EXISTS cache (
        key TEXT PRIMARY KEY, data TEXT NOT NULL, stored_at INTEGER NOT NULL)""")
    c.commit(); c.close()


def _cache_get(key, ttl=3600 * 4):
    try:
        c = sqlite3.connect(CACHE_DB)
        row = c.execute("SELECT data, stored_at FROM cache WHERE key=?", (key,)).fetchone()
        c.close()
        if row and (time.time() - row[1]) < ttl:
            return json.loads(row[0])
    except:
        pass
    return None


def _cache_set(key, data):
    try:
        c = sqlite3.connect(CACHE_DB)
        c.execute("INSERT OR REPLACE INTO cache VALUES (?,?,?)",
                  (key, json.dumps(data), int(time.time())))
        c.commit(); c.close()
    except:
        pass


def _get(path, date_str):
    cache_key = f"espn:{path.replace('/',':')}:{date_str}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached
    url = f"{ESPN_BASE}/{path}/scoreboard?dates={date_str.replace('-','')}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
    except Exception:
        return []
    events = data.get("events", [])
    result = [_parse_event(ev) for ev in events if ev]
    _cache_set(cache_key, result)
    return result


def _american_to_decimal(odds_str):
    try:
        ml = int(str(odds_str or "").replace("+", "").strip())
        return round(100 / abs(ml) + 1, 3) if ml < 0 else round(ml / 100 + 1, 3)
    except:
        return None


def _get_ml(comp):
    for o in (comp.get("odds") or []):
        if not isinstance(o, dict):
            continue
        ml = o.get("moneyline") or {}
        if isinstance(ml, dict) and ml:
            h_c = ml.get("home") or {}
            a_c = ml.get("away") or {}
            h_raw = ((h_c.get("close") or h_c.get("open")) or {}).get("odds")
            a_raw = ((a_c.get("close") or a_c.get("open")) or {}).get("odds")
            if h_raw and a_raw:
                return _american_to_decimal(h_raw), _american_to_decimal(a_raw)
        h_raw = (o.get("homeTeamOdds") or {}).get("moneyLine")
        a_raw = (o.get("awayTeamOdds") or {}).get("moneyLine")
        if h_raw and a_raw:
            return _american_to_decimal(h_raw), _american_to_decimal(a_raw)
    return None, None


def _parse_event(ev):
    comp = (ev.get("competitions") or [{}])[0]
    home = away = None
    for c in comp.get("competitors", []):
        name = (c.get("team") or c.get("athlete") or {}).get("displayName", "?")
        if c.get("homeAway") == "home":
            home = name
        elif c.get("homeAway") == "away":
            away = name
    if not home:
        cs = comp.get("competitors", [])
        home = (cs[0].get("team") or cs[0].get("athlete") or {}).get("displayName", "?") if cs else "?"
        away = (cs[1].get("team") or cs[1].get("athlete") or {}).get("displayName", "?") if len(cs) > 1 else "?"

    status = comp.get("status", {}).get("type", {}).get("name", "")
    h_dec, a_dec = _get_ml(comp)
    kickoff_str = ev.get("date", "")[:16].replace("T", " ")
    tournament = ((ev.get("competitions") or [{}])[0].get("notes") or [{}])[0].get("headline", "") if comp.get("notes") else ""
    if not tournament:
        tournament = ev.get("name", "")

    return {
        "home": home or "?",
        "away": away or "?",
        "kickoff": kickoff_str,
        "status": status,
        "home_odds": h_dec,
        "away_odds": a_dec,
        "tournament": tournament,
    }


def events_week(sport_path: str, start_date: str, days: int = 7) -> list:
    """Get all events for a sport over a date range."""
    start = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    results = []
    for i in range(days):
        d = (start + timedelta(days=i)).strftime("%Y-%m-%d")
        results.extend(_get(sport_path, d))
    return results


def week_qualifying(start_date: str, min_odds: float, max_odds: float,
                    min_implied_prob: float = 0.0, days: int = 7) -> list:
    """
    Scan all sports for events this week where the favourite's odds are in [min_odds, max_odds].
    Returns list of dicts with: home, away, kickoff, pick, odds, implied_prob, sport_label, tournament.
    """
    _init_cache()
    qualifying = []
    now = datetime.now(timezone.utc)

    for sport_path, emoji, sport_label in SPORT_PATHS:
        for i in range(days):
            d = (now + timedelta(days=i)).strftime("%Y-%m-%d")
            events = _get(sport_path, d)
            for ev in events:
                if ev.get("status") in ("STATUS_FINAL", "STATUS_IN_PROGRESS"):
                    continue
                h, a = ev.get("home", "?"), ev.get("away", "?")
                h_d, a_d = ev.get("home_odds"), ev.get("away_odds")
                if not h_d or not a_d:
                    continue
                fav_odds = min(h_d, a_d)
                pick = h if h_d <= a_d else a
                implied_prob = round(1.0 / fav_odds * 100, 1)
                if fav_odds < min_odds or fav_odds > max_odds:
                    continue
                if implied_prob < min_implied_prob:
                    continue
                qualifying.append({
                    "home": h,
                    "away": a,
                    "match": f"{h} vs {a}",
                    "kickoff": ev.get("kickoff", d),
                    "pick": pick,
                    "odds": fav_odds,
                    "implied_prob": implied_prob,
                    "sport": f"{emoji} {sport_label}",
                    "tournament": ev.get("tournament", sport_label),
                })

    return qualifying


if __name__ == "__main__":
    _init_cache()
    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    print(f"Qualifying games this week (1.05 - 1.50):")
    picks = week_qualifying(today, 1.05, 1.50)
    picks.sort(key=lambda x: x["odds"])
    for p in picks:
        print(f"  {p['odds']:.3f} ({p['implied_prob']}%) | {p['pick']:25s} | {p['match'][:40]:40s} | {p['sport']:15s} | {p['kickoff'][:10]}")
    print(f"Total: {len(picks)}")
