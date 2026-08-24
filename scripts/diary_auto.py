#!/usr/bin/env python3
"""diary_auto.py — fallback diary writer so /diary never goes stale.

The primary diary path is OpenClaw composing a reflective entry and piping it
to diary_save.py. When that agent is down (e.g. model usage limits), nothing
gets written. This script composes a plain factual entry straight from bets.db
and upserts it ONLY if no entry exists for that date — an agent-written entry
always wins.

Usage:
    python3 diary_auto.py              # today
    python3 diary_auto.py 2026-06-08   # backfill a specific date
"""
import json, sqlite3, sys
from datetime import datetime, timezone

DB = "~.openclaw/workspace/data/bets.db"


def _fmt_ngn(v):
    return f"₦{v:,.0f}" if v is not None else "?"


def compose(date: str) -> dict:
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row

    settled = c.execute(
        """SELECT match, pick, odds, outcome, bet_type, bookmaker FROM bets
           WHERE substr(settled_at,1,10)=? AND outcome IN ('win','loss')
           ORDER BY settled_at""", (date,)).fetchall()
    won = [r for r in settled if r["outcome"] == "win"]
    lost = [r for r in settled if r["outcome"] == "loss"]

    scanned = c.execute(
        "SELECT COUNT(*) FROM bets WHERE scan_date=?", (date,)).fetchone()[0]
    pending = c.execute(
        """SELECT COUNT(*) FROM bets
           WHERE scan_date=? AND outcome IS NULL AND bet_type='kelly'""",
        (date,)).fetchone()[0]

    ledger = c.execute(
        """SELECT kind, delta, note FROM bankroll
           WHERE substr(ts,1,10)=? ORDER BY id""", (date,)).fetchall()
    day_pl = sum(r["delta"] or 0 for r in ledger)
    bank = c.execute(
        "SELECT balance FROM bankroll ORDER BY id DESC LIMIT 1").fetchone()

    chain = c.execute(
        """SELECT streak_status, restrategy_until, streak_day
           FROM continuous_bet_state WHERE id=1""").fetchone()
    c.close()

    lines = []
    if scanned:
        lines.append(f"Scanned and logged {scanned} pick(s) today; {pending} Kelly pick(s) still open.")
    if won or lost:
        lines.append(f"Settled {len(won) + len(lost)} bet(s): {len(won)} won, {len(lost)} lost.")
        for r in (won + lost)[:6]:
            lines.append(f"  - {r['pick']} ({r['match']}) @ {r['odds']} — {r['outcome'].upper()} [{r['bookmaker'] or '?'}]")
    for r in ledger:
        lines.append(f"Money moved: {r['note']} ({'+' if (r['delta'] or 0) >= 0 else ''}{_fmt_ngn(r['delta'])})")
    if chain and chain["streak_status"] == "restrategy":
        lines.append(f"Chain is on restrategy break until {chain['restrategy_until']}; Kelly picks keep running.")
    if not lines:
        lines.append("Quiet day — no settlements, no money moved. Pipeline ran normally.")
    if bank:
        lines.append(f"Bankroll stands at {_fmt_ngn(bank['balance'])}.")

    if day_pl > 0:
        mood, title = "upbeat", f"{len(won)}W {len(lost)}L — a green day ({_fmt_ngn(day_pl)})"
    elif day_pl < 0:
        mood, title = "measured", f"{len(won)}W {len(lost)}L — gave some back ({_fmt_ngn(day_pl)})"
    elif won or lost:
        mood, title = "steady", f"{len(won)}W {len(lost)}L — flat day"
    else:
        mood, title = "patient", "Quiet day on the books"

    return {
        "date": date, "title": title, "mood": mood,
        "body": "\n".join(lines) + "\n\n(auto-generated from day data)",
        "stats": {"date": date, "won": len(won), "lost": len(lost),
                  "day_pl": round(day_pl, 2),
                  "bankroll": bank["balance"] if bank else None},
    }


def main():
    date = sys.argv[1] if len(sys.argv) > 1 else datetime.now().strftime("%Y-%m-%d")
    c = sqlite3.connect(DB)
    exists = c.execute("SELECT 1 FROM diary WHERE date=?", (date,)).fetchone()
    if exists:
        c.close()
        print(json.dumps({"ok": True, "date": date, "skipped": "entry exists"}))
        return
    e = compose(date)
    c.execute("""INSERT INTO diary(date,title,body,mood,stats_json,created_at)
                 VALUES(?,?,?,?,?,?)""",
              (e["date"], e["title"], e["body"], e["mood"],
               json.dumps(e["stats"]), datetime.now(timezone.utc).isoformat()))
    c.commit(); c.close()
    print(json.dumps({"ok": True, "date": date, "title": e["title"]}))


if __name__ == "__main__":
    main()
