#!/usr/bin/env python3
"""bridge.py — Hendrix's long-distance co-pilot for A'isha (Lagos ↔ North Carolina).

Helps him be a present husband and dad across the ocean: best call windows, important
dates, gestures, the reunion checklist, daughter milestones, and "she mentioned…" memory.

Commands:
  setup '<json>'        save config (timezones, dates, schedule)  [or pipe JSON on stdin]
  now                   both clocks + is it a good time to call?
  windows               today's good call windows (overlap of waking hours)
  dates                 upcoming important dates with countdowns
  goodnight             is it near the daughter's NC bedtime?
  gesture suggest|list  surprise ideas / log
  reunion [list|add|done] gap-closing checklist
  note '<text>'         log something A'isha mentioned (to follow up)
  notes                 open follow-ups
  milestone '<text>'    log a daughter milestone
  summary               one-glance status (used by dashboard + crons)
"""
import json, sqlite3, sys, os
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo

DB = os.path.expanduser("~/.openclaw/workspace/data/bridge.db")
DEFAULTS = {
    "aisha_name": "A'isha", "aisha_tz": "America/New_York", "hendrix_tz": "Africa/Lagos",
    "daughter_name": "", "daughter_birthday": "2024-05-13", "daughter_bedtime_nc": "19:30",
    "aisha_birthday": "", "anniversary": "",
    "aisha_wake": "07:00", "aisha_sleep": "22:30",
    "hendrix_wake": "07:00", "hendrix_sleep": "23:30",
}

def conn():
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row
    c.executescript("""
    CREATE TABLE IF NOT EXISTS config(key TEXT PRIMARY KEY, value TEXT);
    CREATE TABLE IF NOT EXISTS gestures(id INTEGER PRIMARY KEY AUTOINCREMENT,
      date TEXT, type TEXT, description TEXT, status TEXT DEFAULT 'idea', cost TEXT);
    CREATE TABLE IF NOT EXISTS reunion(id INTEGER PRIMARY KEY AUTOINCREMENT,
      step TEXT, category TEXT, status TEXT DEFAULT 'todo', due TEXT, notes TEXT);
    CREATE TABLE IF NOT EXISTS milestones(id INTEGER PRIMARY KEY AUTOINCREMENT,
      date TEXT, title TEXT, note TEXT, media_path TEXT);
    CREATE TABLE IF NOT EXISTS mentions(id INTEGER PRIMARY KEY AUTOINCREMENT,
      date TEXT, topic TEXT, note TEXT, followed_up INTEGER DEFAULT 0);
    CREATE TABLE IF NOT EXISTS stories(id INTEGER PRIMARY KEY AUTOINCREMENT,
      date TEXT, title TEXT, text TEXT, audio_path TEXT, sent INTEGER DEFAULT 0);
    """)
    return c

def cfg(c=None):
    own = c is None; c = c or conn()
    d = dict(DEFAULTS)
    d.update({r["key"]: r["value"] for r in c.execute("SELECT key,value FROM config")})
    if own: c.close()
    return d

def _hm(s):
    h, m = s.split(":"); return int(h), int(m)

def both_now():
    d = cfg()
    htz, atz = ZoneInfo(d["hendrix_tz"]), ZoneInfo(d["aisha_tz"])
    now = datetime.now(htz)
    return now, now.astimezone(atz), d

def is_awake(dt, wake, sleep):
    wh, wm = _hm(wake); sh, sm = _hm(sleep)
    t = dt.hour * 60 + dt.minute
    return wh*60+wm <= t <= sh*60+sm

def good_windows():
    """Return today's hourly slots where BOTH are awake; flag evenings as prime."""
    _, _, d = both_now()
    htz, atz = ZoneInfo(d["hendrix_tz"]), ZoneInfo(d["aisha_tz"])
    base = datetime.now(htz).replace(minute=0, second=0, microsecond=0)
    slots = []
    for h in range(0, 24):
        t = base.replace(hour=h)
        if t < datetime.now(htz) - timedelta(hours=1):
            t = t + timedelta(days=1)
        a = t.astimezone(atz)
        if is_awake(t, d["hendrix_wake"], d["hendrix_sleep"]) and \
           is_awake(a, d["aisha_wake"], d["aisha_sleep"]):
            prime = a.hour >= 18 or t.hour >= 18  # someone's evening = relaxed
            slots.append({"lagos": t.strftime("%a %H:%M"), "nc": a.strftime("%a %H:%M"),
                          "prime": prime, "ts": t.isoformat()})
    # collapse consecutive into ranges
    return slots

def next_window():
    htz = ZoneInfo(cfg()["hendrix_tz"]); nowts = datetime.now(htz)
    for s in good_windows():
        if datetime.fromisoformat(s["ts"]) >= nowts:
            return s
    return None

ANNIV_FILE = os.path.expanduser("~/.openclaw/workspace/data/anniversaries.json")

def _next_occurrence(mm, dd, today):
    try:
        nxt = date(today.year, mm, dd)
        if nxt < today:
            nxt = date(today.year + 1, mm, dd)
        return nxt
    except Exception:
        return None

def upcoming_dates():
    """Single source of truth = anniversaries.json (the rich LDR date system).
    Falls back to bridge config + daughter's birthday."""
    d = cfg(); out = []; today = date.today()
    # 1) anniversaries.json (A'isha's birthday, met-day, dating, engagement, marriages)
    try:
        data = json.load(open(ANNIV_FILE))
        for a in data.get("anniversaries", []):
            ds = a.get("date", "")  # "MM-DD"
            if "-" not in ds: continue
            mm, dd = int(ds[:2]), int(ds[3:5])
            nxt = _next_occurrence(mm, dd, today)
            if nxt:
                out.append({"what": a.get("title", "Date"), "date": nxt.isoformat(),
                            "in_days": (nxt - today).days})
    except Exception:
        pass
    # 2) daughter's birthday from config
    db = d.get("daughter_birthday")
    if db:
        try:
            nxt = _next_occurrence(int(db[5:7]), int(db[8:10]), today)
            if nxt:
                out.append({"what": f"{d.get('daughter_name') or 'Daughter'}'s birthday",
                            "date": nxt.isoformat(), "in_days": (nxt - today).days})
        except Exception: pass
    # de-dup by (what), keep soonest
    seen = {}
    for x in sorted(out, key=lambda x: x["in_days"]):
        seen.setdefault(x["what"], x)
    return sorted(seen.values(), key=lambda x: x["in_days"])

def summary():
    now_h, now_a, d = both_now()
    nw = next_window()
    callable_now = bool(good_windows()) and is_awake(now_h, d["hendrix_wake"], d["hendrix_sleep"]) \
                   and is_awake(now_a, d["aisha_wake"], d["aisha_sleep"])
    c = conn()
    reunion = c.execute("SELECT COUNT(*) t, SUM(status='done') d FROM reunion").fetchone()
    open_notes = [dict(r) for r in c.execute("SELECT topic,note,date FROM mentions WHERE followed_up=0 ORDER BY date DESC LIMIT 5")]
    gestures = [dict(r) for r in c.execute("SELECT date,type,description,status FROM gestures ORDER BY id DESC LIMIT 5")]
    miles = [dict(r) for r in c.execute("SELECT date,title,note FROM milestones ORDER BY date DESC LIMIT 5")]
    c.close()
    return {
        "aisha_name": d["aisha_name"],
        "lagos_time": now_h.strftime("%a %d %b, %H:%M"),
        "nc_time": now_a.strftime("%a %d %b, %H:%M"),
        "callable_now": callable_now,
        "next_window": nw, "today_windows": good_windows(),
        "dates": upcoming_dates(),
        "reunion": {"total": reunion["t"] or 0, "done": reunion["d"] or 0},
        "open_notes": open_notes, "gestures": gestures, "milestones": miles,
        "configured": bool(upcoming_dates()),
    }

# ---------- writes ----------
def setup(js):
    data = json.loads(js)
    c = conn()
    for k, v in data.items():
        c.execute("INSERT OR REPLACE INTO config(key,value) VALUES(?,?)", (k, str(v)))
    c.commit(); c.close()
    return {"ok": True, "saved": list(data.keys())}

def add(table, **kw):
    c = conn()
    cols = ",".join(kw); ph = ",".join("?"*len(kw))
    c.execute(f"INSERT INTO {table}({cols}) VALUES({ph})", tuple(kw.values()))
    c.commit(); c.close(); return {"ok": True}

# ---------- CLI ----------
def main():
    a = sys.argv[1:] or ["summary"]
    cmd = a[0]
    if cmd == "setup":
        js = a[1] if len(a) > 1 else sys.stdin.read()
        print(json.dumps(setup(js))); return
    if cmd == "summary":
        print(json.dumps(summary(), indent=2)); return
    if cmd == "now":
        h, n, d = both_now()
        print(f"🇳🇬 Lagos: {h:%a %H:%M}   🇺🇸 {d['aisha_name']} (NC): {n:%a %H:%M}")
        s = summary()
        print("📞 Good time to call now." if s["callable_now"] else "😴 Not ideal right now.")
        if s["next_window"]:
            print(f"   Next good window: {s['next_window']['lagos']} your time "
                  f"({s['next_window']['nc']} hers).")
        return
    if cmd == "windows":
        for w in good_windows():
            star = "⭐" if w["prime"] else "  "
            print(f"{star} {w['lagos']} (you) = {w['nc']} (her)")
        return
    if cmd == "dates":
        for x in upcoming_dates():
            print(f"  {x['what']}: {x['date']} (in {x['in_days']} days)")
        return
    if cmd == "goodnight":
        _, n, d = both_now(); bh, bm = _hm(d["daughter_bedtime_nc"])
        mins = (bh*60+bm) - (n.hour*60+n.minute)
        if -30 <= mins <= 60:
            print(f"🌙 It's {n:%H:%M} in NC — near {d.get('daughter_name') or 'her'} bedtime "
                  f"({d['daughter_bedtime_nc']}). Send a goodnight / story.")
        else:
            print(f"NC time {n:%H:%M}; bedtime {d['daughter_bedtime_nc']}.")
        return
    if cmd == "note":
        print(json.dumps(add("mentions", date=date.today().isoformat(),
                             topic=(a[1] if len(a)>1 else ""), note=" ".join(a[2:])))); return
    if cmd == "notes":
        c = conn()
        for r in c.execute("SELECT id,date,topic,note FROM mentions WHERE followed_up=0 ORDER BY date DESC"):
            print(f"  [{r['id']}] {r['date']} {r['topic']}: {r['note']}")
        c.close(); return
    if cmd == "milestone":
        print(json.dumps(add("milestones", date=date.today().isoformat(),
                             title=" ".join(a[1:]), note=""))); return
    if cmd == "gesture":
        sub = a[1] if len(a) > 1 else "list"
        if sub == "list":
            c = conn()
            for r in c.execute("SELECT id,date,type,description,status FROM gestures ORDER BY id DESC LIMIT 20"):
                print(f"  [{r['id']}] {r['date']} {r['type']} — {r['description']} ({r['status']})")
            c.close()
        else:
            print(json.dumps(add("gestures", date=date.today().isoformat(),
                                 type=sub, description=" ".join(a[2:]), status="idea")))
        return
    if cmd == "reunion":
        sub = a[1] if len(a) > 1 else "list"
        c = conn()
        if sub == "add":
            c.execute("INSERT INTO reunion(step,category,status) VALUES(?,?, 'todo')",
                      (" ".join(a[2:]), "general")); c.commit()
            print(json.dumps({"ok": True}))
        elif sub == "done" and len(a) > 2:
            c.execute("UPDATE reunion SET status='done' WHERE id=?", (a[2],)); c.commit()
            print(json.dumps({"ok": True}))
        else:
            for r in c.execute("SELECT id,step,category,status,due FROM reunion ORDER BY status,id"):
                box = "✅" if r["status"]=="done" else "⬜"
                print(f"  {box} [{r['id']}] {r['step']}" + (f" (due {r['due']})" if r['due'] else ""))
        c.close(); return
    print("unknown command:", cmd)

if __name__ == "__main__":
    main()
