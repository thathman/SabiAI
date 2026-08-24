#!/usr/bin/env python3
"""pes.py — PES / eFootball rivalry tracker (Fun lane).

Logs Hendrix's matches vs his mates and tracks the head-to-head record + streaks.

  log <opponent> <w|d|l> [score] [note]   record a match
  record [opponent]                        overall, or head-to-head vs one mate
  streak [opponent]                        current run
"""
import sqlite3, sys, os
from datetime import date

DB = os.path.expanduser("~/.openclaw/workspace/data/pes.db")

def conn():
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row
    c.execute("""CREATE TABLE IF NOT EXISTS matches(
        id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT, opponent TEXT,
        result TEXT, score TEXT, note TEXT)""")
    return c

def log(opp, res, score="", note=""):
    res = res.lower()[0]
    res = {"w": "win", "l": "loss", "d": "draw"}.get(res)
    if not res:
        print("result must be w / d / l"); return
    c = conn()
    c.execute("INSERT INTO matches(date,opponent,result,score,note) VALUES(?,?,?,?,?)",
              (date.today().isoformat(), opp, res, score, note))
    c.commit(); c.close()
    print(f"Logged: {res} vs {opp}" + (f" ({score})" if score else ""))

def record(opp=None):
    c = conn()
    q = "SELECT result,COUNT(*) n FROM matches"
    args = ()
    if opp:
        q += " WHERE opponent=? COLLATE NOCASE"; args = (opp,)
    q += " GROUP BY result"
    tally = {r["result"]: r["n"] for r in c.execute(q, args)}
    c.close()
    w, d, l = tally.get("win", 0), tally.get("draw", 0), tally.get("loss", 0)
    tot = w + d + l
    who = f"vs {opp}" if opp else "overall"
    if not tot:
        print(f"No matches logged {who} yet."); return
    wr = round(100 * w / tot)
    print(f"PES {who}: {w}W-{d}D-{l}L  ({wr}% win rate, {tot} played)")

def streak(opp=None):
    c = conn()
    q = "SELECT result FROM matches"
    args = ()
    if opp:
        q += " WHERE opponent=? COLLATE NOCASE"; args = (opp,)
    q += " ORDER BY id DESC"
    rows = [r["result"] for r in c.execute(q, args)]
    c.close()
    if not rows:
        print("No matches yet."); return
    cur = rows[0]; n = 0
    for r in rows:
        if r == cur: n += 1
        else: break
    print(f"Current run: {n} {cur}{'s' if n != 1 else ''} in a row")

def main():
    a = sys.argv[1:] or ["record"]
    cmd = a[0]
    if cmd == "log" and len(a) >= 3:
        log(a[1], a[2], a[3] if len(a) > 3 else "", " ".join(a[4:]))
    elif cmd == "record":
        record(a[1] if len(a) > 1 else None)
    elif cmd == "streak":
        streak(a[1] if len(a) > 1 else None)
    else:
        print(__doc__)

if __name__ == "__main__":
    main()
