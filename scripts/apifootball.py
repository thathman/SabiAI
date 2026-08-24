#!/usr/bin/env python3
"""apifootball.py — API-Football.com integration for SabiAI.

Free plan: 100 calls/day. Every call is counted — use the cache aggressively.

Budget per daily run:
  1  call  → fixtures (all leagues, today)
  1  call  → finished results (auto-settle)
  ≤30 calls → predictions for top picks
  ≤20 calls → team stats (cached 48h, so usually 0)
  ≤10 calls → H2H for strongest picks

Base URL: https://v3.football.api-sports.io/
Auth:    x-apisports-key header

Coverage (vs current stack):
  TheRundown   → ~25 major leagues, odds-based
  ESPN         → ~70 leagues, form only (no odds)
  API-Football → 1000+ competitions worldwide, fixtures + scores + predictions + form + H2H
"""

import json, os, sqlite3, time, unicodedata, re, urllib.request
from datetime import datetime, timezone, timedelta

# ── Config ────────────────────────────────────────────────────────────────────
BASE_URL   = "https://v3.football.api-sports.io"
KEY        = ""   # loaded from env/secrets
CACHE_DB   = "~.openclaw/workspace/data/apif_cache.db"
SECRETS    = "~.config/systemd/user/openclaw-gateway.service.d/20-secrets.conf"

# How long to cache different response types
CACHE_TTL = {
    "fixtures_day":  3600 * 6,    # 6h — re-fetch if stale
    "results_day":   3600 * 24,   # 24h — finished scores don't change
    "team_stats":    3600 * 48,   # 48h — season stats change weekly
    "predictions":   3600 * 12,   # 12h — predictions stable pre-game
    "h2h":           3600 * 72,   # 72h — H2H history rarely changes
    "team_search":   3600 * 168,  # 1 week — team IDs are permanent
}

_calls_today = 0


def _load_key():
    global KEY
    import re as _re
    KEY = os.environ.get("API_FOOTBALL_KEY", "")
    if not KEY:
        try:
            with open(SECRETS) as f:
                for line in f:
                    if "API_FOOTBALL_KEY" in line:
                        # Handles: Environment="API_FOOTBALL_KEY=value"
                        m = _re.search(r'API_FOOTBALL_KEY=([^"\s\']+)', line)
                        if m:
                            KEY = m.group(1)
                            break
        except Exception:
            pass


def _init_cache():
    os.makedirs(os.path.dirname(CACHE_DB), exist_ok=True)
    c = sqlite3.connect(CACHE_DB)
    c.execute("""CREATE TABLE IF NOT EXISTS cache (
        key TEXT PRIMARY KEY,
        data TEXT NOT NULL,
        stored_at INTEGER NOT NULL
    )""")
    c.commit()
    c.close()


def _cache_get(key: str, ttl: int):
    try:
        c = sqlite3.connect(CACHE_DB)
        row = c.execute("SELECT data, stored_at FROM cache WHERE key=?", (key,)).fetchone()
        c.close()
        if row and (time.time() - row[1]) < ttl:
            return json.loads(row[0])
    except Exception:
        pass
    return None


def _cache_set(key: str, data):
    try:
        c = sqlite3.connect(CACHE_DB)
        c.execute("INSERT OR REPLACE INTO cache VALUES (?,?,?)",
                  (key, json.dumps(data), int(time.time())))
        c.commit()
        c.close()
    except Exception:
        pass


def _call(endpoint: str, params: dict = None) -> dict | None:
    global _calls_today
    if not KEY:
        return None
    qs = "&".join(f"{k}={v}" for k, v in (params or {}).items())
    url = f"{BASE_URL}/{endpoint}?{qs}" if qs else f"{BASE_URL}/{endpoint}"
    try:
        req = urllib.request.Request(url, headers={
            "x-apisports-key": KEY,
            "User-Agent": "Mozilla/5.0",
        })
        with urllib.request.urlopen(req, timeout=12) as r:
            data = json.load(r)
            _calls_today += 1
            return data
    except Exception:
        return None

# ── Name normalisation ────────────────────────────────────────────────────────
def _norm(s: str) -> str:
    """Lowercase, strip accents, remove punctuation."""
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"[^a-z0-9 ]", "", s.lower())
    return s.strip()


def _name_match(a: str, b: str, threshold=0.6) -> bool:
    """Fuzzy team name match — handles 'Man City' vs 'Manchester City'."""
    na, nb = _norm(a), _norm(b)
    if na == nb:
        return True
    if na in nb or nb in na:
        return True
    # Word overlap
    wa = set(na.split()); wb = set(nb.split())
    if wa and wb:
        overlap = len(wa & wb) / max(len(wa), len(wb))
        if overlap >= threshold:
            return True
    return False

# ── Public API ────────────────────────────────────────────────────────────────

def init():
    """Call once at startup."""
    _load_key()
    _init_cache()
    return bool(KEY)


def status() -> dict | None:
    """Account status + calls remaining today."""
    data = _call("status")
    return data.get("response") if data else None


def fixtures_today(date_str: str = None) -> list:
    """
    All fixtures for a date (default: today). Returns a list of normalised dicts:
      { fixture_id, home, home_id, away, away_id, league, league_id,
        country, kickoff, status, home_score, away_score }

    One API call, cached 6h.
    """
    if not date_str:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    cache_key = f"fixtures:{date_str}"
    cached = _cache_get(cache_key, CACHE_TTL["fixtures_day"])
    if cached is not None:
        return cached

    data = _call("fixtures", {"date": date_str})
    if not data:
        return []

    results = []
    for f in data.get("response", []):
        fix = f.get("fixture", {}); lg = f.get("league", {})
        teams = f.get("teams", {}); goals = f.get("goals", {})
        results.append({
            "fixture_id":  fix.get("id"),
            "home":        teams.get("home", {}).get("name", ""),
            "home_id":     teams.get("home", {}).get("id"),
            "away":        teams.get("away", {}).get("name", ""),
            "away_id":     teams.get("away", {}).get("id"),
            "league":      lg.get("name", ""),
            "league_id":   lg.get("id"),
            "country":     lg.get("country", ""),
            "season":      lg.get("season"),
            "kickoff":     fix.get("date", ""),
            "status":      fix.get("status", {}).get("short", ""),
            "status_long": fix.get("status", {}).get("long", ""),
            "home_score":  goals.get("home"),
            "away_score":  goals.get("away"),
        })
    _cache_set(cache_key, results)
    return results


def find_fixture(home: str, away: str, date_str: str = None) -> dict | None:
    """Find a fixture by team names. Returns the normalised fixture dict or None."""
    for fix in fixtures_today(date_str):
        if _name_match(home, fix["home"]) and _name_match(away, fix["away"]):
            return fix
        if _name_match(home, fix["away"]) and _name_match(away, fix["home"]):
            return {**fix, "home": fix["away"], "home_id": fix["away_id"],
                    "away": fix["home"], "away_id": fix["home_id"],
                    "home_score": fix["away_score"], "away_score": fix["home_score"]}
    return None


def results_today(date_str: str = None) -> list:
    """All finished (FT) fixtures for a date. Used for auto-settling. Cached 24h."""
    if not date_str:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    # Also check yesterday (midnight UTC games)
    all_results = []
    for d in [date_str, (datetime.strptime(date_str, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")]:
        cache_key = f"results:{d}"
        cached = _cache_get(cache_key, CACHE_TTL["results_day"])
        if cached is not None:
            all_results.extend(cached)
            continue
        data = _call("fixtures", {"date": d, "status": "FT"})
        if not data:
            continue
        day_results = []
        for f in data.get("response", []):
            fix = f.get("fixture", {}); lg = f.get("league", {})
            teams = f.get("teams", {}); goals = f.get("goals", {})
            day_results.append({
                "fixture_id": fix.get("id"),
                "home":       teams.get("home", {}).get("name", ""),
                "home_id":    teams.get("home", {}).get("id"),
                "away":       teams.get("away", {}).get("name", ""),
                "away_id":    teams.get("away", {}).get("id"),
                "league":     lg.get("name", ""),
                "league_id":  lg.get("id"),
                "country":    lg.get("country", ""),
                "home_score": goals.get("home"),
                "away_score": goals.get("away"),
                "date":       d,
            })
        _cache_set(cache_key, day_results)
        all_results.extend(day_results)
    return all_results


def get_score(home: str, away: str, date_str: str = None) -> dict | None:
    """
    Return {home_score, away_score, home, away} for a finished match, or None.
    Tries today and yesterday for midnight UTC games.
    """
    dates = []
    if date_str:
        dates.append(date_str)
        try:
            d = datetime.strptime(date_str, "%Y-%m-%d")
            dates.append((d - timedelta(days=1)).strftime("%Y-%m-%d"))
            dates.append((d + timedelta(days=1)).strftime("%Y-%m-%d"))
        except Exception:
            pass
    else:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        dates = [today, (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")]

    for d in dates:
        for fix in results_today(d):
            if _name_match(home, fix["home"]) and _name_match(away, fix["away"]):
                return fix
            if _name_match(home, fix["away"]) and _name_match(away, fix["home"]):
                return {**fix, "home": fix["away"], "away": fix["home"],
                        "home_score": fix["away_score"], "away_score": fix["home_score"]}
    return None


def predictions(fixture_id: int) -> dict | None:
    """
    Win/draw/loss probability + advice for a fixture.
    Returns { home_pct, draw_pct, away_pct, advice, winner } or None.
    """
    if not fixture_id:
        return None
    cache_key = f"pred:{fixture_id}"
    cached = _cache_get(cache_key, CACHE_TTL["predictions"])
    if cached is not None:
        return cached

    data = _call("predictions", {"fixture": fixture_id})
    if not data or not data.get("response"):
        return None

    pred = data["response"][0].get("predictions", {})
    pct  = pred.get("percent", {})
    winner = pred.get("winner", {}) or {}
    result = {
        "home_pct":  float((pct.get("home") or "0%").rstrip("%")),
        "draw_pct":  float((pct.get("draw") or "0%").rstrip("%")),
        "away_pct":  float((pct.get("away") or "0%").rstrip("%")),
        "advice":    pred.get("advice", ""),
        "winner_id": winner.get("id"),
        "winner":    winner.get("name", ""),
        "comment":   pred.get("comment", ""),
    }
    _cache_set(cache_key, result)
    return result


def team_stats(team_id: int, league_id: int, season: int = None) -> dict | None:
    """
    Team statistics for a season. Returns form string, goals avg, clean sheets etc.
    Cached 48h since season stats change slowly.
    """
    if not team_id or not league_id:
        return None
    if not season:
        season = datetime.now().year
    cache_key = f"stats:{team_id}:{league_id}:{season}"
    cached = _cache_get(cache_key, CACHE_TTL["team_stats"])
    if cached is not None:
        return cached

    data = _call("teams/statistics", {"team": team_id, "league": league_id, "season": season})
    if not data or not data.get("response"):
        return None

    r = data["response"]
    form = r.get("form", "")
    # Last 5 from form string
    last5 = form[-5:] if form else ""
    w5 = last5.count("W"); d5 = last5.count("D"); l5 = last5.count("L")

    goals_for  = r.get("goals", {}).get("for",  {}).get("average", {}).get("total")
    goals_ag   = r.get("goals", {}).get("against", {}).get("average", {}).get("total")
    clean_sh   = r.get("clean_sheet", {}).get("total")
    played     = r.get("fixtures", {}).get("played", {}).get("total", 0)

    result = {
        "team_id":    team_id,
        "league_id":  league_id,
        "season":     season,
        "form":       form,
        "form_last5": last5,
        "w5": w5, "d5": d5, "l5": l5,
        "goals_scored_avg":   float(goals_for)  if goals_for  else None,
        "goals_conceded_avg": float(goals_ag)   if goals_ag   else None,
        "clean_sheets":       clean_sh,
        "played":             played,
    }
    _cache_set(cache_key, result)
    return result


def h2h(team1_id: int, team2_id: int, last: int = 5) -> list:
    """Last N head-to-head results between two teams. Cached 72h."""
    if not team1_id or not team2_id:
        return []
    cache_key = f"h2h:{min(team1_id,team2_id)}:{max(team1_id,team2_id)}:{last}"
    cached = _cache_get(cache_key, CACHE_TTL["h2h"])
    if cached is not None:
        return cached

    data = _call("fixtures/headtohead", {"h2h": f"{team1_id}-{team2_id}", "last": last})
    if not data:
        return []

    results = []
    for f in data.get("response", []):
        teams = f.get("teams", {}); goals = f.get("goals", {})
        results.append({
            "home":       teams.get("home", {}).get("name", ""),
            "away":       teams.get("away", {}).get("name", ""),
            "home_score": goals.get("home"),
            "away_score": goals.get("away"),
            "date":       f.get("fixture", {}).get("date", "")[:10],
        })
    _cache_set(cache_key, results)
    return results


def format_form(stats: dict, team_name: str) -> str:
    """Format team_stats into a plain-English form string for rationale."""
    if not stats:
        return ""
    f5 = stats.get("form_last5", "")
    gf = stats.get("goals_scored_avg")
    ga = stats.get("goals_conceded_avg")
    parts = []
    if f5:
        parts.append(f"{team_name} recent form: {f5}")
    if gf is not None and ga is not None:
        parts.append(f"scoring {gf:.1f} and conceding {ga:.1f} per game this season")
    return " — ".join(parts) if parts else ""


def format_h2h(matches: list, home: str, away: str) -> str:
    """Format H2H results into a plain-English string."""
    if not matches:
        return ""
    parts = []
    for m in matches[:5]:
        hs = m.get("home_score"); aws = m.get("away_score")
        mh = m.get("home", ""); ma = m.get("away", "")
        date = m.get("date", "")[:7]  # YYYY-MM
        if hs is not None and aws is not None:
            parts.append(f"{mh} {hs}-{aws} {ma} ({date})")
    return "; ".join(parts)


def format_prediction(pred: dict, home: str, away: str) -> str:
    """Format API-Football prediction into a plain-English rationale snippet."""
    if not pred:
        return ""
    hp = pred.get("home_pct", 0)
    dp = pred.get("draw_pct", 0)
    ap = pred.get("away_pct", 0)
    advice = pred.get("advice", "")
    parts = [f"API-Football model: {home} {hp:.0f}% / Draw {dp:.0f}% / {away} {ap:.0f}%"]
    if advice and len(advice) < 100:
        parts.append(f"Their advice: {advice}.")
    return " ".join(parts)


# ── Auto-settle integration ───────────────────────────────────────────────────

def settle_football_bets(db_path: str) -> dict:
    """
    Settle pending football bets using API-Football scores.
    Returns {settled, won, lost, skipped}.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    pending = conn.execute("""
        SELECT id, match, kickoff, market, pick, odds
        FROM bets WHERE outcome IS NULL AND kickoff IS NOT NULL
        AND (sport LIKE '%soccer%' OR sport LIKE '%⚽%' OR sport LIKE '%football%'
             OR sport LIKE '%Friendl%' OR sport LIKE '%Liga%' OR sport LIKE '%League%'
             OR sport LIKE '%Premier%' OR sport LIKE '%Serie%' OR sport LIKE '%Bundes%')
    """).fetchall()

    if not pending:
        conn.close()
        return {"settled": 0, "won": 0, "lost": 0, "skipped": 0}

    import re as _re
    settled = won = lost = skipped = 0
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=2)).replace(tzinfo=None)

    for bet in pending:
        # Only settle if kickoff is past
        try:
            kdt = datetime.fromisoformat(bet["kickoff"].replace("Z", "+00:00")).replace(tzinfo=None)
            if kdt > cutoff:
                skipped += 1
                continue
        except Exception:
            skipped += 1
            continue

        # Parse home/away
        mv = _re.match(r"(.+?)\s+(?:vs\.?|v\.?|@|at)\s+(.+)", bet["match"] or "", _re.IGNORECASE)
        if not mv:
            skipped += 1
            continue
        home, away = mv.group(1).strip(), mv.group(2).strip()

        # Get score from API-Football
        score = get_score(home, away, bet["kickoff"][:10])
        if not score:
            skipped += 1
            continue

        hs = score.get("home_score"); aws = score.get("away_score")
        if hs is None or aws is None:
            skipped += 1
            continue

        # Determine outcome based on market/pick
        market = (bet["market"] or "").lower()
        pick   = (bet["pick"] or "").lower()
        outcome = None
        score_str = f"{score['home']} {hs} - {aws} {score['away']}"

        if "1x2" in market or "h2h" in market or "moneyline" in market or "match winner" in market or not market:
            # Who won?
            if hs > aws:
                winner = home.lower()
            elif aws > hs:
                winner = away.lower()
            else:
                winner = "draw"
            if _name_match(pick, winner) or ("draw" in pick and winner == "draw"):
                outcome = "win"
            else:
                outcome = "loss"

        elif "over" in pick or "under" in pick:
            line_m = _re.search(r"(\d+\.?\d*)", market)
            if line_m:
                line = float(line_m.group(1))
                total = hs + aws
                if "over" in pick:
                    outcome = "win" if total > line else "loss"
                else:
                    outcome = "win" if total < line else "loss"

        elif "btts" in market or "both teams" in market:
            both = (hs > 0 and aws > 0)
            if "yes" in pick:
                outcome = "win" if both else "loss"
            else:
                outcome = "win" if not both else "loss"

        if outcome:
            conn.execute("UPDATE bets SET outcome=?, result_score=?, settled_at=? WHERE id=?",
                         (outcome, score_str, datetime.now(timezone.utc).isoformat(), bet["id"]))
            settled += 1
            if outcome == "win": won += 1
            else: lost += 1
        else:
            skipped += 1

    conn.commit()
    conn.close()
    return {"settled": settled, "won": won, "lost": lost, "skipped": skipped}
