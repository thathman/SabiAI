#!/usr/bin/env python3
"""
continuous_bet.py — SabiAI continuous compounding bet tracker.

Runs daily. The 30-day compound bet:
  - Selects the best Kelly picks totalling ≥1.30 combined odds (no individual odds cap).
  - Starting stake: ₦1,000. Compounds on win.
  - On loss: 1-week restrategy break, then restart.
  - On 30 successful days: cycle complete, restart with profit withdrawn.

State lives in continuous_bet_state (id=1). Picks are logged to
bets.db so the dashboard reflects the chain.

Cron-safe: silent when nothing to report.
"""
import argparse, json, os, sqlite3, sys, subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path

DB = "~.openclaw/workspace/data/bets.db"
CHAIN_BOOKMAKER = "sporty"
CFG_FIELDS = [
    "starting_stake", "odds_min", "min_confidence",
    "compound_days", "loss_break_days",
]


def cfg():
    """Read SabiAI rules from config table."""
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    out = {
        "starting_stake": 1000,
        "odds_min": 1.30,
        "min_confidence": 0.60, "compound_days": 30,
        "loss_break_days": 7,
    }
    for k in CFG_FIELDS:
        r = c.execute("SELECT value FROM config WHERE key=?", (k,)).fetchone()
        if r and r["value"]:
            try:
                out[k] = json.loads(r["value"])
            except Exception:
                out[k] = float(r["value"]) if "." in r["value"] else int(r["value"])
    c.close()
    return out


def state():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    r = c.execute("SELECT * FROM continuous_bet_state WHERE id=1").fetchone()
    c.close()
    return dict(r) if r else None


def update_state(**fields):
    c = sqlite3.connect(DB)
    sets = ", ".join(f"{k}=?" for k in fields)
    vals = list(fields.values()) + [datetime.now(timezone.utc).isoformat()]
    c.execute(f"UPDATE continuous_bet_state SET {sets}, updated_at=? WHERE id=1", vals)
    c.commit()
    c.close()


def settle_yesterday_pick(st):
    """Check the previous day's continuous bet outcome.
    If won → increment streak, update current_stake.
    If lost → trigger restrategy."""
    if not st.get("last_pick_id"):
        return None
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    pick = c.execute(
        "SELECT * FROM bets WHERE id=?", (st["last_pick_id"],)
    ).fetchone()
    if not pick:
        c.close()
        return None
    if pick["outcome"] not in ("won", "lost"):
        c.close()  # still pending
        return "pending"
    outcome = pick["outcome"]
    if outcome == "won":
        # RULE: day counter advances on settle-WIN. Was on day N (just won), now on day N+1.
        previous_day = st.get("streak_day") or 1
        new_day = previous_day + 1
        new_stake = (st["current_stake"] or cfg()["starting_stake"]) * (pick["odds"] or 1.0)
        if new_day > cfg()["compound_days"]:
            # 30 days complete — withdraw profit, restart
            update_state(
                streak_status="won_30day", streak_day=new_day,
                current_stake=new_stake, total_compounded=(st.get("total_compounded") or 0) + new_stake,
                cycle_count=(st.get("cycle_count") or 0) + 1,
                last_outcome="won_30day",
            )
        else:
            update_state(
                streak_status="active", streak_day=new_day,
                current_stake=new_stake, last_outcome="won",
            )
    else:  # lost
        # RULE: loss resets to day 1, stake back to starting, mark restrategy.
        restrategy_until = (datetime.now(timezone.utc) + timedelta(days=cfg()["loss_break_days"])).strftime("%Y-%m-%d")
        update_state(
            streak_status="restrategy", streak_day=1, current_stake=cfg()["starting_stake"],
            restrategy_until=restrategy_until,
            restrategy_started_at=datetime.now(timezone.utc).isoformat(),
            restrategy_reason=f"Lost day {st['streak_day']} pick (id={st['last_pick_id']})",
            last_outcome="lost",
        )
    c.close()
    return outcome


def _is_chain_bookmaker(value: str) -> bool:
    raw = (value or "").strip().lower()
    return raw.startswith(CHAIN_BOOKMAKER)


def _kelly_score(odds, conf):
    """Kelly fraction: how much of bankroll to bet. Higher = better value."""
    b = odds - 1.0
    if b <= 0 or conf <= 0:
        return 0.0
    fk = (b * conf - (1.0 - conf)) / b
    return max(0.0, fk)


def find_pick():
    """Select the best Kelly picks totalling ≥1.30 combined odds. No individual odds cap.
    Ranks all available picks by Kelly fraction, then combines the top picks until the
    accumulator reaches the target. A single pick at 1.35 is fine. So is 10 picks at 1.03.
    The only constraint is: combined odds ≥1.30 and each pick has positive Kelly value.
    """
    cf = cfg()
    odds_min = cf["odds_min"]   # combined target floor (default 1.30)
    min_conf = cf["min_confidence"]
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    rows = c.execute("""SELECT id, sport, match, market, pick, odds, confidence_pct, plain_rationale, bookmaker
        FROM bets WHERE outcome IS NULL
        AND confidence_pct >= 55 AND odds >= 1.01
        ORDER BY confidence_pct DESC LIMIT 80""").fetchall()
    if not rows:
        c.close()
        return None, "no picks in bets yet (daily scan hasn't run today)"

    picks = []
    for r in rows:
        odds = float(r["odds"] or 1.0)
        conf = float(r["confidence_pct"] or 0) / 100.0
        ks = _kelly_score(odds, conf)
        if ks <= 0:
            continue
        picks.append({
            "id": r["id"], "sport": r["sport"], "match": r["match"],
            "market": r["market"], "pick": r["pick"], "odds": odds,
            "conf": conf, "kelly_score": ks,
            "rationale": r["plain_rationale"] or "",
            "bookmaker": r["bookmaker"] or "",
        })

    # Sort by Kelly score descending — highest value first
    picks.sort(key=lambda p: -p["kelly_score"])
    sporty = [p for p in picks if _is_chain_bookmaker(p.get("bookmaker"))]
    if not sporty:
        sporty = picks  # fallback: any bookmaker

    # Greedy: take top picks until combined odds clears the floor
    seen_matches = set()
    legs, combined_odds, combined_conf = [], 1.0, 1.0
    for p in sporty:
        if p["match"] in seen_matches:
            continue  # one selection per game
        legs.append(p)
        seen_matches.add(p["match"])
        combined_odds *= p["odds"]
        combined_conf *= p["conf"]
        if combined_odds >= odds_min:
            break
        if len(legs) >= 8:
            break  # safety: max 8 legs

    if not legs or combined_odds < odds_min:
        c.close()
        return None, f"cannot build combo ≥{odds_min} odds (best: {combined_odds:.2f} from {len(sporty)} picks)"
    c.close()
    return (legs, combined_odds, combined_conf), None


def notify_whatsapp(text):
    """Send a WhatsApp message via OpenClaw CLI."""
    try:
        subprocess.run(
            [os.path.expanduser("~/.npm-global/bin/openclaw"), "message", "send", "--channel", "whatsapp",
             "--target", "+234XXXXXXXXXX", "--message", text],
            capture_output=True, text=True, timeout=15,
        )
    except Exception as e:
        print(f"notify error: {e}", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--reset", action="store_true",
                    help="Reset chain to day 0, status=idle (manual use).")
    args = ap.parse_args()

    st = state()
    if not st:
        print("ERROR: continuous_bet_state not initialized", file=sys.stderr)
        sys.exit(1)

    if args.reset:
        update_state(streak_status="idle", streak_day=0,
                     current_stake=cfg()["starting_stake"],
                     restrategy_until=None, restrategy_started_at=None,
                     last_pick_id=None, last_pick_date=None, last_outcome=None)
        print("Reset to idle.")
        return

    # 1) Settle yesterday's pick
    if st.get("streak_status") == "active" and st.get("last_pick_id"):
        outcome = settle_yesterday_pick(st)
        st = state()  # reload

    # 2) If restrategy active, silent
    if st.get("streak_status") == "restrategy":
        until = st.get("restrategy_until")
        if until and until > datetime.now(timezone.utc).strftime("%Y-%m-%d"):
            if not args.dry_run:
                return  # silent
            print(f"In restrategy until {until}")
            return

    # 3) If 30-day cycle complete
    if st.get("streak_status") == "won_30day":
        msg = (f"🎯 Continuous bet cycle complete: 30 days, "
               f"compounded to ₦{st['current_stake']:,.0f}. "
               f"Profit withdrawn, restarting at ₦1,000.")
        if not args.dry_run:
            notify_whatsapp(msg)
            update_state(streak_status="idle", streak_day=0,
                         current_stake=cfg()["starting_stake"])
        print(msg)
        return

    # 4) If idle, ready to start
    result, err = find_pick()
    if result is None:
        if err and not args.dry_run:
            print(f"scan note: {err}", file=sys.stderr)
        # silent if no qualifying pick — chain doesn't force
        return

    legs, combined_odds, combined_conf = result
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    stake = st.get("current_stake") or cfg()["starting_stake"]
    bet_type = "continuous_single" if len(legs) == 1 else f"continuous_accumulator_{len(legs)}leg"
    is_multi = len(legs) > 1
    now = datetime.now(timezone.utc).isoformat()
    slip_code = None  # Hendrix pastes this back after placing
    if is_multi:
        cur = c.execute("""INSERT INTO accumulators
          (slip_code, created_at, bookmaker, legs, combined_odds, stake, status, notes)
          VALUES (?,?,?,?,?,?,?,?)""",
          (slip_code, now, "1xBet", len(legs), combined_odds, stake, "pending",
           f"continuous chain, day {st['streak_day']+1}, conf {combined_conf:.0%}"))
        acc_id = cur.lastrowid
        for L in legs:
            c.execute("""INSERT INTO accumulator_legs
              (acc_id, sport, match, market, pick, odds, confidence_pct, outcome)
              VALUES (?,?,?,?,?,?,?,?)""",
              (acc_id, L["sport"], L["match"], L["market"], L["pick"], L["odds"],
               L["conf"]*100, None))
        bet_id = f"acc:{acc_id}"
        match_summary = " + ".join(f"{L['sport']} {L['pick']}@{L['odds']:.2f}" for L in legs)
        market_summary = "accumulator"
        pick_summary = f"{len(legs)}-leg combo @ {combined_odds:.2f}"
    else:
        L = legs[0]
        cur = c.execute("""INSERT INTO bets
          (bet_id, scan_date, week, sport, match, kickoff, market, pick, odds,
           bookmaker, ev, our_prob, kelly, model, outcome, created_at, confidence_pct,
           plain_rationale, slip_code, bet_type)
          VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
          (f"cont:{now}", datetime.now(timezone.utc).strftime("%Y-%m-%d"),
           datetime.now(timezone.utc).strftime("%Y-W%W"),
           L["sport"], L["match"], "", L["market"], L["pick"], L["odds"],
           "1xBet", combined_odds * combined_conf - 1.0, combined_conf, 0.0,
           "continuous_chain", None, now, L["conf"]*100, L["rationale"],
           slip_code, bet_type))
        bet_id = f"bet:{cur.lastrowid}"
        match_summary = L["match"]; market_summary = L["market"]; pick_summary = L["pick"]
        acc_id = None
    c.commit()
    # Update state: mark the bet as "in flight".
    # RULE: streak_day only moves on SETTLE, not on log.
    #   - Log:   streak_day stays at current position (we are now betting on day N)
    #   - Settle WIN:  streak_day += 1, current_stake *= odds
    #   - Settle LOSS: streak_day = 1, current_stake = starting_stake
    current_day = st.get("streak_day") or 1
    update_state(
        streak_status="active", streak_day=current_day, current_stake=stake,
        last_pick_id=cur.lastrowid, last_pick_date=now, last_outcome="pending",
    )
    c.close()
    # Build streak record — day/30, amount won, running odds product
    start_stake = cfg()["starting_stake"]
    streak_mult = stake / start_stake if start_stake else 1.0
    amount_won = stake - start_stake
    won_str = f"₦{amount_won:,.0f}" if amount_won >= 0 else f"-₦{abs(amount_won):,.0f}"
    new_day = current_day  # current_day = day we are betting on (moves on settle)
    streak_wins = max(0, new_day - 1)  # days already won to reach this stake
    streak_line = (f"Day {new_day}/30 · {streak_wins} wins · "
                   f"{won_str} won · {streak_mult:.2f}× running odds")

    if is_multi:
        type_line = f"Accumulator ({len(legs)} legs)"
        legs_lines = ""
        for i, L in enumerate(legs, 1):
            legs_lines += f"\n  {i}. {L['sport']} | {L['match']}\n     Pick: {L['pick']} @ {L['odds']:.2f}"
        pick_block = f"Type: {type_line}{legs_lines}\nCombined odds: {combined_odds:.2f}"
    else:
        L = legs[0]
        sys.path.insert(0, '~.openclaw/workspace/scripts')
        try:
            import plain_render as _pr
            rationale = _pr.plain_rationale({"our_prob": L["conf"]*100,
                                              "model": L["rationale"],
                                              "market": L["market"],
                                              "pick": L["pick"],
                                              "home": L["match"].split(" vs ")[0] if " vs " in L["match"] else "",
                                              "away": L["match"].split(" vs ")[1] if " vs " in L["match"] else ""})
            pick_text = _pr.plain_pick({"market": L["market"], "pick": L["pick"]})
        except Exception:
            rationale = L["rationale"] or "Model pick"
            pick_text = L["pick"]
        conf_word = "Very strong" if L['conf'] >= 0.75 else "Strong" if L['conf'] >= 0.67 else "Solid" if L['conf'] >= 0.58 else "Slight lean"
        pick_block = (f"Type: Single\n"
                      f"Match: {L['match']}\n"
                      f"Pick: {pick_text} @ {L['odds']:.2f}\n"
                      f"Confidence: {L['conf']*100:.0f}% ({conf_word})\n"
                      f"Why: {rationale}")

    msg = (f"🎯 *Compound Bet — {streak_line}*\n"
           f"{'—'*32}\n"
           f"{pick_block}\n"
           f"{'—'*32}\n"
           f"Stake: ₦{stake:,.0f} → If win: ₦{stake * combined_odds:,.0f}")
    if not args.dry_run:
        notify_whatsapp(msg)
    print(msg)

if __name__ == "__main__":
    main()
