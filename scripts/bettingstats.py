#!/usr/bin/env python3
"""bettingstats.py — per-team soccer stats from bettingstats.org match pages.

Their Next.js match pages embed full per-team stat JSON (BTTS %, Over X.5 %,
average corners, cards, shots) computed from recent matches — covering 130+
leagues including internationals that football-data.co.uk doesn't track.

Used as the market-stats fallback in value_bet_finder when no fdco history
exists (friendlies, World Cup, minor leagues). Cached 12h.

Usage:
    from bettingstats import match_stats
    s = match_stats("Azerbaijan", "San Marino", "2026-06-09")
    → {"home": {"btts_pct": .67, "ou25_pct": .33, "avg_corners": 9.7,
                "avg_cards": 1.3, "n": 3}, "away": {...}}  or None
"""
import json, re, sqlite3, time, unicodedata, urllib.request

BASE = "https://bettingstats.org/match-details"
CACHE_DB = "~.openclaw/workspace/data/sofascore_cache.db"
CACHE_TTL = 12 * 3600
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"


def _cache_get(key):
    try:
        c = sqlite3.connect(CACHE_DB)
        row = c.execute("SELECT data, stored_at FROM cache WHERE key=?", (key,)).fetchone()
        c.close()
        if row and (time.time() - row[1]) < CACHE_TTL:
            return json.loads(row[0])
    except Exception:
        pass
    return None


def _cache_set(key, data):
    try:
        c = sqlite3.connect(CACHE_DB)
        c.execute("CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, data TEXT NOT NULL, stored_at INTEGER NOT NULL)")
        c.execute("INSERT OR REPLACE INTO cache VALUES (?,?,?)", (key, json.dumps(data), int(time.time())))
        c.commit(); c.close()
    except Exception:
        pass


def _slug(team: str) -> str:
    s = unicodedata.normalize("NFKD", team or "")
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    s = s.lower().replace("&", "and")
    s = re.sub(r"[^a-z0-9 -]", "", s)
    return re.sub(r"\s+", "-", s.strip())


def _extract_team_stats(html: str) -> list:
    """The page embeds two stat objects (home first, away second)."""
    raw = html.replace('\\"', '"')
    out = []
    for m in re.finditer(r'\{[^{}]*"avg_corners_total"[^{}]*\}', raw):
        try:
            out.append(json.loads(m.group(0)))
        except Exception:
            continue
    return out


def _simplify(o: dict) -> dict:
    def pct(key):
        v = o.get(key)
        return round(v / 100.0, 4) if isinstance(v, (int, float)) else None
    return {
        "n":            o.get("matches_played"),
        "btts_pct":     pct("btts_pct"),
        "ou15_pct":     pct("over_1_5_pct"),
        "ou25_pct":     pct("over_2_5_pct"),
        "ou35_pct":     pct("over_3_5_pct"),
        "avg_corners":  o.get("avg_corners_total"),
        "avg_cards":    o.get("avg_yellow_cards"),
        "avg_red_cards": o.get("avg_red_cards"),
        "avg_shots":    o.get("avg_shots"),
        "avg_shots_on_target": o.get("avg_shots_on_target"),
        "avg_fouls":    o.get("avg_fouls"),
        "avg_offsides": o.get("avg_offsides"),
        "avg_free_kicks": o.get("avg_free_kicks"),
    }


def match_stats(home: str, away: str, date_str: str):
    """date_str: YYYY-MM-DD. Returns {"home": {...}, "away": {...}} or None."""
    try:
        d, m, y = date_str[8:10], date_str[5:7], date_str[0:4]
    except Exception:
        return None
    slug = f"{_slug(home)}-{_slug(away)}-{d}-{m}-{y}"
    key = f"bstats:{slug}"
    cached = _cache_get(key)
    if cached is not None:
        return cached or None        # cached {} = known miss
    url = f"{BASE}/{slug}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        html = urllib.request.urlopen(req, timeout=12).read().decode("utf-8", "ignore")
    except Exception:
        _cache_set(key, {})          # cache the miss to avoid refetch storms
        return None
    teams = _extract_team_stats(html)
    if len(teams) < 2:
        _cache_set(key, {})
        return None
    result = {"home": _simplify(teams[0]), "away": _simplify(teams[1])}
    _cache_set(key, result)
    return result


if __name__ == "__main__":
    import sys
    h, a, dt = (sys.argv[1:4] + ["Azerbaijan", "San Marino", "2026-06-09"])[:3] \
        if len(sys.argv) >= 4 else ("Azerbaijan", "San Marino", "2026-06-09")
    s = match_stats(h, a, dt)
    print(json.dumps(s, indent=2) if s else f"No stats for {h} vs {a} on {dt}")
