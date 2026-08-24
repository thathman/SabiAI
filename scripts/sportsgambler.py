#!/usr/bin/env python3
"""sportsgambler.py — soccer injury & suspension feed from sportsgambler.com.

They publish per-team injury tables (player, position, injury, expected return)
for the major leagues + FIFA World Cup, sourced from official team news.
No API — we parse the HTML. Cached 6h (they update around team-news cycles).

Usage:
    from sportsgambler import injuries_for_match
    txt = injuries_for_match("Arsenal", "Chelsea")
    → "Arsenal: Ben White (D, Knee, back 2026-07-20) | Chelsea: ..."  or ""
"""
import json, re, sqlite3, time, unicodedata, urllib.request

BASE = "https://www.sportsgambler.com/injuries/football"
CACHE_DB = "~.openclaw/workspace/data/sofascore_cache.db"
CACHE_TTL = 6 * 3600
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"

LEAGUE_SLUGS = [
    "fifa-world-cup",
    "england-premier-league",
    "spain-la-liga",
    "italy-serie-a",
    "germany-bundesliga",
    "uefa-champions-league",
]


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


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    return re.sub(r"[^a-z0-9 ]", "", s.lower()).strip()


def fetch_league(slug: str) -> dict:
    """{team_name: [{"player","position","injury","return"}]} for one league page."""
    key = f"sg:injuries:{slug}"
    cached = _cache_get(key)
    if cached is not None:
        return cached
    url = f"{BASE}/{slug}/"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        html = urllib.request.urlopen(req, timeout=15).read().decode("utf-8", "ignore")
    except Exception:
        return {}
    out = {}
    # Page is a sequence of <h3>Team</h3> ... rows until the next <h3>
    chunks = re.split(r"<h3[^>]*>", html)
    for chunk in chunks[1:]:
        team = re.sub(r"<[^>]+>", "", chunk.split("</h3>")[0]).strip()
        if not team:
            continue
        rows = []
        for m in re.finditer(
            r'<span class="inj-player">([^<]+)</span>\s*'
            r'<span class="inj-position[^"]*">([^<]*)</span>.*?'
            r'<span class="inj-info">([^<]*)</span>\s*'
            r'<span class="inj-return[^"]*">([^<]*)</span>',
            chunk, re.S):
            player, pos, info, ret = (x.strip() for x in m.groups())
            if player and player != "Name":
                rows.append({"player": player, "position": pos,
                             "injury": info, "return": ret})
        if rows:
            out[team] = rows
    _cache_set(key, out)
    return out


def _team_injuries(team_name: str) -> list:
    """Search all configured leagues for a team's injury list."""
    want = _norm(team_name)
    if not want:
        return []
    for slug in LEAGUE_SLUGS:
        data = fetch_league(slug)
        for team, rows in data.items():
            t = _norm(team)
            if t == want or want in t or t in want:
                return rows
    return []


def injuries_for_match(home: str, away: str, max_players: int = 4) -> str:
    """Human-readable injury summary for both teams, '' if nothing found."""
    parts = []
    for side in (home, away):
        rows = _team_injuries(side)
        if rows:
            players = ", ".join(
                f"{r['player']}" + (f" ({r['position']}, {r['injury']})" if r['injury'] else "")
                for r in rows[:max_players])
            more = f" +{len(rows)-max_players} more" if len(rows) > max_players else ""
            # "ruled out" phrasing is load-bearing: injury_prob_adjustment() in
            # value_bet_finder keys on it to apply the probability penalty.
            parts.append(f"{side} ruled out: {players}{more}")
    return " | ".join(parts)


if __name__ == "__main__":
    epl = fetch_league("england-premier-league")
    print(f"EPL teams with injuries: {len(epl)}")
    for team, rows in list(epl.items())[:3]:
        print(f"  {team}: {[r['player'] for r in rows]}")
    print()
    print("Match check:", injuries_for_match("Arsenal", "Aston Villa") or "(none)")
