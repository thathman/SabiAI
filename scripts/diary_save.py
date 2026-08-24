#!/usr/bin/env python3
"""diary_save.py — save SabiAI's daily diary entry into bets.db (diary table).

openclaw composes the reflective entry (plain language) and pipes JSON here:
  echo '{"date":"2026-06-05","title":"First day on the books",
         "body":"We start today...","mood":"focused"}' | python3 diary_save.py
One entry per date (upsert). The Diary page on the dashboard renders these.
"""
import json, sqlite3, sys
from datetime import datetime, timezone

DB = "~.openclaw/workspace/data/bets.db"

def day_stats():
    """Snapshot of the day to attach to the entry."""
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row
    today = datetime.now().strftime("%Y-%m-%d")
    settled = c.execute("SELECT outcome,odds FROM bets WHERE substr(settled_at,1,10)=?", (today,)).fetchall()
    won = sum(1 for r in settled if r["outcome"] == "win")
    lost = sum(1 for r in settled if r["outcome"] == "loss")
    bank = c.execute("SELECT balance FROM bankroll ORDER BY id DESC LIMIT 1").fetchone()
    c.close()
    return {"date": today, "won": won, "lost": lost,
            "bankroll": bank["balance"] if bank else None}

def main():
    try:
        e = json.loads(sys.stdin.read())
    except Exception as ex:
        print(json.dumps({"ok": False, "error": f"bad JSON: {ex}"})); return
    date = e.get("date") or datetime.now().strftime("%Y-%m-%d")
    c = sqlite3.connect(DB)
    c.execute("""INSERT INTO diary(date,title,body,mood,stats_json,created_at)
        VALUES(?,?,?,?,?,?)
        ON CONFLICT(date) DO UPDATE SET
          title=excluded.title, body=excluded.body, mood=excluded.mood,
          stats_json=excluded.stats_json""",
        (date, e.get("title","Daily note"), e.get("body",""), e.get("mood",""),
         json.dumps(e.get("stats") or day_stats()),
         datetime.now(timezone.utc).isoformat()))
    c.commit(); c.close()
    print(json.dumps({"ok": True, "date": date}))

if __name__ == "__main__":
    main()
