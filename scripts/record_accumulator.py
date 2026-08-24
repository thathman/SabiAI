#!/usr/bin/env python3
"""
record_accumulator.py — generic accumulator screenshot logger for SabiAI.

Use this for multi-leg slips that are not the 30-day compound chain and not the
weekly long-shot builder. It writes the slip into:

  1. accumulators       — slip summary
  2. accumulator_legs   — one row per leg
  3. bets               — summary row for settled-bet history

It does NOT touch continuous_bet_state.

Examples:
  python3 record_accumulator.py log \
    --slip-code 82749633423 \
    --legs "England vs New Zealand:England:1.097,Argentina vs Honduras:Argentina:1.114" \
    --stake 0.72 \
    --payout 1.41 \
    --bookmaker 1xBet \
    --scan-date 2026-06-06 \
    --status won \
    --note "Kelly suggestions screenshot"

  python3 record_accumulator.py today
"""
import argparse
import sqlite3
import sys
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
    if "1x" in raw:
        return "1xBet"
    if "sport" in raw:
        return "SportyBet"
    return value.strip() if value else "1xBet"


def _parse_legs(s: str):
    legs = []
    for chunk in (s or "").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        parts = [p.strip() for p in chunk.split(":")]
        if len(parts) < 3:
            raise ValueError(f"leg '{chunk}' must be match:pick:odds")
        leg = {
            "match": parts[0],
            "pick": parts[1],
            "odds": float(parts[2]),
            "conf": None,
            "sport": "Football",
            "market": "1X2",
        }
        if len(parts) >= 4 and parts[3]:
            try:
                leg["conf"] = float(parts[3])
            except ValueError:
                pass
        if len(parts) >= 5 and parts[4]:
            leg["sport"] = parts[4]
        if len(parts) >= 6 and parts[5]:
            leg["market"] = parts[5]
        if not leg["match"] or not leg["pick"] or leg["odds"] < 1.01:
            raise ValueError(f"bad leg: {chunk}")
        legs.append(leg)
    if not legs:
        raise ValueError("no legs provided")
    return legs


def _week_str(scan_date: str):
    dt = datetime.strptime(scan_date, "%Y-%m-%d").date()
    iso = dt.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def _last_bankroll_balance(cur):
    row = cur.execute("SELECT balance FROM bankroll ORDER BY id DESC LIMIT 1").fetchone()
    return float(row["balance"]) if row and row["balance"] is not None else 0.0


def _write_bankroll(cur, bet_id: str, stake: float, payout: float, status: str, settled_at: str, note: str):
    status = (status or "").strip().lower()
    if status not in ("won", "lost"):
        return

    delta = round(float(payout) - float(stake), 2) if status == "won" else -round(float(stake), 2)
    prev = _last_bankroll_balance(cur)
    balance = round(prev + delta, 2)
    kind = "acc_win" if status == "won" else "acc_loss"

    cur.execute("DELETE FROM bankroll WHERE bet_id=?", (bet_id,))
    cur.execute(
        "INSERT INTO bankroll(ts, bet_id, stake, delta, balance, kind, note) VALUES(?,?,?,?,?,?,?)",
        (
            settled_at or _now(),
            bet_id,
            float(stake),
            delta,
            balance,
            kind,
            note or f"Accumulator {status.upper()}",
        ),
    )


def cmd_log(args):
    slip_code = args.slip_code.strip() if args.slip_code else None
    if not slip_code:
        slip_code = f"ACCA-{_today()}-{int(datetime.now(timezone.utc).timestamp())}"
    bookmaker = _canon_bookmaker(args.bookmaker)
    scan_date = args.scan_date or _today()
    settled_at = args.settled_at or _now()
    status = (args.status or "pending").strip().lower()
    if status not in ("pending", "won", "lost"):
        print("ERROR: status must be pending, won, or lost")
        sys.exit(1)
    outcome = {"won": "win", "lost": "loss"}.get(status)

    if args.from_json:
        import json
        with open(args.from_json, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
        legs = _parse_legs(
            ",".join(
                f"{L['match']}:{L['pick']}:{L['odds']}:{L.get('conf','')}:{L.get('sport','Football')}:{L.get('market','1X2')}"
                for L in payload.get("legs", [])
            )
        )
        stake = float(payload.get("stake") or 0)
        payout = float(payload.get("payout") or 0) if payload.get("payout") is not None else None
        bookmaker = _canon_bookmaker(payload.get("bookmaker") or bookmaker)
        note = payload.get("note") or args.note or ""
        if payload.get("scan_date"):
            scan_date = payload["scan_date"]
        if payload.get("settled_at"):
            settled_at = payload["settled_at"]
        if payload.get("status"):
            status = str(payload["status"]).strip().lower()
    else:
        legs = _parse_legs(args.legs or "")
        stake = float(args.stake or 0)
        payout = float(args.payout) if args.payout is not None else None
        note = args.note or ""

    if stake <= 0:
        print("ERROR: stake must be > 0")
        sys.exit(1)

    combined = 1.0
    for leg in legs:
        combined *= float(leg["odds"])
    combined = round(combined, 3)
    if payout is None:
        payout = round(stake * combined, 2) if status == "won" else 0.0
    profit = round(payout - stake, 2) if status == "won" else (-round(stake, 2) if status == "lost" else 0.0)
    week_str = _week_str(scan_date)
    created_at = settled_at if status != "pending" else _now()

    c = _db()
    cur = c.cursor()

    existing = cur.execute("SELECT id FROM accumulators WHERE slip_code=?", (slip_code,)).fetchone()
    existing_bet = cur.execute("SELECT id, created_at FROM bets WHERE bet_id=?", (f"acc:{slip_code}",)).fetchone()
    if existing:
        acc_id = existing["id"]
        cur.execute("DELETE FROM accumulator_legs WHERE acc_id=?", (acc_id,))
        cur.execute("""UPDATE accumulators SET
            created_at=?, bookmaker=?, legs=?, combined_odds=?, stake=?, status=?, payout=?, settled_at=?, notes=?
            WHERE id=?""",
            (created_at, bookmaker, len(legs), combined, stake, status, payout if status != "pending" else None,
             settled_at if status != "pending" else None, note, acc_id))
        print(f"↻ Updated accumulator {slip_code} (id={acc_id})")
    else:
        cur.execute("""INSERT INTO accumulators
            (slip_code, created_at, bookmaker, legs, combined_odds, stake, status, payout, settled_at, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (slip_code, created_at, bookmaker, len(legs), combined, stake, status,
             payout if status != "pending" else None,
             settled_at if status != "pending" else None,
             note))
        acc_id = cur.lastrowid
        print(f"✓ Created accumulator {slip_code} (id={acc_id})")

    for leg in legs:
        cur.execute("""INSERT INTO accumulator_legs
            (acc_id, sport, match, market, pick, odds, confidence_pct, outcome)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (acc_id, leg["sport"], leg["match"], leg["market"], leg["pick"],
             leg["odds"], leg["conf"], outcome))

    bet_id = f"acc:{slip_code}"
    match_summary = " + ".join(f"{leg['pick']} ({leg['match']}) @ {leg['odds']:.3f}" for leg in legs)
    existing_bet_row_id = existing_bet["id"] if existing_bet else None
    existing_bet_created_at = existing_bet["created_at"] if existing_bet else None
    bet_update = (
        scan_date, week_str, legs[0]["sport"],
        f"{len(legs)}-leg accumulator: " + " + ".join(leg["match"] for leg in legs),
        "", "1X2", f"{len(legs)}-leg combo @ {combined:.3f}", combined,
        bookmaker, None, combined - 1.0, 0.0, "accumulator",
        outcome, existing_bet_created_at or created_at, settled_at,
        None, f"{match_summary}. Stake {stake:.2f} → payout {payout:.2f}. {note}",
        slip_code, "accumulator"
    )
    if existing_bet_row_id:
        cur.execute("""UPDATE bets SET
            scan_date=?, week=?, sport=?, match=?, kickoff=?, market=?, pick=?, odds=?,
            bookmaker=?, ev=?, our_prob=?, kelly=?, model=?, outcome=?, created_at=?, settled_at=?,
            confidence_pct=?, plain_rationale=?, slip_code=?, bet_type=?
            WHERE id=?""", (*bet_update, existing_bet_row_id))
    else:
        cur.execute("""INSERT INTO bets
            (bet_id, scan_date, week, sport, match, kickoff, market, pick, odds,
             bookmaker, ev, our_prob, kelly, model, outcome, created_at, settled_at,
             confidence_pct, plain_rationale, slip_code, bet_type)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (bet_id, *bet_update))

    if status in ("won", "lost"):
        bankroll_note = (
            f"Accumulator {status.upper()} on {bookmaker}. Slip {slip_code}. "
            f"Stake {stake:.2f} → payout {payout:.2f}. {note}".strip()
        )
        _write_bankroll(cur, bet_id, stake, payout, status, settled_at, bankroll_note)

    c.commit()
    c.close()

    print()
    print(f"  Slip code     : {slip_code}")
    print(f"  Combined odds : {combined:.3f}")
    print(f"  Stake         : {stake:.2f}")
    print(f"  Payout        : {payout:.2f}")
    print(f"  Profit        : {profit:.2f}")
    print(f"  Bookmaker     : {bookmaker}")
    print(f"  Status        : {status}")
    print(f"  Bets row id   : {existing_bet_row_id if existing_bet_row_id else cur.lastrowid}")


def cmd_today(args):
    c = _db()
    rows = c.execute("""SELECT id, slip_code, bookmaker, legs, combined_odds, stake, status, payout, settled_at, notes
        FROM accumulators WHERE DATE(created_at)=DATE('now') ORDER BY id DESC""").fetchall()
    c.close()
    if not rows:
        print("No accumulators logged today.")
        return
    print(f"Today — {len(rows)} accumulator(s):")
    print("─" * 90)
    for r in rows:
        payout = f" · payout {r['payout']:.2f}" if r["payout"] is not None else ""
        print(f"  [{r['id']}] {r['slip_code']} · {r['bookmaker']} · {r['legs']} legs · "
              f"{r['combined_odds']:.3f} · stake {r['stake']:.2f} · {r['status']}{payout}")


def main():
    ap = argparse.ArgumentParser(description="clawson generic accumulator recorder for SabiAI")
    sub = ap.add_subparsers(dest="cmd")

    lg = sub.add_parser("log", help="Log a new accumulator from a screenshot")
    lg.add_argument("--slip-code", help="Screenshot ticket / slip number")
    lg.add_argument("--legs", help="Comma list of match:pick:odds[:conf[:sport[:market]]]")
    lg.add_argument("--from-json", help="Path to JSON file with slip data")
    lg.add_argument("--stake", type=float, required=False, help="Stake amount")
    lg.add_argument("--payout", type=float, help="Paid-out amount when settled")
    lg.add_argument("--bookmaker", default="1xBet")
    lg.add_argument("--scan-date", help="Scan date YYYY-MM-DD")
    lg.add_argument("--settled-at", help="Settled timestamp ISO-8601 or YYYY-MM-DDTHH:MM:SSZ")
    lg.add_argument("--status", default="won", help="pending, won, or lost")
    lg.add_argument("--note", default="", help="Free-form note")

    sub.add_parser("today", help="List today's accumulators")

    args = ap.parse_args()
    if args.cmd == "log":
        if not args.from_json and not args.legs:
            ap.error("log needs either --legs or --from-json")
        if not args.from_json and args.stake is None:
            ap.error("log needs --stake unless stake is present in --from-json")
        cmd_log(args)
    elif args.cmd == "today":
        cmd_today(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
