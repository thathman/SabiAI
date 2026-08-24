#!/usr/bin/env python3
"""sportybet_odds.py — read-only SportyBet NG odds via the public factsCenter API.

Plain HTTP (no Playwright). Exposes corner/card/foul Over-Under prop odds so they
can be matched against SabiAI's stat models for live/pre-match value.

Read-only — never places bets (see sportybet_book.py for placement).

Prop availability: SportyBet only lists corner/card/foul markets for major matches
near or during kickoff. Minor/amateur fixtures return no prop markets.
"""
import json, re, time, urllib.request
from difflib import SequenceMatcher

BASE   = "https://www.sportybet.com/api/ng/factsCenter"
UA     = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
REF    = "https://www.sportybet.com/ng/sport/football"
SOCCER = "sr:sport:1"

# Betradar market IDs (via SportyBet) → our stat-model market name
PROP_MARKETS = {
    "166":    "corners",   # Corners - Over/Under
    "800063": "cards",     # Match Cards (count)
    "900342": "fouls",     # Fouls Over/Under
}


def _get(path, timeout=12):
    url = f"{BASE}/{path}{'&' if '?' in path else '?'}_t={int(time.time())}000"
    req = urllib.request.Request(
        url, headers={"User-Agent": UA, "Referer": REF, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def _norm(s):
    return "".join(ch for ch in (s or "").lower() if ch.isalnum())


def _sim(a, b):
    return SequenceMatcher(None, _norm(a), _norm(b)).ratio()


def _events_from(data):
    out, cats = [], (data if isinstance(data, list)
                     else data.get("tournaments", []) if isinstance(data, dict) else [])
    for cat in cats:
        for e in cat.get("events", []):
            out.append({"eventId": e.get("eventId"), "home": e.get("homeTeamName"),
                        "away": e.get("awayTeamName"), "status": e.get("matchStatus"),
                        "clock": e.get("playedSeconds")})
    return out


def live_events(timeout=12):
    """In-play soccer events: [{eventId, home, away, status, clock}]."""
    try:
        d = _get(f"liveOrPrematchEvents?sportId={SOCCER}&marketId=1&pageSize=100&pageNum=1&option=1", timeout)
        return _events_from(d.get("data"))
    except Exception:
        return []


def upcoming_events(page_size=60, timeout=12):
    """Upcoming (pre-match) soccer events."""
    try:
        d = _get(f"pcUpcomingEvents?sportId={SOCCER}&marketId=1&pageSize={page_size}&pageNum=1&option=1", timeout)
        return _events_from(d.get("data"))
    except Exception:
        return []


def find_event(home, away, events, min_sim=0.6):
    """Match our fixture to a SportyBet event by team-name similarity."""
    best, best_score = None, 0.0
    for e in events:
        s = (_sim(home, e["home"]) + _sim(away, e["away"])) / 2
        if s > best_score:
            best, best_score = e, s
    return best if best and best_score >= min_sim else None


def prop_odds(event_id, timeout=12):
    """Return {market: [ {line, over, under}, ... ]} for corners/cards/fouls.
    Each market can carry several lines; the caller picks the one nearest its model.
    """
    try:
        d = _get(f"event?eventId={event_id}&productId=3", timeout)
    except Exception:
        return {}
    mks = (d.get("data") or {}).get("markets", [])
    out = {}
    for m in mks:
        name = PROP_MARKETS.get(m.get("id"))
        if not name:
            continue
        over = under = line = None
        spec = m.get("specifier", "") or ""
        ms = re.search(r"(?:total|hcp)?=?\s*(\d+(?:\.\d+)?)", spec)
        if ms:
            line = float(ms.group(1))
        for o in m.get("outcomes", []):
            desc = (o.get("desc") or "").lower()
            try:
                odd = float(o.get("odds"))
            except (TypeError, ValueError):
                continue
            if "over" in desc:
                over = odd
            elif "under" in desc:
                under = odd
        if over and under and line is not None:
            out.setdefault(name, []).append({"line": line, "over": over, "under": under})
    for name in out:
        out[name].sort(key=lambda x: x["line"])
    return out


def line_for(market_lines, target_line):
    """From a market's lines, return the entry nearest target_line (e.g. our model line)."""
    if not market_lines:
        return None
    return min(market_lines, key=lambda x: abs(x["line"] - target_line))


def all_upcoming(max_pages=8, page_size=100, timeout=12):
    """Paginate pcUpcomingEvents to index the day's soccer slate (beyond the
    popular/featured first page). Returns the same event dicts as upcoming_events."""
    out, seen = [], set()
    for pg in range(1, max_pages + 1):
        try:
            d = _get(f"pcUpcomingEvents?sportId={SOCCER}&marketId=1&pageSize={page_size}&pageNum={pg}&option=1", timeout)
        except Exception:
            break
        evs = _events_from(d.get("data"))
        if not evs:
            break
        new = 0
        for e in evs:
            if e["eventId"] and e["eventId"] not in seen:
                seen.add(e["eventId"]); out.append(e); new += 1
        if new == 0:
            break
    return out


def event_odds_internal(event_id, home_name, away_name, timeout=8):
    """Return a bookmaker dict in value_bet_finder's internal event shape:
       {"key","title","markets":[{"key":"h2h"|"totals","outcomes":[...]}]}
    h2h outcomes are keyed by the caller's home/away names (+ "Draw") so they
    line up with model_h2h / consensus_fair. Returns None on any failure."""
    try:
        d = _get(f"event?eventId={event_id}&productId=3", timeout)
    except Exception:
        return None
    mks = (d.get("data") or {}).get("markets", [])
    markets = []
    # 1X2 → h2h
    m1 = next((m for m in mks if m.get("id") == "1"), None)
    if m1:
        outs = []
        for o in m1.get("outcomes", []):
            desc = (o.get("desc") or "").strip().lower()
            try:
                price = float(o.get("odds"))
            except (TypeError, ValueError):
                continue
            name = home_name if desc == "home" else away_name if desc == "away" else "Draw" if desc == "draw" else None
            if name:
                outs.append({"name": name, "price": price})
        if len(outs) == 3:
            markets.append({"key": "h2h", "outcomes": outs})
    # Over/Under goals → totals (main lines only)
    tot_outs = []
    for m in mks:
        if m.get("id") != "18":
            continue
        spec = m.get("specifier", "") or ""
        ms = re.search(r"total=(\d+(?:\.\d+)?)", spec)
        if not ms:
            continue
        line = float(ms.group(1))
        if line not in (1.5, 2.5, 3.5):
            continue
        for o in m.get("outcomes", []):
            desc = (o.get("desc") or "").lower()
            try:
                price = float(o.get("odds"))
            except (TypeError, ValueError):
                continue
            side = "Over" if "over" in desc else "Under" if "under" in desc else None
            if side:
                tot_outs.append({"name": f"{side} {line:g}", "price": price, "point": line})
    if tot_outs:
        markets.append({"key": "totals", "outcomes": tot_outs})
    if not markets:
        return None
    return {"key": "sportybet", "title": "SportyBet", "markets": markets}


if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 3:
        home, away = sys.argv[1], sys.argv[2]
        evs = (live_events() or []) + upcoming_events()
        ev = find_event(home, away, evs)
        if not ev:
            print(f"No SportyBet event for {home} vs {away}")
            sys.exit(0)
        print(f"Matched: {ev['home']} vs {ev['away']} [{ev['status']} {ev['clock']}] {ev['eventId']}")
        print(json.dumps(prop_odds(ev["eventId"]), indent=2))
    else:
        print(f"live events: {len(live_events())} | upcoming: {len(upcoming_events())}")
