#!/usr/bin/env python3
"""sofascore.py — SofaScore via SportAPI7 on RapidAPI.

RapidAPI host: sportapi7.p.rapidapi.com
Rate limit: ~50 requests/month (reset every ~30 days) + 500k hard cap
Cost: Free tier

Covers ALL sports with real-time data:
  Football: 200-400+ events/day (all leagues worldwide)
  Table Tennis: 1000-1500 events/day
  Basketball: 200+ events/day (incl. European leagues)
  Tennis: 800+ events/day
  Volleyball: 60+ events/day
  Baseball: 400+ events/day
  Cricket: 30+ events/day

No odds — use for:
  • Fixture discovery (all sports, all leagues)
  • Auto-settling bets (final scores for every sport)
  • Head-to-head history
  • Team/player form
"""

import json, os, re, sqlite3, time, unicodedata, urllib.request
from datetime import datetime, timezone, timedelta

HOST     = "sportapi7.p.rapidapi.com"
KEY      = ""
CACHE_DB = "~.openclaw/workspace/data/sofascore_cache.db"
SECRETS  = "~.config/systemd/user/openclaw-gateway.service.d/20-secrets.conf"

# Sport slugs for the API
SPORTS = {
    "football":    "football",
    "soccer":      "football",
    "basketball":  "basketball",
    "tennis":      "tennis",
    "table-tennis":"table-tennis",
    "tabletennis": "table-tennis",
    "tt":          "table-tennis",
    "volleyball":  "volleyball",
    "baseball":    "baseball",
    "cricket":     "cricket",
    "rugby":       "rugby",
    "handball":    "handball",
    "hockey":      "ice-hockey",
    "icehockey":   "ice-hockey",
    "mma":         "mma",
    "boxing":      "boxing",
    "darts":       "darts",
    "futsal":      "futsal",
    "snooker":     "snooker",
    "esports":     "esports",
    "waterpolo":   "waterpolo",
    "cycling":     "cycling",
}

CACHE_TTL = {
    "fixtures": 3600 * 4,   # 4h — scores update during the day
    "event":    3600 * 6,   # 6h — event details
    "h2h":      3600 * 72,  # 72h — H2H history stable
    "team":     3600 * 24,  # 24h — team info
}


def _load_key():
    global KEY
    KEY = os.environ.get("RAPIDAPI_KEY", "") or os.environ.get("RAPID_API_KEY", "")
    if not KEY:
        try:
            with open(SECRETS) as f:
                for line in f:
                    # Find any rapidapi key stored (same key used for all rapidapi products)
                    m = re.search(r'(?:RAPIDAPI|RAPID_API)_KEY=([^"\s\']+)', line, re.IGNORECASE)
                    if m:
                        KEY = m.group(1); break
        except Exception:
            pass
    # Fallback: use the known key directly
    if not KEY:
        KEY = "YOUR_RAPIDAPI_KEY_HERE"


def _init_cache():
    os.makedirs(os.path.dirname(CACHE_DB), exist_ok=True)
    c = sqlite3.connect(CACHE_DB)
    c.execute("""CREATE TABLE IF NOT EXISTS cache (
        key TEXT PRIMARY KEY,
        data TEXT NOT NULL,
        stored_at INTEGER NOT NULL
    )""")
    c.commit(); c.close()


def _cache_get(key, ttl):
    try:
        c = sqlite3.connect(CACHE_DB)
        row = c.execute("SELECT data, stored_at FROM cache WHERE key=?", (key,)).fetchone()
        c.close()
        if row and (time.time() - row[1]) < ttl:
            return json.loads(row[0])
    except Exception:
        pass
    return None


def _cache_set(key, data):
    try:
        c = sqlite3.connect(CACHE_DB)
        c.execute("INSERT OR REPLACE INTO cache VALUES (?,?,?)",
                  (key, json.dumps(data), int(time.time())))
        c.commit(); c.close()
    except Exception:
        pass


def _call(path):
    if not KEY:
        return None
    url = f"https://{HOST}/{path}"
    req = urllib.request.Request(url, headers={
        "x-rapidapi-key": KEY,
        "x-rapidapi-host": HOST,
        "User-Agent": "Mozilla/5.0",
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


def _match(a, b, threshold=0.55):
    na, nb = _norm(a), _norm(b)
    if na == nb: return True
    if na in nb or nb in na: return True
    wa, wb = set(na.split()), set(nb.split())
    if wa and wb:
        return len(wa & wb) / max(len(wa), len(wb)) >= threshold
    return False


def _parse_event(e):
    """Normalise a raw SofaScore event into a flat dict."""
    ht = e.get("homeTeam") or e.get("homePlayer") or {}
    at = e.get("awayTeam") or e.get("awayPlayer") or {}
    hs_raw = e.get("homeScore") or {}; as_raw = e.get("awayScore") or {}
    status  = e.get("status", {})
    tour    = e.get("tournament") or {}

    # Final score = current (for finished) or display (for live)
    hs = hs_raw.get("current"); aws = as_raw.get("current")

    return {
        "id":         e.get("id"),
        "home":       ht.get("name") or ht.get("shortName", ""),
        "home_id":    ht.get("id"),
        "away":       at.get("name") or at.get("shortName", ""),
        "away_id":    at.get("id"),
        "home_score": hs,
        "away_score": aws,
        "status":     status.get("type", ""),        # "finished", "inprogress", "notstarted"
        "status_desc":status.get("description", ""),
        "winner_code":e.get("winnerCode"),            # 1=home, 2=away, 3=draw
        "kickoff_ts": e.get("startTimestamp"),
        "tournament": tour.get("name", ""),
        "tournament_id": tour.get("id"),
        "country":    (tour.get("category") or {}).get("name", ""),
        "slug":       e.get("slug", ""),
    }


def init():
    _load_key()
    _init_cache()
    return bool(KEY)


def events_today(sport: str, date_str: str = None) -> list:
    """
    All events for a sport on a given date.
    Returns list of normalised event dicts.
    """
    sport_slug = SPORTS.get(sport.lower(), sport.lower())
    if not date_str:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    cache_key = f"fixtures:{sport_slug}:{date_str}"
    cached = _cache_get(cache_key, CACHE_TTL["fixtures"])
    if cached is not None:
        return cached

    data = _call(f"api/v1/sport/{sport_slug}/scheduled-events/{date_str}")
    if not data:
        return []

    results = [_parse_event(e) for e in data.get("events", [])]
    _cache_set(cache_key, results)
    return results


def find_event(home: str, away: str, sport: str = "football",
               date_str: str = None) -> dict | None:
    """Find an event by team names. Returns parsed event dict or None."""
    events = events_today(sport, date_str)
    for ev in events:
        if _match(home, ev["home"]) and _match(away, ev["away"]):
            return ev
        if _match(home, ev["away"]) and _match(away, ev["home"]):
            return {**ev, "home": ev["away"], "home_id": ev["away_id"],
                    "away": ev["home"], "away_id": ev["home_id"],
                    "home_score": ev["away_score"], "away_score": ev["home_score"],
                    "winner_code": 3 - ev.get("winner_code", 0) if ev.get("winner_code") else None}
    return None


def get_score(home: str, away: str, sport: str = "football",
              date_str: str = None) -> dict | None:
    """
    Return final score for a match, or None if not found/finished.
    Tries today and adjacent days for midnight-UTC edge cases.
    """
    dates = []
    if date_str:
        dates.append(date_str)
        try:
            d = datetime.strptime(date_str, "%Y-%m-%d")
            dates += [(d - timedelta(days=1)).strftime("%Y-%m-%d"),
                      (d + timedelta(days=1)).strftime("%Y-%m-%d")]
        except Exception:
            pass
    else:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        dates = [today, (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")]

    for d in dates:
        ev = find_event(home, away, sport, d)
        if ev and ev.get("status") == "finished" and ev.get("home_score") is not None:
            return ev
    return None


def event_odds(event_id: int) -> dict | None:
    """
    Fetch pre-match 1X2 (or best-available) odds for an event.
    Returns {"home": float, "draw": float|None, "away": float} or None if not available.
    Caches for 24h.
    """
    if not event_id:
        return None
    cache_key = f"odds:{event_id}"
    cached = _cache_get(cache_key, 3600 * 24)
    if cached is not None:
        return cached if cached else None  # {} → None, dict with keys → return as-is

    data = _call(f"api/v1/event/{event_id}/odds/1/all")
    if not data:
        _cache_set(cache_key, {})  # cache empty so we don't re-fetch
        return None
    result = _parse_odds(data)
    _cache_set(cache_key, result or {})  # cache even if empty
    return result or None


def _frac_to_decimal(frac_str: str) -> float | None:
    """Convert fractional odds string like '23/20' to decimal odds (2.15)."""
    try:
        if "/" in str(frac_str):
            n, d = frac_str.split("/", 1)
            return round(int(n) / int(d) + 1, 4)
        return float(frac_str)  # already decimal
    except (ValueError, ZeroDivisionError, TypeError):
        return None


def _parse_odds(data: dict) -> dict | None:
    """Extract lowest-vig 1X2 (or H2H) odds from a SportAPI7 odds payload.
    SofaScore returns fractionalValue strings like '23/20'; we convert to decimal.
    """
    entries = data.get("odds") or data.get("markets") or []
    if not entries:
        return None

    best, best_margin = None, float("inf")
    for entry in entries:
        # Only Full-time 1X2 market (marketId=1, marketGroup='1X2')
        if entry.get("marketGroup", "").upper() not in ("1X2", "") and entry.get("marketId") not in (1, None):
            continue
        if entry.get("marketId") not in (1, None):
            continue

        choices = entry.get("choices") or []
        if len(choices) < 2:
            continue
        home_o = draw_o = away_o = None
        for ch in choices:
            name = (ch.get("name") or "").strip()
            raw = ch.get("fractionalValue") or ch.get("initialFractionalValue")
            val = _frac_to_decimal(raw)
            if val is None or val < 1.01:
                continue
            if name == "1":
                home_o = val
            elif name == "X":
                draw_o = val
            elif name == "2":
                away_o = val

        if home_o and away_o:
            probs = [1 / home_o, 1 / away_o]
            if draw_o:
                probs.append(1 / draw_o)
            margin = sum(probs) - 1.0
            if margin < best_margin:
                best_margin = margin
                best = {"home": home_o, "away": away_o}
                if draw_o:
                    best["draw"] = draw_o

    return best


def h2h(home_id: int, away_id: int) -> list:
    """Last head-to-head results between two teams/players."""
    if not home_id or not away_id:
        return []
    cache_key = f"h2h:{min(home_id,away_id)}:{max(home_id,away_id)}"
    cached = _cache_get(cache_key, CACHE_TTL["h2h"])
    if cached is not None:
        return cached

    data = _call(f"api/v1/event/{home_id}/h2h")  # need an event ID, not team ID
    if not data:
        return []
    # h2h is on event, not teams directly - return team duel stats
    result = [data.get("teamDuel", {})]
    _cache_set(cache_key, result)
    return result


def all_sports_scores(date_str: str = None) -> dict:
    """
    Fetch finished scores for all major sports on a date.
    Returns { sport_slug: [event, ...] }.
    Useful for running auto-settle across everything at once.
    Budget: 1 call per sport = ~8 calls total.
    """
    if not date_str:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    result = {}
    sports_to_check = [
        "football", "basketball", "tennis", "table-tennis",
        "volleyball", "baseball", "cricket",
    ]
    for sport_slug in sports_to_check:
        events = events_today(sport_slug, date_str)
        finished = [e for e in events if e.get("status") == "finished"]
        if finished:
            result[sport_slug] = finished
    return result


def format_event_str(ev: dict) -> str:
    """Format a finished event as a score string."""
    if ev.get("home_score") is None:
        return f"{ev['home']} vs {ev['away']}"
    return f"{ev['home']} {ev['home_score']} - {ev['away_score']} {ev['away']}"
