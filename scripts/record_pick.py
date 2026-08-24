#!/usr/bin/env python3
"""
record_pick.py — clawson's pick logging tool for SabiAI.

Usage:
  python3 record_pick.py log      --match "Belgium vs Tunisia" --pick "Belgium" --odds 1.35 --type compound [--market "1X2"] [--sport "Football"] [--conf 73] [--note "..."]
  python3 record_pick.py settle   --match "Belgium vs Tunisia" --result win
  python3 record_pick.py settle   --id 42 --result loss
  python3 record_pick.py pending  (list all pending picks)
  python3 record_pick.py today    (list today's picks)
  python3 record_pick.py remove   --id 42 (delete a wrongly logged pick)
"""
import argparse, sqlite3, sys, json
from datetime import datetime, timezone, date as _date

DB = "~.openclaw/workspace/data/bets.db"

def _db():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c

def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def _today():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _canon_bookmaker(value: str) -> str:
    raw = (value or "").strip().lower()
    if "sport" in raw:
        return "SportyBet"
    if "1x" in raw:
        return "1xBet"
    if "9ja" in raw or "bet9" in raw:
        return "Bet9ja"
    return value.strip() if value else ""


def _default_bookmaker(btype: str) -> str:
    # Routing rule: Bet9ja = long shots, SportyBet = chain, 1xBet = kelly/live
    if btype == "longshot":
        return "Bet9ja"
    if btype == "compound":
        return "SportyBet"
    if btype in ("kelly", "live"):
        return "1xBet"
    return "SportyBet"


def _write_ledger(c, bet_id: str, stake: float, delta: float, kind: str, note: str):
    """Append a settled money event to the bankroll ledger (idempotent per bet_id)."""
    prev = c.execute(
        "SELECT balance FROM bankroll WHERE balance IS NOT NULL ORDER BY id DESC LIMIT 1"
    ).fetchone()
    balance = round((float(prev["balance"]) if prev else 0.0) + delta, 2)
    c.execute("DELETE FROM bankroll WHERE bet_id=?", (bet_id,))
    c.execute(
        "INSERT INTO bankroll (ts, bet_id, stake, delta, balance, kind, note) VALUES (?,?,?,?,?,?,?)",
        (_now(), bet_id, round(stake, 2), round(delta, 2), balance, kind, note),
    )

def cmd_log(args):
    match   = args.match.strip()
    pick    = args.pick.strip()
    odds    = float(args.odds)
    btype   = (args.type or "kelly").lower().strip()
    market  = (args.market or "1X2").strip()
    sport   = (args.sport or "Football").strip()
    bookmaker = _canon_bookmaker(args.bookmaker) if getattr(args, "bookmaker", None) else ""
    if not bookmaker:
        bookmaker = _default_bookmaker(btype)
    conf    = int(args.conf) if args.conf else None
    note    = args.note or ""

    if odds < 1.01:
        print(f"ERROR: odds {odds} look wrong — decimal odds must be ≥ 1.01 (e.g. 1.35, not 35)")
        sys.exit(1)

    _iso = _date.today().isocalendar()
    week_str = f"{_iso[0]}-W{_iso[1]:02d}"
    bet_id = f"manual_{_today()}_{match[:20].replace(' ','_')}_{pick[:10].replace(' ','_')}"

    c = _db()
    # Avoid duplicates
    existing = c.execute("SELECT id FROM bets WHERE bet_id=?", (bet_id,)).fetchone()
    if existing:
        print(f"⚠️  Pick already logged (id {existing['id']}). Use settle to update result.")
        c.close()
        return

    c.execute("""
        INSERT INTO bets
          (bet_id, scan_date, week, sport, match, market, pick, odds, bookmaker,
           confidence_pct, bet_type, notes, created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        bet_id, _today(), week_str, sport, match, market, pick, odds,
        bookmaker,
        conf, btype, note, _now()
    ))
    c.commit()
    row_id = c.execute("SELECT id FROM bets WHERE bet_id=?", (bet_id,)).fetchone()["id"]
    c.close()

    type_label = {"compound": "🎯 Compound chain", "kelly": "📊 Kelly pick",
                  "longshot": "🎰 Long shot leg", "live": "⚡ Live alert"}.get(btype, btype)
    conf_str = f" · {conf}% confidence" if conf else ""
    print(f"✅ Logged (id={row_id})")
    print(f"   {type_label}: {match} — {pick} @ {odds:.2f}{conf_str}")
    print(f"   Market: {market} · Sport: {sport} · Bookmaker: {bookmaker}")
    if note:
        print(f"   Note: {note}")

    # If compound, also update continuous_bet_state.
    # RULE: day counter only moves on SETTLE, not on log.
    #   - Log:   streak_day stays at current position (e.g. 2 means we are on day 2)
    #   - Settle WIN:  streak_day += 1, current_stake *= odds
    #   - Settle LOSS: streak_day = 1 (reset), current_stake = starting_stake
    if btype == "compound":
        c2 = _db()
        state = c2.execute("SELECT * FROM continuous_bet_state WHERE id=1").fetchone()
        if state:
            c2.execute("""UPDATE continuous_bet_state SET
                last_pick_id=?, last_pick_date=?,
                last_outcome='pending', streak_status='active', updated_at=?
                WHERE id=1""", (row_id, _now(), _now()))
            c2.commit()
            current_day = state["streak_day"] or 1
            print(f"   Chain logged on Day {current_day}/30 (stays day {current_day} until settled)")
        c2.close()

def cmd_settle(args):
    result = args.result.lower().strip()
    if result not in ("win", "loss", "w", "l"):
        print("ERROR: result must be 'win' or 'loss'")
        sys.exit(1)
    outcome = "win" if result in ("win", "w") else "loss"

    c = _db()
    if args.id:
        row = c.execute("SELECT * FROM bets WHERE id=?", (args.id,)).fetchone()
    else:
        # Match by match name (case-insensitive, partial)
        pattern = f"%{args.match.strip()}%"
        row = c.execute("""SELECT * FROM bets WHERE match LIKE ? AND outcome IS NULL
            ORDER BY id DESC LIMIT 1""", (pattern,)).fetchone()

    if not row:
        print(f"ERROR: no pending pick found{' for id '+str(args.id) if args.id else ' matching: '+args.match}")
        c.close()
        sys.exit(1)

    c.execute("""UPDATE bets SET outcome=?, settled_at=? WHERE id=?""",
              (outcome, _now(), row["id"]))

    # Update bankroll if we have starting balance
    if outcome == "win":
        payout = float(row["odds"] or 1.0) * (float(row["kelly"] or 0) or 100)
    else:
        payout = 0

    # Update compound chain state
    # RULE: settle is where the day counter actually moves.
    #   - WIN:  streak_day += 1, current_stake = current_stake * odds, total_compounded += profit
    #   - LOSS: streak_day = 1 (reset), current_stake = starting_stake, streak_status='restrategy'
    if (row["bet_type"] or "").lower() == "compound" or "compound" in (row["notes"] or "").lower():
        state = c.execute("SELECT * FROM continuous_bet_state WHERE id=1").fetchone()
        if state:
            slip = row["slip_code"] or f"id{row['id']}"
            old_stake = float(state["current_stake"] or state["starting_stake"] or 1000)
            if outcome == "win":
                new_stake = old_stake * float(row["odds"] or 1.35)
                profit = new_stake - old_stake
                new_day = (state["streak_day"] or 1) + 1
                c.execute("""UPDATE continuous_bet_state SET
                    last_outcome='win', streak_status='active',
                    streak_day=?, current_stake=?,
                    total_compounded=COALESCE(total_compounded,0)+?, updated_at=?
                    WHERE id=1""", (new_day, round(new_stake, 2), round(profit, 2), _now()))
                _write_ledger(c, f"chain:{slip}", old_stake, profit, "chain_win",
                              f"Chain Day {state['streak_day'] or 1} WIN. {row['match']} @ {row['odds']}. "
                              f"Stake ₦{old_stake:,.0f} → ₦{new_stake:,.2f}.")
                print(f"✅ Settled WIN — Day {(state['streak_day'] or 1)}/30 done, advanced to Day {new_day}/30. Stake → ₦{round(new_stake):,}")
            else:
                # LOSS: reset to day 1, stake back to starting, 7-day restrategy break
                from datetime import timedelta
                starting = float(state["starting_stake"] or 1000)
                until = (datetime.now(timezone.utc) + timedelta(days=7)).strftime("%Y-%m-%d")
                c.execute("""UPDATE continuous_bet_state SET
                    last_outcome='loss', streak_status='restrategy',
                    streak_day=1, current_stake=?,
                    restrategy_started_at=?, restrategy_until=?, updated_at=? WHERE id=1""",
                    (starting, _now(), until, _now()))
                _write_ledger(c, f"chain:{slip}", old_stake, -old_stake, "chain_loss",
                              f"Chain LOSS. {row['match']}. Stake ₦{old_stake:,.0f} gone. "
                              f"Reset to Day 1; restrategy until {until}.")
                print(f"❌ Settled LOSS — chain reset to Day 1/30, stake back to ₦{round(starting):,}. Restrategy break until {until}.")
    else:
        print(f"{'✅' if outcome=='win' else '❌'} Settled {outcome.upper()}: {row['match']} — {row['pick']} @ {row['odds'] or '—'}")

    c.commit()
    c.close()

def cmd_pending(args):
    c = _db()
    rows = c.execute("""SELECT id, scan_date, sport, match, pick, odds, confidence_pct,
        bet_type FROM bets WHERE outcome IS NULL ORDER BY id DESC LIMIT 30""").fetchall()
    c.close()
    if not rows:
        print("No pending picks.")
        return
    print(f"{'ID':<5} {'Date':<12} {'Type':<10} {'Match':<30} {'Pick':<20} {'Odds':<7} {'Conf'}")
    print("─" * 95)
    for r in rows:
        conf = f"{r['confidence_pct']}%" if r['confidence_pct'] else "—"
        print(f"{r['id']:<5} {(r['scan_date'] or ''):<12} {(r['bet_type'] or 'kelly'):<10} "
              f"{(r['match'] or '')[:29]:<30} {(r['pick'] or '')[:19]:<20} "
              f"{float(r['odds'] or 0):<7.2f} {conf}")

def cmd_today(args):
    c = _db()
    rows = c.execute("""SELECT id, sport, match, market, pick, odds, confidence_pct,
        bet_type, outcome FROM bets WHERE scan_date=? ORDER BY id DESC""",
        (_today(),)).fetchall()
    c.close()
    if not rows:
        print(f"No picks logged for today ({_today()}).")
        return
    print(f"Today ({_today()}) — {len(rows)} picks:")
    print("─" * 90)
    for r in rows:
        status = r['outcome'] or 'pending'
        conf = f"{r['confidence_pct']}%" if r['confidence_pct'] else "—"
        print(f"  [{r['id']}] {(r['bet_type'] or 'kelly'):<10} {r['match']} — {r['pick']} "
              f"@ {float(r['odds'] or 0):.2f}  {conf}  [{status}]")

def cmd_remove(args):
    c = _db()
    row = c.execute("SELECT * FROM bets WHERE id=?", (args.id,)).fetchone()
    if not row:
        print(f"ERROR: no pick with id={args.id}")
        c.close(); sys.exit(1)
    if row["outcome"] is not None:
        print(f"⚠️  Pick already settled ({row['outcome']}) — cannot remove. Use settle to correct.")
        c.close(); sys.exit(1)
    c.execute("DELETE FROM bets WHERE id=?", (args.id,))
    c.commit()
    c.close()
    print(f"🗑  Removed pick id={args.id}: {row['match']} — {row['pick']}")

def cmd_not_placed(args):
    """Mark a model-only pick as not placed. Excluded from W/L counts."""
    c = _db()
    if args.id:
        row = c.execute("SELECT * FROM bets WHERE id=?", (args.id,)).fetchone()
    else:
        pattern = f"%{args.match.strip()}%"
        row = c.execute("""SELECT * FROM bets WHERE match LIKE ? AND outcome IS NULL
            ORDER BY id DESC LIMIT 1""", (pattern,)).fetchone()
    if not row:
        print(f"ERROR: no pending pick found")
        c.close(); sys.exit(1)
    note = (row["notes"] or "")
    if args.note:
        note = (note + " | " if note else "") + f"NOT PLACED: {args.note}"
    c.execute("""UPDATE bets SET outcome='not_placed', notes=?, settled_at=? WHERE id=?""",
              (note, _now(), row["id"]))
    c.commit()
    c.close()
    print(f"🚫 Marked id={row['id']} as not_placed: {row['match']} — {row['pick']}")

def cmd_select(args):
    """Mark a generated pick as actually placed (selected=1) or deselect it."""
    c = _db()
    deselect = getattr(args, 'deselect', False)
    if args.id:
        row = c.execute("SELECT * FROM bets WHERE id=?", (args.id,)).fetchone()
    else:
        pattern = f"%{args.match.strip()}%"
        row = c.execute("SELECT * FROM bets WHERE match LIKE ? ORDER BY id DESC LIMIT 1", (pattern,)).fetchone()
    if not row:
        print("ERROR: no pick found"); c.close(); sys.exit(1)
    c.execute("UPDATE bets SET selected=? WHERE id=?", (0 if deselect else 1, row["id"]))
    c.commit(); c.close()
    action = "Deselected" if deselect else "Selected (placed)"
    print(f"✓ {action} id={row['id']}: {row['match']} — {row['pick']}")

def main():
    p = argparse.ArgumentParser(description="clawson pick recorder for SabiAI")
    sub = p.add_subparsers(dest="cmd")
    lg = sub.add_parser("log", help="Log a new pick")
    lg.add_argument("--match",  required=True)
    lg.add_argument("--pick",   required=True)
    lg.add_argument("--odds",   required=True, type=float)
    lg.add_argument("--type",   default="kelly",
                    choices=["compound","kelly","longshot","live"])
    lg.add_argument("--market", default="1X2")
    lg.add_argument("--sport",  default="Football")
    lg.add_argument("--bookmaker", default="", help="Override bookmaker label (default depends on bet type)")
    lg.add_argument("--conf",   type=int, help="Confidence 0-100")
    lg.add_argument("--note",   default="")

    st = sub.add_parser("settle", help="Settle a pick win/loss")
    g = st.add_mutually_exclusive_group(required=True)
    g.add_argument("--id",    type=int, help="Pick DB id")
    g.add_argument("--match", help="Match name (partial)")
    st.add_argument("--result", required=True, choices=["win","loss","w","l","not_placed"])

    np = sub.add_parser("not-placed", help="Mark a model-only pick as not placed (excluded from W/L)")
    np.add_argument("--id", type=int, help="Pick DB id")
    np.add_argument("--match", help="Match name (partial)")
    np.add_argument("--note", default="", help="Why it wasn't placed")

    sub.add_parser("pending", help="List pending picks")
    sub.add_parser("today",   help="List today's picks")

    rm = sub.add_parser("remove", help="Remove a wrongly logged pick")
    rm.add_argument("--id", required=True, type=int)

    sl = sub.add_parser("select", help="Mark a pick as actually placed (counts towards performance)")
    g2 = sl.add_mutually_exclusive_group(required=True)
    g2.add_argument("--id", type=int)
    g2.add_argument("--match", help="Match name (partial)")

    dsl = sub.add_parser("deselect", help="Unmark a pick (remove from performance stats)")
    g3 = dsl.add_mutually_exclusive_group(required=True)
    g3.add_argument("--id", type=int)
    g3.add_argument("--match", help="Match name (partial)")

    args = p.parse_args()
    if not args.cmd:
        p.print_help(); sys.exit(0)

    if args.cmd == "deselect":
        args.deselect = True
        cmd_select(args)
    else:
        {"log": cmd_log, "settle": cmd_settle, "pending": cmd_pending,
         "today": cmd_today, "remove": cmd_remove, "not-placed": cmd_not_placed,
         "select": cmd_select}[args.cmd](args)

if __name__ == "__main__":
    main()
