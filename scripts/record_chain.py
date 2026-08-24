#!/usr/bin/env python3
"""
record_chain.py — clawson's chain-bet (accumulator) recorder for SabiAI.

Logs a screenshot-derived chain pick so the dashboard, the betchain history,
the bankroll ledger, and the continuous_bet_state all stay in sync. Writes
to four tables in a single transaction:

  1. accumulators         — the slip itself
  2. accumulator_legs     — one row per leg
  3. bets                 — single summary row (dashboard reads from here)
  4. continuous_bet_state — link state.last_pick_id to the bets row
  5. bankroll             — stake ledger row

Idempotent: rerunning with the same slip_code replaces the previous legs
and updates state without duplicating the bets row or bankroll row.

Usage:
  python3 record_chain.py \\
      --slip-code CHAIN-2026-06-07-002 \\
      --legs "Ecuador vs Guatemala:Ecuador:1.18,Colombia vs Jordan:Colombia:1.20" \\
      --stake 1340 \\
      --bookmaker SportyBet \\
      --conf 75 \\
      --note "Day 2 of 30-day chain. Screenshot forwarded 16:39 UTC."

  # Or from an LLM-extracted JSON file:
  python3 record_chain.py --from-json /tmp/screenshot_extract.json

  # Show today's chain:
  python3 record_chain.py today
"""
import argparse, json, os, sqlite3, sys
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


def _canon_bookmaker(b: str) -> str:
    b = (b or "").strip().lower()
    if b in ("sportybet", "sporty", "sb"):
        return "SportyBet"
    if b in ("1xbet", "1x", "1xb"):
        return "1xBet"
    if b in ("bet9ja", "9ja", "b9j"):
        return "Bet9ja"
    return b.title() if b else "SportyBet"


def _validate_legs(legs):
    """legs: list of dicts with match, pick, odds (and optional sport, market, conf)."""
    if not legs or len(legs) < 2:
        print(f"ERROR: chain needs at least 2 legs (got {len(legs) if legs else 0})")
        sys.exit(1)
    cleaned = []
    for i, L in enumerate(legs, 1):
        try:
            odds = float(L["odds"])
        except (KeyError, TypeError, ValueError):
            print(f"ERROR: leg {i} '{L.get('match','?')}' has invalid odds: {L.get('odds')}")
            sys.exit(1)
        if odds < 1.01:
            print(f"ERROR: leg {i} odds {odds} < 1.01 — must be decimal odds")
            sys.exit(1)
        cleaned.append({
            "match":   (L.get("match") or "").strip(),
            "pick":    (L.get("pick")  or "").strip(),
            "odds":    round(odds, 3),
            "sport":   (L.get("sport")   or "Intl Friendlies").strip(),
            "market":  (L.get("market")  or "1X2").strip(),
            "conf":    L.get("conf"),
        })
        if not cleaned[-1]["match"] or not cleaned[-1]["pick"]:
            print(f"ERROR: leg {i} missing match or pick: {L}")
            sys.exit(1)
    return cleaned


def _parse_legs_arg(s):
    """Parse 'match:pick:odds' or 'match:pick:odds:conf' comma-separated string."""
    out = []
    for chunk in s.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        parts = [p.strip() for p in chunk.split(":")]
        if len(parts) < 3:
            print(f"ERROR: leg '{chunk}' — expected format match:pick:odds[:conf]")
            sys.exit(1)
        leg = {"match": parts[0], "pick": parts[1], "odds": parts[2]}
        if len(parts) >= 4 and parts[3]:
            try:
                leg["conf"] = float(parts[3])
            except ValueError:
                pass
        if len(parts) >= 5 and parts[4]:
            leg["sport"] = parts[4]
        out.append(leg)
    return out


def cmd_log(args):
    slip_code = args.slip_code or f"CHAIN-{_today()}-{int(datetime.now(timezone.utc).timestamp())}"
    bookmaker = _canon_bookmaker(args.bookmaker or "SportyBet")

    if args.from_json:
        with open(args.from_json) as f:
            data = json.load(f)
        legs_in = data.get("legs") or []
        stake = float(data.get("stake") or 0)
        bookmaker = _canon_bookmaker(data.get("bookmaker") or "SportyBet")
        note = data.get("note") or args.note or ""
        conf = data.get("confidence_pct")
    else:
        legs_in = _parse_legs_arg(args.legs)
        stake = float(args.stake or 0)
        note = args.note or ""
        conf = args.conf

    legs = _validate_legs(legs_in)

    if stake <= 0:
        print(f"ERROR: stake must be > 0 (got {stake})")
        sys.exit(1)

    combined = 1.0
    for L in legs:
        combined *= L["odds"]
    combined = round(combined, 3)
    payout = round(stake * combined, 2)
    profit = round(payout - stake, 2)

    today = _today()
    now = _now()
    iso = _date.today().isocalendar()
    week_str = f"{iso[0]}-W{iso[1]:02d}"

    con = _db()
    cur = con.cursor()

    # 1) accumulators
    existing = cur.execute("SELECT id FROM accumulators WHERE slip_code=?", (slip_code,)).fetchone()
    if existing:
        acc_id = existing["id"]
        # Replace legs to keep idempotent
        cur.execute("DELETE FROM accumulator_legs WHERE acc_id=?", (acc_id,))
        cur.execute("""UPDATE accumulators SET
            bookmaker=?, legs=?, combined_odds=?, stake=?, status='pending', notes=?
            WHERE id=?""", (bookmaker, len(legs), combined, stake, note, acc_id))
        print(f"↻ Updated slip {slip_code} (id={acc_id})")
    else:
        cur.execute("""INSERT INTO accumulators
            (slip_code, created_at, bookmaker, legs, combined_odds, stake, status, notes)
            VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)""",
            (slip_code, now, bookmaker, len(legs), combined, stake, note))
        acc_id = cur.lastrowid
        print(f"✓ Created slip {slip_code} (id={acc_id})")

    # 2) accumulator_legs
    for L in legs:
        cur.execute("""INSERT INTO accumulator_legs
            (acc_id, sport, match, market, pick, odds, confidence_pct, outcome)
            VALUES (?, ?, ?, ?, ?, ?, ?, NULL)""",
            (acc_id, L["sport"], L["match"], L["market"], L["pick"],
             L["odds"], L["conf"]))

    # 3) bets — single summary row that the dashboard reads
    bet_id_str = f"chain:{slip_code}"
    match_summary = " + ".join(f"{L['pick']} ({L['match']}) @ {L['odds']}" for L in legs)
    last_ko = ""  # caller can pass via --kickoff if needed; not stored in accumulators
    existing_bet = cur.execute("SELECT id FROM bets WHERE bet_id=?", (bet_id_str,)).fetchone()
    if existing_bet:
        bet_pk = existing_bet["id"]
        cur.execute("""UPDATE bets SET
            scan_date=?, week=?, sport=?, match=?, market=?, pick=?, odds=?,
            bookmaker=?, confidence_pct=?, plain_rationale=?, bet_type='compound',
            outcome=NULL, settled_at=NULL
            WHERE id=?""",
            (today, week_str, legs[0]["sport"],
             f"{len(legs)}-leg chain: " + " + ".join(L["match"] for L in legs),
             "1X2", f"{len(legs)}-leg combo @ {combined}", combined, bookmaker,
             conf, f"{match_summary} = {combined}. Stake ₦{stake:,.0f} → ₦{payout:,.2f} on {bookmaker}. {note}",
             bet_pk))
    else:
        cur.execute("""INSERT INTO bets
            (bet_id, scan_date, week, sport, match, kickoff, market, pick, odds,
             bookmaker, ev, our_prob, kelly, model, outcome, created_at, confidence_pct,
             plain_rationale, slip_code, bet_type)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (bet_id_str, today, week_str, legs[0]["sport"],
             f"{len(legs)}-leg chain: " + " + ".join(L["match"] for L in legs),
             last_ko, "1X2", f"{len(legs)}-leg combo @ {combined}", combined,
             bookmaker, None, conf, 0.0, "compound_chain", None, now, conf,
             f"{match_summary} = {combined}. Stake ₦{stake:,.0f} → ₦{payout:,.2f} on {bookmaker}. {note}",
             slip_code, "compound"))
        bet_pk = cur.lastrowid

    # 4) continuous_bet_state — link last_pick_id, KEEP streak_day unchanged
    # RULE: log does not advance the day counter — settle does.
    cur.execute("""UPDATE continuous_bet_state SET
        last_pick_id=?, last_pick_date=?, last_outcome='pending',
        streak_status='active', current_stake=?, updated_at=?
        WHERE id=1""", (bet_pk, today, stake, now))

    # 5) bankroll ledger — pending marker (delta stays NULL until settle writes the result)
    cur.execute("DELETE FROM bankroll WHERE bet_id=?", (f"chain:{slip_code}",))
    cur.execute("""INSERT INTO bankroll (ts, bet_id, stake, delta, balance, kind, note)
                   VALUES (?, ?, ?, NULL, NULL, 'chain_pending', ?)""",
                (now, f"chain:{slip_code}", stake,
                 f"Chain stake on {bookmaker}. Slip {slip_code}. Combined {combined}. Pending. Will settle to ₦{payout:,.2f} if all legs hit (profit ₦{profit:,.2f})."))

    con.commit()
    con.close()

    print()
    print(f"  Combined odds : {combined:.3f}")
    print(f"  Stake         : ₦{stake:,.0f}")
    print(f"  Potential     : ₦{payout:,.2f}  (profit ₦{profit:,.2f})")
    print(f"  Bookmaker     : {bookmaker}")
    print(f"  Status        : pending")
    print(f"  Day counter   : unchanged (settle moves it)")
    print(f"  Bets row id   : {bet_pk}")
    print()
    print("  Dashboard picks this up via /api/betchain/today.")


def cmd_today(args):
    con = _db()
    rows = con.execute("""SELECT id, slip_code, bookmaker, legs, combined_odds, stake,
        status, payout, settled_at, notes
        FROM accumulators WHERE DATE(created_at)=DATE('now') ORDER BY id DESC""").fetchall()
    con.close()
    if not rows:
        print("No chain picks logged today.")
        return
    print(f"Today — {len(rows)} chain slip(s):")
    print("─" * 90)
    for r in rows:
        print(f"  [{r['id']}] {r['slip_code']} · {r['bookmaker']} · {r['legs']} legs · "
              f"{r['combined_odds']:.3f} · stake ₦{r['stake']:,.0f} · {r['status']}")


def main():
    p = argparse.ArgumentParser(description="clawson chain-bet recorder for SabiAI")
    sub = p.add_subparsers(dest="cmd")

    lg = sub.add_parser("log", help="Log a new chain pick from a screenshot")
    lg.add_argument("--slip-code", help="e.g. CHAIN-2026-06-07-002 (auto-generated if omitted)")
    lg.add_argument("--legs", help='Comma list of match:pick:odds[:conf[:sport]]')
    lg.add_argument("--from-json", help="Path to JSON file with legs/stake/bookmaker/note")
    lg.add_argument("--stake", type=float, help="Total stake in NGN (e.g. 1340)")
    lg.add_argument("--bookmaker", default="SportyBet", help="SportyBet (default) or 1xBet")
    lg.add_argument("--conf", type=float, help="Confidence (percent, optional)")
    lg.add_argument("--note", default="", help="Free-form note")

    td = sub.add_parser("today", help="List today's chain picks")

    args = p.parse_args()
    if args.cmd == "log":
        if not args.from_json and not args.legs:
            p.error("log needs either --legs '...' or --from-json FILE")
        if not args.from_json and args.stake is None:
            p.error("log needs --stake (or stake in --from-json)")
        cmd_log(args)
    elif args.cmd == "today":
        cmd_today(args)
    else:
        p.print_help()


if __name__ == "__main__":
    main()
