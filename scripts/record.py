#!/usr/bin/env python3
"""record.py — one-line performance record for the daily WhatsApp message."""
import sqlite3

db = sqlite3.connect("~.openclaw/workspace/data/bets.db")
wins   = db.execute("SELECT COUNT(*) FROM bets WHERE outcome='win'  AND selected=1").fetchone()[0]
losses = db.execute("SELECT COUNT(*) FROM bets WHERE outcome='loss' AND selected=1").fetchone()[0]
pending = db.execute("SELECT COUNT(*) FROM bets WHERE outcome IS NULL AND selected=1").fetchone()[0]
start = float((db.execute("SELECT value FROM config WHERE key='bankroll_start'").fetchone() or [0])[0] or 0)
pl = db.execute("SELECT COALESCE(SUM(delta),0) FROM bankroll WHERE delta IS NOT NULL").fetchone()[0]
db.close()

settled = wins + losses
parts = []
if settled:
    parts.append(f"Record: {wins}W/{losses}L ({wins/settled*100:.0f}%) · {pending} pending")
else:
    parts.append(f"Record: {pending} pending (season start)")
if start:
    parts.append(f"Bankroll ₦{start+pl:,.0f} ({pl/start*100:+.1f}%)")
print("📈 " + " · ".join(parts))
