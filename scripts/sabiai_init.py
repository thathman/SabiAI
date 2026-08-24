#!/usr/bin/env python3
"""sabiai_init.py — fresh-start SabiAI: clear records, add config/diary/accumulators tables.

Idempotent. Clears betting records (we start today) but keeps schema + structures.
Bankroll is initialised later by setup.py once the questionnaire is answered.
"""
import sqlite3, sys
from datetime import datetime, timezone

DB = "~.openclaw/workspace/data/bets.db"

def main(reset=True):
    c = sqlite3.connect(DB)
    c.executescript("""
    CREATE TABLE IF NOT EXISTS config(key TEXT PRIMARY KEY, value TEXT, updated_at TEXT);
    CREATE TABLE IF NOT EXISTS diary(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      date TEXT UNIQUE, title TEXT, body TEXT, mood TEXT,
      stats_json TEXT, created_at TEXT DEFAULT (datetime('now')));
    CREATE TABLE IF NOT EXISTS accumulators(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      slip_code TEXT, created_at TEXT, bookmaker TEXT,
      legs INTEGER, combined_odds REAL, stake REAL,
      status TEXT DEFAULT 'pending',      -- pending | won | lost | void
      payout REAL, settled_at TEXT, notes TEXT);
    CREATE TABLE IF NOT EXISTS accumulator_legs(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      acc_id INTEGER, sport TEXT, match TEXT, market TEXT, pick TEXT,
      odds REAL, confidence_pct REAL, outcome TEXT,
      FOREIGN KEY(acc_id) REFERENCES accumulators(id));
    """)
    if reset:
        for t in ["bets", "predictions", "bankroll", "calibration",
                  "accumulators", "accumulator_legs"]:
            try: c.execute(f"DELETE FROM {t}")
            except sqlite3.OperationalError: pass
        # reset autoincrement counters
        c.execute("DELETE FROM sqlite_sequence WHERE name IN "
                  "('bets','predictions','calibration','bankroll','accumulators','accumulator_legs')")
        c.execute("INSERT OR REPLACE INTO config(key,value,updated_at) VALUES('started_on',?,?)",
                  (datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                   datetime.now(timezone.utc).isoformat()))
        c.execute("INSERT OR REPLACE INTO config(key,value,updated_at) VALUES('brand','SabiAI',?)",
                  (datetime.now(timezone.utc).isoformat(),))
        c.execute("INSERT OR REPLACE INTO config(key,value,updated_at) VALUES('onboarded','no',?)",
                  (datetime.now(timezone.utc).isoformat(),))
    c.commit()
    counts = {t: c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
              for t in ["bets","predictions","bankroll","accumulators","diary","config"]}
    c.close()
    print("SabiAI initialised. Row counts:", counts)

if __name__ == "__main__":
    main(reset="--no-reset" not in sys.argv)
