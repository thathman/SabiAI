#!/usr/bin/env python3
"""nfl_elo.py — NFL win probabilities from nfelo's published model ratings.

nfelo (github.com/greerreNFL/nfelo) is an open-source NFL Elo model adapted
from 538's framework, with QB adjustments. The repo publishes current ratings
to output_data/elo_snapshot.csv after every week of the season. We consume
those ratings directly rather than running their data pipeline.

P(home) = 1 / (1 + 10^(-(elo_home - elo_away + HFA) / 400))
HFA ≈ 52 Elo points (nfelo's average home-field mod).

Usage:
    from nfl_elo import nfl_probs
    nfl_probs("Kansas City Chiefs", "Buffalo Bills")
    → {"home": 0.58, "away": 0.42, "label": "nfelo (2025 wk22)"} or None
"""
import json, os, sqlite3, time, urllib.request

SNAPSHOT_URL = "https://raw.githubusercontent.com/greerreNFL/nfelo/main/output_data/elo_snapshot.csv"
CACHE_DB = "~.openclaw/workspace/data/sofascore_cache.db"
CACHE_KEY = "nfelo:snapshot"
CACHE_TTL = 24 * 3600          # ratings change at most weekly in season
HFA_ELO = 52.0

# nfelo team abbreviations → full names as used by TheRundown / ESPN
TEAMS = {
    "ARI": "Arizona Cardinals",   "ATL": "Atlanta Falcons",    "BAL": "Baltimore Ravens",
    "BUF": "Buffalo Bills",       "CAR": "Carolina Panthers",  "CHI": "Chicago Bears",
    "CIN": "Cincinnati Bengals",  "CLE": "Cleveland Browns",   "DAL": "Dallas Cowboys",
    "DEN": "Denver Broncos",      "DET": "Detroit Lions",      "GB":  "Green Bay Packers",
    "HOU": "Houston Texans",      "IND": "Indianapolis Colts", "JAX": "Jacksonville Jaguars",
    "KC":  "Kansas City Chiefs",  "LAC": "Los Angeles Chargers","LAR": "Los Angeles Rams",
    "LV":  "Las Vegas Raiders",   "MIA": "Miami Dolphins",     "MIN": "Minnesota Vikings",
    "NE":  "New England Patriots","NO":  "New Orleans Saints", "NYG": "New York Giants",
    "NYJ": "New York Jets",       "PHI": "Philadelphia Eagles","PIT": "Pittsburgh Steelers",
    "SEA": "Seattle Seahawks",    "SF":  "San Francisco 49ers","TB":  "Tampa Bay Buccaneers",
    "TEN": "Tennessee Titans",    "WAS": "Washington Commanders",
}
_NAME_TO_ABBR = {v.lower(): k for k, v in TEAMS.items()}
# Common short forms seen in odds feeds
_ALIASES = {
    "la chargers": "LAC", "la rams": "LAR", "ny giants": "NYG", "ny jets": "NYJ",
    "washington football team": "WAS", "washington redskins": "WAS",
    "oakland raiders": "LV", "san diego chargers": "LAC", "st. louis rams": "LAR",
    "jacksonville": "JAX", "arizona": "ARI", "niners": "SF", "49ers": "SF",
}

_mem: dict = {}


def _cache_get():
    try:
        c = sqlite3.connect(CACHE_DB)
        row = c.execute("SELECT data, stored_at FROM cache WHERE key=?", (CACHE_KEY,)).fetchone()
        c.close()
        if row and (time.time() - row[1]) < CACHE_TTL:
            return json.loads(row[0])
    except Exception:
        pass
    return None


def _cache_set(data):
    try:
        c = sqlite3.connect(CACHE_DB)
        c.execute("CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, data TEXT NOT NULL, stored_at INTEGER NOT NULL)")
        c.execute("INSERT OR REPLACE INTO cache VALUES (?,?,?)", (CACHE_KEY, json.dumps(data), int(time.time())))
        c.commit(); c.close()
    except Exception:
        pass


def _load_ratings():
    """{abbr: {"elo": float, "season": int, "week": int}} from the latest snapshot."""
    if _mem:
        return _mem
    cached = _cache_get()
    if cached:
        _mem.update(cached)
        return _mem
    try:
        req = urllib.request.Request(SNAPSHOT_URL, headers={"User-Agent": "Mozilla/5.0"})
        raw = urllib.request.urlopen(req, timeout=10).read().decode()
    except Exception:
        return _mem
    lines = raw.strip().split("\n")
    header = lines[0].split(",")
    idx = {h: i for i, h in enumerate(header)}
    out = {}
    for line in lines[1:]:
        cols = line.split(",")
        try:
            team = cols[idx["team"]]
            out[team] = {
                "elo": float(cols[idx["nfelo"]]),          # base + QB adjustment
                "season": int(cols[idx["season"]]),
                "week": int(cols[idx["week"]]),
            }
        except (KeyError, ValueError, IndexError):
            continue
    if out:
        _mem.update(out)
        _cache_set(out)
    return _mem


def _abbr(team_name: str):
    t = (team_name or "").lower().strip()
    if t in _NAME_TO_ABBR:
        return _NAME_TO_ABBR[t]
    if t in _ALIASES:
        return _ALIASES[t]
    if t.upper() in TEAMS:
        return t.upper()
    # Last-word match: "Chiefs" → Kansas City Chiefs
    for full, ab in _NAME_TO_ABBR.items():
        if t and (t in full or full.split()[-1] == t.split()[-1]):
            return ab
    return None


def nfl_probs(home: str, away: str):
    """Win probabilities for an NFL matchup, or None if either team is unknown."""
    ratings = _load_ratings()
    if not ratings:
        return None
    ha, aa = _abbr(home), _abbr(away)
    if not ha or not aa or ha not in ratings or aa not in ratings:
        return None
    rh, ra = ratings[ha], ratings[aa]
    diff = rh["elo"] - ra["elo"] + HFA_ELO
    p_home = 1.0 / (1.0 + 10 ** (-diff / 400.0))
    season = max(rh["season"], ra["season"])
    week = max(rh["week"], ra["week"])
    return {"home": round(p_home, 4), "away": round(1 - p_home, 4),
            "label": f"nfelo ({season} wk{week})"}


if __name__ == "__main__":
    r = _load_ratings()
    print(f"Ratings loaded: {len(r)} teams")
    top = sorted(r.items(), key=lambda kv: -kv[1]["elo"])[:5]
    for ab, d in top:
        print(f"  {TEAMS.get(ab, ab):28s} {d['elo']:7.1f}  ({d['season']} wk{d['week']})")
    demo = nfl_probs("Seattle Seahawks", "New England Patriots")
    print("Seahawks v Patriots:", demo)
