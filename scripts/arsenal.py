#!/usr/bin/env python3
"""arsenal.py — Hendrix's Arsenal matchday companion (Fun lane).

THE SACRED RULE (non-negotiable, applied by `matchday` / cron):
  • Arsenal WIN  → celebrate freely, loud and proud.
  • Arsenal LOSE or DRAW → SILENCE. Say nothing. Let him process it alone.
Manual commands (`last`, `next`, `form`) always answer honestly when he asks —
the silence rule only governs the *unprompted* matchday push.

Data: ESPN public API (team id 359, eng.1). No key needed.
Tracks what we've already reacted to in a tiny state file so we celebrate once.

Commands:
  next        next fixture + countdown (off-season aware)
  last        last result (honest — only when asked)
  form        last 5 results (W/D/L)
  matchday    cron entry: prints a celebration ONLY if the latest finished
              game is an unreacted WIN; otherwise prints nothing (exit 0)
  summary     JSON for the dashboard
"""
import json, os, sys, urllib.request
from datetime import datetime, timezone

TEAM = "359"
BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1"
STATE = os.path.expanduser("~/.openclaw/workspace/data/arsenal_state.json")
ARSENAL = "Arsenal"

def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (openclaw arsenal)"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())

def _state():
    try:
        return json.load(open(STATE))
    except Exception:
        return {}

def _save_state(s):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    json.dump(s, open(STATE, "w"), indent=2)

def _parse_event(e):
    c = e["competitions"][0]
    comps = c["competitors"]
    us = next((x for x in comps if x["team"]["displayName"] == ARSENAL), None)
    them = next((x for x in comps if x["team"]["displayName"] != ARSENAL), None)
    if not us or not them:
        return None
    status = c["status"]["type"]["name"]
    completed = c["status"]["type"].get("completed", False)
    us_score = us.get("score", {})
    us_score = us_score.get("value") if isinstance(us_score, dict) else us_score
    them_score = them.get("score", {})
    them_score = them_score.get("value") if isinstance(them_score, dict) else them_score
    return {
        "id": e.get("id"),
        "date": e.get("date"),
        "name": e.get("name"),
        "home_away": us.get("homeAway"),
        "opponent": them["team"]["displayName"],
        "us_score": int(us_score) if us_score is not None else None,
        "them_score": int(them_score) if them_score is not None else None,
        "winner": us.get("winner"),
        "completed": completed,
        "status": status,
    }

def _schedule():
    d = _get(f"{BASE}/teams/{TEAM}/schedule")
    out = []
    for e in d.get("events", []):
        p = _parse_event(e)
        if p:
            out.append(p)
    out.sort(key=lambda x: x["date"] or "")
    return out

def _result(m):
    """'win' | 'loss' | 'draw' from a completed match."""
    if m["us_score"] is None or m["them_score"] is None:
        return None
    if m["us_score"] > m["them_score"]:
        return "win"
    if m["us_score"] < m["them_score"]:
        return "loss"
    return "draw"

def last_completed():
    done = [m for m in _schedule() if m["completed"]]
    return done[-1] if done else None

def next_fixture():
    now = datetime.now(timezone.utc).isoformat()
    upcoming = [m for m in _schedule() if not m["completed"] and (m["date"] or "") >= now]
    return upcoming[0] if upcoming else None

def _countdown(iso):
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        days = (dt - datetime.now(timezone.utc)).days
        return dt, days
    except Exception:
        return None, None

def _scoreline(m):
    if m["home_away"] == "home":
        return f"Arsenal {m['us_score']}-{m['them_score']} {m['opponent']}"
    return f"{m['opponent']} {m['them_score']}-{m['us_score']} Arsenal"

# ---------- celebration copy (WIN only) ----------
def celebration(m):
    line = _scoreline(m)
    margin = m["us_score"] - m["them_score"]
    if m["us_score"] >= 4:
        hype = "We battered them. 🔴⚪️"
    elif margin >= 3:
        hype = "Comfortable. Class showed. 🔴⚪️"
    elif m["them_score"] == 0:
        hype = "Clean sheet and the three points. Solid. 🔴⚪️"
    elif margin == 1:
        hype = "Nervy one but we got it done. COYG! 🔴⚪️"
    else:
        hype = "Get in! Up the Arsenal! 🔴⚪️"
    return f"🎉 ARSENAL WIN — {line}\n{hype}"

def cmd_matchday():
    """Unprompted push. Celebrate ONLY a fresh WIN; otherwise stay silent."""
    m = last_completed()
    if not m:
        return  # nothing to say
    st = _state()
    if st.get("last_reacted_id") == m["id"]:
        return  # already reacted to this game
    res = _result(m)
    # Mark as seen regardless, so we never re-litigate a loss/draw later.
    st["last_reacted_id"] = m["id"]
    st["last_result"] = res
    st["last_match"] = _scoreline(m)
    _save_state(st)
    if res == "win":
        print(celebration(m))
    # loss/draw → print nothing. Sacred silence.

def cmd_last():
    m = last_completed()
    if not m:
        print("No recent Arsenal match found."); return
    res = _result(m)
    when, _ = _countdown(m["date"])
    when = when.strftime("%a %d %b") if when else m["date"]
    emoji = {"win": "✅", "loss": "❌", "draw": "➖"}.get(res, "")
    print(f"{emoji} {when}: {_scoreline(m)} ({res})")

def cmd_next():
    m = next_fixture()
    if not m:
        print("No fixture scheduled yet — off-season. Next season's dates drop soon. 🔴⚪️")
        return
    dt, days = _countdown(m["date"])
    venue = "home vs" if m["home_away"] == "home" else "away at"
    when = dt.strftime("%a %d %b, %H:%M UTC") if dt else m["date"]
    cd = f"in {days} day{'s' if days != 1 else ''}" if days is not None else ""
    print(f"⚽ Next: Arsenal {venue} {m['opponent']} — {when} ({cd})")

def cmd_form():
    done = [m for m in _schedule() if m["completed"]][-5:]
    if not done:
        print("No results yet."); return
    seq = "".join({"win": "W", "loss": "L", "draw": "D"}.get(_result(m), "?") for m in done)
    print(f"Last 5: {seq}")
    for m in done:
        print(f"   {_scoreline(m)}")

def cmd_summary():
    m = last_completed(); n = next_fixture()
    done = [x for x in _schedule() if x["completed"]][-5:]
    print(json.dumps({
        "last": {"scoreline": _scoreline(m), "result": _result(m), "date": m["date"]} if m else None,
        "next": {"opponent": n["opponent"], "home_away": n["home_away"], "date": n["date"]} if n else None,
        "form": "".join({"win": "W", "loss": "L", "draw": "D"}.get(_result(x), "?") for x in done),
    }, indent=2, default=str))

def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "summary"
    {
        "matchday": cmd_matchday, "last": cmd_last, "next": cmd_next,
        "form": cmd_form, "summary": cmd_summary,
    }.get(cmd, cmd_summary)()

if __name__ == "__main__":
    main()
