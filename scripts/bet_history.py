#!/usr/bin/env python3
"""
bet_history.py — Personal bet history tracker

Every pick from value_bet_finder.py is stored as a row.
Settle results, view stats, track ROI over time.

Usage:
  python3 bet_history.py --pending                        # unsettled bets
  python3 bet_history.py --list [--weeks 4]               # recent bets
  python3 bet_history.py --settle <bet_id> W|L|V          # W=win L=loss V=void
  python3 bet_history.py --settle-week <2026-W22> W|L     # settle whole week
  python3 bet_history.py --stats                          # full stats
  python3 bet_history.py --stats --sport soccer           # filter by sport
"""

import sqlite3, os, sys, argparse, hashlib
from datetime import datetime, timezone

DB_PATH = "~.openclaw/workspace/data/bets.db"


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS bets (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            bet_id      TEXT UNIQUE,
            scan_date   TEXT NOT NULL,
            week        TEXT NOT NULL,
            sport       TEXT,
            match       TEXT,
            kickoff     TEXT,
            market      TEXT,
            pick        TEXT,
            odds        REAL,
            bookmaker   TEXT,
            ev          REAL,
            our_prob    REAL,
            kelly       REAL,
            model       TEXT,
            outcome     TEXT,       -- NULL | win | loss | void
            settled_at  TEXT,
            notes       TEXT,
            created_at  TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_week    ON bets(week)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sport   ON bets(sport)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_outcome ON bets(outcome)")
    conn.commit()
    return conn


def make_bet_id(scan_date, match, market, pick, bookmaker):
    raw = f"{scan_date}|{match}|{market}|{pick}|{bookmaker}"
    return hashlib.sha1(raw.encode()).hexdigest()[:12]


def insert_picks(picks: list, week: str, scan_date: str):
    """Called by value_bet_finder.py after each scan."""
    conn = get_db()
    inserted = 0
    for p in picks:
        bid = make_bet_id(scan_date, p.get("match",""), p.get("market",""),
                          p.get("pick",""), p.get("bookmaker",""))
        try:
            conn.execute("""
                INSERT OR IGNORE INTO bets
                  (bet_id, scan_date, week, sport, match, kickoff, market, pick,
                   odds, bookmaker, ev, our_prob, kelly, model)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                bid, scan_date, week,
                p.get("sport",""), p.get("match",""), p.get("kickoff",""),
                p.get("market",""), p.get("pick",""),
                p.get("odds"), p.get("bookmaker",""),
                p.get("ev"), p.get("our_prob"), p.get("kelly"),
                p.get("model",""),
            ))
            inserted += conn.execute("SELECT changes()").fetchone()[0]
        except Exception as e:
            print(f"  [warn] Could not insert bet: {e}")
    conn.commit()
    conn.close()
    return inserted


def settle_bet(bet_id: str, outcome: str):
    """Settle a single bet by short ID. outcome: win | loss | void"""
    outcome = outcome.lower()
    if outcome in ("w", "won"):   outcome = "win"
    if outcome in ("l", "lost"):  outcome = "loss"
    if outcome in ("v", "void"):  outcome = "void"
    if outcome not in ("win", "loss", "void"):
        print(f"Invalid outcome: {outcome}. Use W, L, or V.")
        return
    conn = get_db()
    conn.execute("""
        UPDATE bets SET outcome=?, settled_at=datetime('now')
        WHERE bet_id LIKE ? AND outcome IS NULL
    """, (outcome, f"{bet_id}%"))
    changed = conn.execute("SELECT changes()").fetchone()[0]
    conn.commit()
    conn.close()
    if changed:
        print(f"Settled {changed} bet(s) as {outcome}.")
    else:
        print(f"No unsettled bet found with ID starting '{bet_id}'.")


def settle_week(week_str: str, outcome: str):
    """Settle all unsettled bets for a week."""
    outcome = outcome.lower()
    if outcome in ("w", "won"):   outcome = "win"
    if outcome in ("l", "lost"):  outcome = "loss"
    if outcome not in ("win", "loss"):
        print(f"Invalid outcome: {outcome}. Use W or L.")
        return
    conn = get_db()
    conn.execute("""
        UPDATE bets SET outcome=?, settled_at=datetime('now')
        WHERE week=? AND outcome IS NULL
    """, (outcome, week_str))
    changed = conn.execute("SELECT changes()").fetchone()[0]
    conn.commit()
    conn.close()
    print(f"Week {week_str}: {changed} bets marked as {outcome}.")


def show_pending():
    conn = get_db()
    rows = conn.execute("""
        SELECT bet_id, week, sport, match, market, pick, odds, ev, bookmaker
        FROM bets WHERE outcome IS NULL
        ORDER BY scan_date DESC, sport, match
    """).fetchall()
    conn.close()
    if not rows:
        print("No unsettled bets.")
        return
    print(f"\n{'─'*80}")
    print(f"  PENDING BETS ({len(rows)} unsettled)")
    print(f"{'─'*80}")
    cur_week = None
    for r in rows:
        if r["week"] != cur_week:
            cur_week = r["week"]
            print(f"\n  Week {cur_week}")
        ev_str = f"+{r['ev']*100:.1f}%" if r["ev"] else "?"
        print(f"  [{r['bet_id']}]  {r['sport']:<14} {r['match']:<30}  "
              f"{r['market']:<14} {r['pick']:<12}  @ {r['odds']:.2f}  EV {ev_str}  {r['bookmaker']}")
    print(f"\n  To settle: python3 bet_history.py --settle <bet_id> W|L|V")
    print(f"  To settle week: python3 bet_history.py --settle-week <2026-W22> W|L\n")


def show_list(weeks: int = 4):
    conn = get_db()
    rows = conn.execute("""
        SELECT bet_id, week, sport, match, market, pick, odds, ev, outcome
        FROM bets
        WHERE scan_date >= date('now', ?)
        ORDER BY scan_date DESC, sport, match
    """, (f"-{weeks*7} days",)).fetchall()
    conn.close()
    if not rows:
        print(f"No bets in the last {weeks} weeks.")
        return
    icon = {"win": "✅", "loss": "❌", "void": "⬜", None: "⏳"}
    print(f"\n{'─'*80}")
    print(f"  BET HISTORY — last {weeks} weeks ({len(rows)} bets)")
    print(f"{'─'*80}")
    cur_week = None
    for r in rows:
        if r["week"] != cur_week:
            cur_week = r["week"]
            week_rows = [x for x in rows if x["week"] == cur_week]
            settled = [x for x in week_rows if x["outcome"]]
            wins = sum(1 for x in settled if x["outcome"] == "win")
            print(f"\n  Week {cur_week}  ({wins}/{len(settled)} settled wins)")
        ev_str = f"+{r['ev']*100:.1f}%" if r["ev"] else "?"
        status = icon.get(r["outcome"], "?")
        print(f"  {status}  [{r['bet_id']}]  {r['sport']:<12} {r['match']:<28} "
              f"{r['market']:<12} {r['pick']:<10} @ {r['odds']:.2f}  EV {ev_str}")
    print()


def show_stats(sport_filter: str = None):
    conn = get_db()
    where = "WHERE outcome IS NOT NULL"
    params = []
    if sport_filter:
        where += " AND sport LIKE ?"
        params.append(f"%{sport_filter}%")

    total_q = conn.execute(f"SELECT COUNT(*) FROM bets {where}", params).fetchone()[0]
    wins_q  = conn.execute(f"SELECT COUNT(*) FROM bets {where} AND outcome='win'", params).fetchone()[0]
    total_all = conn.execute("SELECT COUNT(*) FROM bets").fetchone()[0]
    pending   = conn.execute("SELECT COUNT(*) FROM bets WHERE outcome IS NULL").fetchone()[0]

    print(f"\n{'═'*60}")
    print(f"  VALUE BET TRACKER — ALL-TIME RECORD")
    print(f"{'═'*60}")
    print(f"  Total bets logged : {total_all}")
    print(f"  Settled           : {total_q}")
    print(f"  Pending           : {pending}")
    if total_q:
        pct = wins_q / total_q * 100
        losses = total_q - wins_q - conn.execute(
            f"SELECT COUNT(*) FROM bets {where} AND outcome='void'", params
        ).fetchone()[0]
        print(f"  Win / Loss        : {wins_q} / {losses}  ({pct:.0f}% win rate)")

        # Average odds on winning bets
        avg_win_odds = conn.execute(
            f"SELECT AVG(odds) FROM bets {where} AND outcome='win'", params
        ).fetchone()[0]
        avg_ev = conn.execute(
            f"SELECT AVG(ev) FROM bets {where}", params
        ).fetchone()[0]
        if avg_win_odds:
            print(f"  Avg win odds      : {avg_win_odds:.2f}")
        if avg_ev:
            print(f"  Avg EV at scan    : +{avg_ev*100:.1f}%")

    # By sport
    print(f"\n  {'SPORT':<20} {'SETTLED':>7} {'WINS':>5} {'WIN%':>6}")
    print(f"  {'─'*42}")
    by_sport = conn.execute(f"""
        SELECT sport,
               COUNT(*) as n,
               SUM(CASE WHEN outcome='win' THEN 1 ELSE 0 END) as w
        FROM bets {where}
        GROUP BY sport ORDER BY n DESC
    """, params).fetchall()
    for r in by_sport:
        pct = r["w"] / r["n"] * 100 if r["n"] else 0
        bar = "█" * int(pct / 10)
        print(f"  {r['sport']:<20} {r['n']:>7} {r['w']:>5}  {pct:>5.0f}%  {bar}")

    # By market
    print(f"\n  {'MARKET':<20} {'SETTLED':>7} {'WINS':>5} {'WIN%':>6}")
    print(f"  {'─'*42}")
    by_market = conn.execute(f"""
        SELECT market,
               COUNT(*) as n,
               SUM(CASE WHEN outcome='win' THEN 1 ELSE 0 END) as w
        FROM bets {where}
        GROUP BY market ORDER BY n DESC LIMIT 15
    """, params).fetchall()
    for r in by_market:
        pct = r["w"] / r["n"] * 100 if r["n"] else 0
        bar = "█" * int(pct / 10)
        print(f"  {r['market']:<20} {r['n']:>7} {r['w']:>5}  {pct:>5.0f}%  {bar}")

    # By bookmaker (top 8)
    print(f"\n  {'BOOKMAKER':<20} {'SETTLED':>7} {'WINS':>5} {'WIN%':>6}")
    print(f"  {'─'*42}")
    by_book = conn.execute(f"""
        SELECT bookmaker,
               COUNT(*) as n,
               SUM(CASE WHEN outcome='win' THEN 1 ELSE 0 END) as w
        FROM bets {where}
        GROUP BY bookmaker ORDER BY n DESC LIMIT 8
    """, params).fetchall()
    for r in by_book:
        pct = r["w"] / r["n"] * 100 if r["n"] else 0
        bar = "█" * int(pct / 10)
        print(f"  {r['bookmaker']:<20} {r['n']:>7} {r['w']:>5}  {pct:>5.0f}%  {bar}")

    # Best EV bets that actually won
    if total_q >= 3:
        print(f"\n  TOP 5 EV WINNERS")
        top = conn.execute(f"""
            SELECT match, market, pick, odds, ev FROM bets
            {where} AND outcome='win'
            ORDER BY ev DESC LIMIT 5
        """, params).fetchall()
        for r in top:
            ev_str = f"+{r['ev']*100:.1f}%" if r["ev"] else "?"
            print(f"  ✅ {r['match'][:28]:<28}  {r['market']:<12} {r['pick']:<10} "
                  f"@ {r['odds']:.2f}  EV {ev_str}")

    conn.close()
    print()


def migrate_from_json():
    """One-time import of existing value_bet_results.json into SQLite."""
    import json
    json_path = "~.openclaw/workspace/data/value_bet_results.json"
    try:
        with open(json_path) as f:
            data = json.load(f)
    except Exception:
        print("No JSON history to migrate.")
        return

    total = 0
    for entry in data:
        week = entry.get("week", "")
        scan_date = entry.get("scan_date", "")
        outcome = entry.get("actual_outcome")
        picks = entry.get("picks", [])
        inserted = insert_picks(picks, week, scan_date)
        if outcome:
            settle_week(week, outcome)
        total += inserted
    print(f"Migrated {total} bets from JSON history.")


def main():
    parser = argparse.ArgumentParser(description="Bet history tracker")
    parser.add_argument("--pending",      action="store_true", help="Show unsettled bets")
    parser.add_argument("--list",         action="store_true", help="Recent bet history")
    parser.add_argument("--weeks",        type=int, default=4,  help="How many weeks to show (default 4)")
    parser.add_argument("--settle",       nargs=2, metavar=("BET_ID", "OUTCOME"), help="Settle a bet: --settle abc123 W")
    parser.add_argument("--settle-week",  nargs=2, metavar=("WEEK", "OUTCOME"),   help="Settle a week: --settle-week 2026-W22 W")
    parser.add_argument("--stats",        action="store_true", help="Show win/loss stats")
    parser.add_argument("--sport",        default=None, help="Filter stats by sport")
    parser.add_argument("--migrate",      action="store_true", help="Import existing JSON history into SQLite")
    args = parser.parse_args()

    if args.migrate:
        migrate_from_json()
        return

    if args.pending:
        show_pending()
        return

    if args.list:
        show_list(args.weeks)
        return

    if args.settle:
        settle_bet(args.settle[0], args.settle[1])
        return

    if args.settle_week:
        settle_week(args.settle_week[0], args.settle_week[1])
        return

    if args.stats:
        show_stats(args.sport)
        return

    # Default: show pending + quick stats summary
    show_pending()
    conn = get_db()
    total = conn.execute("SELECT COUNT(*) FROM bets").fetchone()[0]
    conn.close()
    if total:
        print(f"  ({total} total bets stored — run --stats for full breakdown)\n")


if __name__ == "__main__":
    main()
