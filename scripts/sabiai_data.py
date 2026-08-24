#!/usr/bin/env python3
"""sabiai_data.py — stats/metrics layer for the SabiAI dashboard (reads bets.db)."""
import sqlite3, json, sys, os
from datetime import datetime

DB = "/home/hendrix/.openclaw/workspace/data/bets.db"

# Import plain_render for live plain_pick generation
sys.path.insert(0, os.path.dirname(__file__))
try:
    import plain_render as _PR
except Exception:
    _PR = None

def _c():
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row; return c

def config():
    c = _c(); cfg = {r["key"]: r["value"] for r in c.execute("SELECT key,value FROM config")}; c.close()
    for k in ("sports_focus","markets_focus","bookmakers"):
        if k in cfg:
            try: cfg[k] = json.loads(cfg[k])
            except Exception: pass
    return cfg

def _settled(c):
    # Only count bets that were actually selected (placed by the user).
    return c.execute("SELECT * FROM bets WHERE outcome IN ('win','loss') AND selected=1 ORDER BY settled_at, id").fetchall()

# ── Sport label normaliser ────────────────────────────────────────────────────
def _norm_sport(s):
    """Collapse sport label variants into one canonical form."""
    if not s:
        return "Other"
    clean = s.strip()
    l = clean.lower()
    if "intl friendl" in l or ("friendl" in l and ("⚽" in clean or "soccer" in l or "football" in l)):
        return "⚽ Intl Friendlies"
    if "premier league" in l or "eng.1" in l:  return "⚽ EPL"
    if "la liga" in l:                           return "⚽ La Liga"
    if "serie a" in l:                           return "⚽ Serie A"
    if "bundesliga" in l:                        return "⚽ Bundesliga"
    if "ligue 1" in l:                           return "⚽ Ligue 1"
    if "champions" in l and "soccer" in l:       return "⚽ UCL"
    if "mlb" in l or "⚾" in clean:              return "⚾ MLB"
    if "nba" in l or "🏀" in clean:              return "🏀 NBA"
    if "nhl" in l or "🏒" in clean:              return "🏒 NHL"
    if "nfl" in l or "🏈" in clean:              return "🏈 NFL"
    if "tennis" in l or "atp" in l or "wta" in l or "🎾" in clean: return "🎾 Tennis"
    if "mma" in l or "ufc" in l or "🥊" in clean:  return "🥊 MMA"
    if "boxing" in l:                             return "🥊 Boxing"
    if "rugby" in l or "🏉" in clean:            return "🏉 Rugby"
    if "cricket" in l or "🏏" in clean:          return "🏏 Cricket"
    # Generic football/soccer with no league → keep emoji if present, else "⚽ Football"
    if "football" in l or "soccer" in l or "⚽" in clean:
        return "⚽ Football" if "⚽" not in clean else clean
    return clean

# ── Market name normaliser ────────────────────────────────────────────────────
def _norm_market(m):
    """Collapse market label variants into canonical form."""
    if not m:
        return "Other"
    l = m.strip().lower()
    if l in ("1x2","h2h","match winner","match winner (1x2)","moneyline","winner"):
        return "1X2"
    if "btts" in l or "both teams to score" in l:
        return "BTTS"
    if "double chance" in l:
        return "Double Chance"
    if "draw no bet" in l or l == "dnb":
        return "Draw No Bet"
    if "handicap" in l or "spread" in l or "asian" in l:
        return "Handicap"
    if "o/u" in l or "total" in l or "over" in l or "under" in l:
        return "Over/Under"
    if "corner" in l:
        return "Corners"
    if "card" in l:
        return "Cards"
    if "first goal" in l or "anytime goal" in l or "scorer" in l:
        return "Goalscorer"
    return m.strip()

def overview():
    c = _c(); cfg = config()
    start = float(cfg.get("bankroll_start", 0) or 0)
    unit_stake = float(cfg.get("unit_stake", 0) or 0)  # NGN per Kelly unit

    # Realised P/L from the bankroll ledger (one row per settled money event)
    ledger_pl = c.execute(
        "SELECT COALESCE(SUM(delta), 0) FROM bankroll WHERE delta IS NOT NULL"
    ).fetchone()[0]
    chain_profit = c.execute(
        "SELECT COALESCE(SUM(delta), 0) FROM bankroll WHERE delta IS NOT NULL AND kind LIKE 'chain%'"
    ).fetchone()[0]

    state_row = c.execute(
        "SELECT current_stake, starting_stake FROM continuous_bet_state WHERE id=1"
    ).fetchone()
    chain_current = float(state_row["current_stake"] or 1000) if state_row else 1000

    # Pending compound stake — money currently out for a running chain bet
    pending_compound = c.execute(
        "SELECT COUNT(*) FROM bets WHERE bet_type='compound' AND outcome IS NULL"
    ).fetchone()[0]
    stake_in_play = chain_current if pending_compound else 0.0

    s = _settled(c)
    won  = sum(1 for r in s if r["outcome"] == "win")
    lost = sum(1 for r in s if r["outcome"] == "loss")
    not_placed = c.execute("SELECT COUNT(*) FROM bets WHERE outcome='not_placed'").fetchone()[0]
    pending = c.execute("SELECT COUNT(*) FROM bets WHERE outcome IS NULL AND selected=1").fetchone()[0]
    unselected = c.execute("SELECT COUNT(*) FROM bets WHERE outcome IS NULL AND selected=0").fetchone()[0]
    n = won + lost

    profit_units = sum((r["odds"]-1) if r["outcome"]=="win" else -1 for r in s if r["odds"])

    # Bankroll: starting + realised ledger P/L - any stake currently in play
    current = start + ledger_pl - stake_in_play

    streak = 0; streak_kind = None
    for r in reversed(s):
        if streak_kind is None: streak_kind = r["outcome"]
        if r["outcome"] == streak_kind: streak += 1
        else: break
    c.close()
    profit = current - start
    return {
        "brand": cfg.get("brand","SabiAI"),
        "onboarded": cfg.get("onboarded","no"),
        "started_on": cfg.get("started_on"),
        "currency": cfg.get("currency","NGN"),
        "bankroll_start": start, "bankroll_current": current,
        "profit": profit, "roi_pct": round(profit/start*100,1) if start else 0,
        "won": won, "lost": lost, "pending": pending, "settled": n,
        "not_placed": not_placed,
        "unselected": unselected,
        "win_rate": round(100*won/n,1) if n else None,
        "profit_units": round(profit_units,2),
        "streak": streak, "streak_kind": streak_kind,
        "target_roi_pct": cfg.get("target_roi_pct"),
        "chain_profit": round(chain_profit, 2),
        "stake_in_play": round(stake_in_play, 2),
        "pending_compound": pending_compound,
    }

def by_sport():
    c = _c(); out = []
    raw = c.execute("""SELECT sport,
            COUNT(*) n, SUM(outcome='win') won,
            SUM(CASE WHEN outcome='win' THEN odds-1 ELSE -1 END) prof
        FROM bets WHERE outcome IN ('win','loss') AND selected=1 AND sport IS NOT NULL
        GROUP BY sport ORDER BY n DESC""").fetchall()
    # Merge normalised sport labels
    merged = {}
    for r in raw:
        key = _norm_sport(r["sport"])
        if key not in merged:
            merged[key] = {"n": 0, "won": 0, "prof": 0.0}
        merged[key]["n"]   += r["n"]
        merged[key]["won"] += r["won"]
        merged[key]["prof"]+= r["prof"] or 0.0
    for sport, d in sorted(merged.items(), key=lambda x: -x[1]["n"]):
        n = d["n"]
        out.append({"sport": sport, "n": n, "won": d["won"],
                    "win_rate": round(100*d["won"]/n,1) if n else 0,
                    "roi": round(d["prof"]/n*100,1) if n else 0,
                    "profit_units": round(d["prof"],2)})
    c.close(); return out

def over_time():
    c = _c()
    bank = [{"ts": r["ts"], "balance": r["balance"]} for r in
            c.execute("SELECT ts,balance FROM bankroll ORDER BY id")]
    cum = []; run = 0.0
    for r in c.execute("""SELECT settled_at, outcome, odds FROM bets
                          WHERE outcome IN ('win','loss') AND selected=1 ORDER BY settled_at, id"""):
        run += (r["odds"]-1) if r["outcome"]=="win" else -1
        cum.append({"ts": r["settled_at"], "units": round(run,2)})
    c.close(); return {"bankroll": bank, "cumulative_profit": cum}

def breakdown():
    c = _c()
    rows = c.execute("""SELECT market k, COUNT(*) n, SUM(outcome='win') won
        FROM bets WHERE outcome IN ('win','loss') AND selected=1 AND market IS NOT NULL
        GROUP BY market ORDER BY n DESC""").fetchall()
    # Merge normalised market labels
    merged = {}
    for r in rows:
        key = _norm_market(r["k"])
        if key not in merged:
            merged[key] = {"n": 0, "won": 0}
        merged[key]["n"]   += r["n"]
        merged[key]["won"] += r["won"]
    by_market = [{"key": k, "n": d["n"], "won": d["won"],
                  "win_rate": round(100*d["won"]/d["n"],1) if d["n"] else 0}
                 for k, d in sorted(merged.items(), key=lambda x: -x[1]["n"])]
    conf = []
    for lo,hi,lab in [(0,55,"Coin-flip <55%"),(55,62,"Slight 55-62%"),
                      (62,70,"Solid 62-70%"),(70,200,"Strong 70%+")]:
        r = c.execute("""SELECT COUNT(*) n, SUM(outcome='win') won FROM bets
            WHERE outcome IN ('win','loss') AND selected=1 AND confidence_pct>=? AND confidence_pct<?""",(lo,hi)).fetchone()
        if r["n"]: conf.append({"band":lab,"n":r["n"],"won":r["won"],
                                "win_rate":round(100*r["won"]/r["n"],1)})
    singles = c.execute(
        "SELECT COUNT(*) FROM bets WHERE outcome IN ('win','loss') AND selected=1 AND (bet_type IS NULL OR bet_type NOT IN ('compound','longshot'))"
    ).fetchone()[0]
    accas = c.execute("SELECT COUNT(*) FROM accumulators WHERE status IN ('won','lost')").fetchone()[0]
    c.close()
    return {"by_market": by_market, "by_confidence": conf,
            "singles": singles, "accumulators": accas}

def accumulators():
    c = _c()
    tot = c.execute("SELECT COUNT(*) FROM accumulators WHERE status IN ('won','lost')").fetchone()[0]
    won = c.execute("SELECT COUNT(*) FROM accumulators WHERE status='won'").fetchone()[0]
    agg = c.execute("""SELECT AVG(legs) al, AVG(combined_odds) ao,
        SUM(CASE WHEN status='won' THEN COALESCE(payout,0)-COALESCE(stake,0)
                 WHEN status='lost' THEN -COALESCE(stake,0) ELSE 0 END) prof
        FROM accumulators WHERE status IN ('won','lost')""").fetchone()
    recent = [dict(r) for r in c.execute("""SELECT slip_code,legs,combined_odds,stake,status,settled_at
        FROM accumulators ORDER BY id DESC LIMIT 20""")]
    c.close()
    return {"total": tot, "won": won, "hit_rate": round(100*won/tot,1) if tot else None,
            "avg_legs": round(agg["al"],1) if agg["al"] else None,
            "avg_odds": round(agg["ao"],2) if agg["ao"] else None,
            "profit": round(agg["prof"],2) if agg["prof"] else 0, "recent": recent}

def streaks_edge():
    c = _c(); s = _settled(c)
    longest_w = longest_l = cur = 0; kind = None
    for r in s:
        if r["outcome"] == kind: cur += 1
        else: kind = r["outcome"]; cur = 1
        if kind == "win": longest_w = max(longest_w, cur)
        else: longest_l = max(longest_l, cur)
    clvs = [r["clv"] for r in s if r["clv"] is not None]
    c.close()
    return {"longest_win_streak": longest_w, "longest_loss_streak": longest_l,
            "avg_clv_pct": round(sum(clvs)/len(clvs),2) if clvs else None, "clv_n": len(clvs)}

def markets_covered():
    c = _c()
    rows = c.execute("""SELECT market, COUNT(*) n FROM bets WHERE selected=1 AND market IS NOT NULL
        GROUP BY market ORDER BY n DESC""").fetchall()
    try:
        preds = c.execute("""SELECT market, COUNT(*) n FROM predictions WHERE market IS NOT NULL
            GROUP BY market""").fetchall()
    except Exception:
        preds = []
    c.close()
    agg = {}
    for r in rows:
        key = _norm_market(r["market"])
        agg[key] = agg.get(key, 0) + r["n"]
    for r in preds:
        key = _norm_market(r["market"])
        agg[key] = agg.get(key, 0) + r["n"]
    return [{"market": k, "n": v} for k,v in sorted(agg.items(), key=lambda x:-x[1])]

def history(limit=200):
    """Legacy: flat list (kept for any old consumers)."""
    return history_page(page=1, page_size=limit)["rows"]


def history_page(page=1, page_size=25, sport=None, outcome=None, bookmaker=None, q=None):
    """Filterable, paginated bet history.
    outcome: 'win' | 'loss' | 'pending' | None (all)."""
    c = _c()
    where = ["bet_type IN ('kelly', 'accumulator')"]
    params = []
    if sport:
        where.append("sport LIKE ?"); params.append(f"%{sport}%")
    if outcome == "pending":
        where.append("outcome IS NULL")
    elif outcome:
        where.append("outcome = ?"); params.append(outcome)
    if bookmaker:
        where.append("bookmaker = ?"); params.append(bookmaker)
    if q:
        where.append("(match LIKE ? OR pick LIKE ?)"); params += [f"%{q}%", f"%{q}%"]
    W = " AND ".join(where)

    total = c.execute(f"SELECT COUNT(*) FROM bets WHERE {W}", params).fetchone()[0]
    # Aggregates over the WHOLE filtered set (not just the page)
    agg = c.execute(f"""SELECT
        SUM(outcome='win') w, SUM(outcome='loss') l,
        SUM(CASE WHEN outcome='win' AND odds THEN odds-1
                 WHEN outcome='loss' THEN -1 ELSE 0 END) pu,
        SUM(outcome IS NULL) pending
        FROM bets WHERE {W}""", params).fetchone()

    page = max(1, int(page)); page_size = min(100, max(5, int(page_size)))
    rows = [dict(r) for r in c.execute(f"""SELECT id,scan_date,sport,match,market,pick,odds,
        confidence_pct,outcome,clv,result_score,settled_at,bookmaker,notes,selected
        FROM bets WHERE {W}
        ORDER BY COALESCE(settled_at, scan_date) DESC, id DESC
        LIMIT ? OFFSET ?""", params + [page_size, (page - 1) * page_size])]
    for b in rows:
        b["sport"] = _norm_sport(b.get("sport"))

    # Distinct values for the filter dropdowns (unfiltered domain)
    sports = [r[0] for r in c.execute("""SELECT DISTINCT sport FROM bets
        WHERE bet_type IN ('kelly','accumulator') AND sport IS NOT NULL ORDER BY sport""")]
    bookmakers = [r[0] for r in c.execute("""SELECT DISTINCT bookmaker FROM bets
        WHERE bet_type IN ('kelly','accumulator') AND bookmaker IS NOT NULL AND bookmaker != ''
        ORDER BY bookmaker""")]
    c.close()
    return {
        "rows": rows, "total": total, "page": page, "page_size": page_size,
        "pages": max(1, -(-total // page_size)),
        "stats": {"won": agg["w"] or 0, "lost": agg["l"] or 0,
                  "profit_units": round(agg["pu"] or 0, 2), "pending": agg["pending"] or 0},
        "sports": list(dict.fromkeys(_norm_sport(s) for s in sports)),
        "bookmakers": bookmakers,
    }

def toggle_selected(bet_id: int, selected: bool):
    """Mark a bet as selected (placed by user) or deselect it."""
    c = _c()
    c.execute("UPDATE bets SET selected=? WHERE id=?", (1 if selected else 0, bet_id))
    c.commit()
    updated = c.execute("SELECT id, match, selected FROM bets WHERE id=?", (bet_id,)).fetchone()
    c.close()
    if not updated:
        return None
    return {"id": updated["id"], "match": updated["match"], "selected": bool(updated["selected"])}

def live_history(limit=100):
    c = _c()
    try:
        rows = [dict(r) for r in c.execute("""
            SELECT date, sport, match, market, signals, status,
                   juicy_score, outcome, result, was_juicy, alerted_at, created_at
            FROM live_bets
            ORDER BY id DESC LIMIT ?""", (limit,))]
    except Exception:
        rows = []
    c.close()
    settled = [r for r in rows if r.get('outcome') in ('win','loss')]
    won = sum(1 for r in settled if r.get('outcome') == 'win')
    return {"rows": rows, "total_alerted": sum(1 for r in rows if r.get('status') == 'alerted'),
            "settled": len(settled), "won": won, "lost": len(settled) - won}

def today():
    c = _c(); d = datetime.now().strftime("%Y-%m-%d")
    rows = [dict(r) for r in c.execute("""SELECT id,sport,match,kickoff,market,pick,odds,
        confidence_pct,plain_rationale,bet_type,selected FROM bets WHERE outcome IS NULL
        AND kickoff LIKE ?
        ORDER BY selected DESC, confidence_pct DESC LIMIT 40""",(f"{d}%",))]
    # Also include picks scanned today with no kickoff set
    if len(rows) < 40:
        ids_seen = {r["match"] for r in rows}
        extras = [dict(r) for r in c.execute("""SELECT id,sport,match,kickoff,market,pick,odds,
            confidence_pct,plain_rationale,bet_type,selected FROM bets WHERE outcome IS NULL
            AND scan_date=? AND (kickoff IS NULL OR kickoff='')
            ORDER BY selected DESC, confidence_pct DESC LIMIT 40""",(d,))
            if r["match"] not in ids_seen]
        rows += extras[:40-len(rows)]
    c.close()
    if _PR:
        for r in rows:
            try:
                r["plain_pick"] = _PR.plain_pick(r)
            except Exception:
                r["plain_pick"] = r.get("pick", "")
    return rows

def today_settled():
    """Picks settled today — only bets settled on today's date."""
    c = _c(); d = datetime.now().strftime("%Y-%m-%d")
    rows = [dict(r) for r in c.execute("""SELECT sport, match, market, pick, odds,
        confidence_pct, outcome, settled_at, bet_type, notes, result_score
        FROM bets WHERE outcome IN ('win','loss') AND selected=1
        AND settled_at LIKE ?
        ORDER BY settled_at DESC LIMIT 30""",(f"{d}%",))]
    c.close()
    # Add plain_pick for consistent display
    if _PR:
        for r in rows:
            try:
                r["plain_pick"] = _PR.plain_pick(r)
            except Exception:
                r["plain_pick"] = r.get("pick", "")
    return rows

def diary(limit=60):
    c = _c()
    rows = [dict(r) for r in c.execute("""SELECT date,title,body,mood,stats_json,created_at
        FROM diary ORDER BY date DESC LIMIT ?""",(limit,))]
    c.close(); return rows

def continuous_bet_state():
    c = _c()
    r = c.execute("SELECT * FROM continuous_bet_state WHERE id=1").fetchone()
    if not r:
        c.close(); return None
    st = dict(r)
    cf = config()
    target = int(json.loads(cf.get("continuous_bet","{}")).get("compound_days",30) or 30)
    st["cycle_target_days"] = target
    st["cycle_progress_pct"] = round(100 * (st.get("streak_day") or 0) / max(1,target), 1)
    st["activity"] = [dict(x) for x in c.execute("""SELECT scan_date, match, pick, odds, confidence_pct, outcome
        FROM bets WHERE match LIKE '%continuous%' OR notes LIKE '%continuous%'
        ORDER BY id DESC LIMIT 30""")]
    c.close(); return st

def weekly_long_shot_recent(limit=8):
    c = _c()
    rows = [dict(r) for r in c.execute("""SELECT week_of, slip_code, legs, combined_odds,
        stake, status, settled_at, created_at, bookmaker
        FROM weekly_long_shot ORDER BY id DESC LIMIT ?""",(limit,))]
    c.close(); return rows

def recent_insights(limit=5):
    c = _c()
    rows = [dict(r) for r in c.execute("""SELECT generated_at, period_start, period_end,
        total_bets, win_rate, roi, best_sport, worst_sport, best_market, worst_market,
        best_odds_band, worst_odds_band, calibration_notes, recommendations
        FROM sabiai_insights ORDER BY id DESC LIMIT ?""",(limit,))]
    c.close(); return rows

def live_bets(limit=20):
    c = _c()
    try:
        rows = [dict(r) for r in c.execute("""
            SELECT created_at, sport, match, market, pick, odds,
                   confidence_pct, plain_rationale, status, result
            FROM live_bets ORDER BY id DESC LIMIT ?""", (limit,))]
    except Exception:
        rows = []
    c.close()
    if _PR:
        for r in rows:
            try:
                r["plain_pick"] = _PR.plain_pick(r)
            except Exception:
                r["plain_pick"] = r.get("pick", "")
    return rows

def continuous_bet_streak():
    c = _c()
    r = c.execute("SELECT * FROM continuous_bet_state WHERE id=1").fetchone()
    if not r:
        c.close()
        return {"streak_status": "idle", "streak_day": 0, "starting_stake": 1000,
                "current_stake": 1000, "streak_wins": 0, "amount_won": 0}
    d = dict(r)
    start   = d.get("starting_stake") or 1000
    current = d.get("current_stake")  or start
    day     = d.get("streak_day")     or 0
    cycle_start = d.get("started_on")

    # Count wins only from current cycle (after started_on)
    if cycle_start:
        db_wins = c.execute(
            "SELECT COUNT(*) FROM bets WHERE bet_type='compound' AND outcome='win' AND created_at >= ?",
            (cycle_start,)
        ).fetchone()[0]
    else:
        db_wins = c.execute(
            "SELECT COUNT(*) FROM bets WHERE bet_type='compound' AND outcome='win'"
        ).fetchone()[0]
    wins = db_wins if db_wins > 0 else max(0, day - 1)

    # Deduct stake if there's a pending compound bet right now
    pending = c.execute(
        "SELECT COUNT(*) FROM bets WHERE bet_type='compound' AND outcome IS NULL"
    ).fetchone()[0]
    stake_in_play = current if pending else 0.0

    # Compute longest streak and total cycles from all historical compound bets
    all_compound = c.execute(
        "SELECT outcome FROM bets WHERE bet_type='compound' AND outcome IS NOT NULL ORDER BY id ASC"
    ).fetchall()
    longest = 0
    cur_run = 0
    total_cycles = 0
    in_cycle = False
    for row in all_compound:
        oc = row[0]
        if oc == 'win':
            cur_run += 1
            in_cycle = True
        else:
            if in_cycle:
                total_cycles += 1
            if cur_run > longest:
                longest = cur_run
            cur_run = 0
            in_cycle = False
    if in_cycle or cur_run > 0:
        total_cycles += 1
    if cur_run > longest:
        longest = cur_run

    c.close()
    amount_won = current - start
    mult = current / start if start else 1.0
    d["streak_wins"]     = wins
    d["amount_won"]      = amount_won
    d["running_mult"]    = round(mult, 2)
    d["cycle_target_days"]   = 30
    d["cycle_progress_pct"]  = round(100 * day / 30, 1)
    d["stake_in_play"]   = stake_in_play
    d["pending_bet"]     = bool(pending)
    d["longest_streak"]  = longest
    d["total_cycles"]    = total_cycles
    return d

def weekly_long_shot_latest():
    c = _c()
    r = c.execute("""SELECT id, week_of, slip_code, legs, combined_odds, stake, payout,
        status, settled_at, created_at, bookmaker
        FROM weekly_long_shot ORDER BY id DESC LIMIT 1""").fetchone()
    c.close()
    return dict(r) if r else {}

def betchain_history(limit=60):
    c = _c()
    state = c.execute("SELECT starting_stake, started_on FROM continuous_bet_state WHERE id=1").fetchone()
    start = float(state["starting_stake"] if state else 1000) or 1000
    cycle_start = state["started_on"] if state else None
    # Filter to only current cycle bets (after cycle started_on)
    if cycle_start:
        rows = [dict(r) for r in c.execute("""
            SELECT id, scan_date, sport, match, market, pick, odds, confidence_pct,
                   plain_rationale, outcome, settled_at, notes, bet_type, bookmaker, kickoff
            FROM bets
            WHERE (bet_type='compound' OR bet_type='chain'
                   OR notes LIKE '%continuous bet%'
                   OR notes LIKE '%compound chain%')
              AND created_at >= ?
            ORDER BY id ASC LIMIT ?""", (cycle_start, limit))]
    else:
        rows = [dict(r) for r in c.execute("""
            SELECT id, scan_date, sport, match, market, pick, odds, confidence_pct,
                   plain_rationale, outcome, settled_at, notes, bet_type, bookmaker, kickoff
            FROM bets
            WHERE bet_type='compound'
               OR bet_type='chain'
               OR notes LIKE '%continuous bet%'
               OR notes LIKE '%compound chain%'
            ORDER BY id ASC LIMIT ?""", (limit,))]
    stake = start
    for i, r in enumerate(rows):
        r['chain_day'] = i + 1
        r['stake'] = round(stake, 2)
        if r.get('outcome') == 'win' and r.get('odds'):
            stake = round(stake * float(r['odds']), 2)
        elif r.get('outcome') == 'loss':
            stake = start
    if _PR:
        for r in rows:
            try:
                r["plain_pick"] = _PR.plain_pick(r)
            except Exception:
                r["plain_pick"] = r.get("pick", "")
    c.close()
    return list(reversed(rows))

def betchain_today():
    c = _c()
    state = c.execute(
        """SELECT last_pick_id, current_stake, streak_day, last_pick_date,
                  streak_status, restrategy_until FROM continuous_bet_state WHERE id=1"""
    ).fetchone()
    if not state:
        c.close()
        return {"waiting_for_pick": True, "streak_day": 1, "stake": 1000}
    pick_id   = state['last_pick_id']
    stake     = state['current_stake'] or 1000
    day       = state['streak_day'] or 1
    last_date = state['last_pick_date'] or ''
    today     = datetime.now().strftime("%Y-%m-%d")

    # 7-day restrategy break after a loss — page shows the countdown, not a stale pick
    until = state['restrategy_until'] or ''
    if state['streak_status'] == 'restrategy' and until >= today:
        c.close()
        return {"on_break": True, "restrategy_until": until,
                "streak_day": day, "stake": stake, "waiting_for_pick": False}

    if not pick_id:
        c.close()
        return {"waiting_for_pick": True, "streak_day": day, "stake": stake}
    r = c.execute("""SELECT id, sport, match, market, pick, odds, confidence_pct,
        plain_rationale, outcome, kickoff, bet_type, bookmaker
        FROM bets WHERE id=?""", (pick_id,)).fetchone()
    c.close()
    if not r:
        return {"waiting_for_pick": True, "streak_day": day, "stake": stake}
    d = dict(r)
    d['stake'] = stake
    d['chain_day'] = day
    already_settled = d.get('outcome') is not None
    new_day = last_date != today
    d['waiting_for_pick'] = already_settled and new_day
    if _PR:
        try:
            d["plain_pick"] = _PR.plain_pick(d)
        except Exception:
            d["plain_pick"] = d.get("pick", "")
    return d

def longshot_legs(ls_id: int):
    c = _c()
    try:
        ls = c.execute("SELECT id, slip_code FROM weekly_long_shot WHERE id=?", (ls_id,)).fetchone()
        if not ls:
            c.close()
            return []
        legs = [dict(r) for r in c.execute("""
            SELECT al.sport, al.match, al.market, al.pick, al.odds, al.confidence_pct, al.outcome
            FROM accumulator_legs al
            JOIN accumulators a ON al.acc_id = a.id
            WHERE a.slip_code = ?
            ORDER BY al.id""", (ls['slip_code'],)).fetchall()]
        if not legs:
            legs = [dict(r) for r in c.execute("""
                SELECT b.sport, b.match, b.market, b.pick, b.odds, b.confidence_pct, b.outcome
                FROM bets b
                WHERE b.slip_code = ?
                ORDER BY b.id""", (ls['slip_code'],)).fetchall()]
    except Exception:
        legs = []
    if _PR:
        for leg in legs:
            try:
                leg["plain_pick"] = _PR.plain_pick(leg)
            except Exception:
                leg["plain_pick"] = leg.get("pick", "")
    c.close()
    return legs


# ── Analytics: CLV, calibration, bookmaker P/L ────────────────────────────────

def clv_stats():
    """Closing-line value: are our entry odds beating the close? The cleanest
    long-run edge signal, independent of short-term win/loss variance."""
    c = _c()
    rows = [dict(r) for r in c.execute("""
        SELECT scan_date, week, match, pick, odds, closing_odds, clv, outcome
        FROM bets WHERE clv IS NOT NULL ORDER BY scan_date, id""").fetchall()]
    c.close()
    if not rows:
        return {"n": 0, "avg_clv": None, "pct_beat_close": None, "by_week": [], "recent": []}
    clvs = [r["clv"] for r in rows]
    beat = sum(1 for v in clvs if v > 0)
    by_week = {}
    for r in rows:
        wk = r["week"] or "?"
        by_week.setdefault(wk, []).append(r["clv"])
    return {
        "n": len(rows),
        "avg_clv": round(sum(clvs) / len(clvs), 2),
        "pct_beat_close": round(100 * beat / len(rows), 1),
        "by_week": [{"week": k, "avg_clv": round(sum(v)/len(v), 2), "n": len(v)}
                    for k, v in sorted(by_week.items())],
        "recent": rows[-15:],
    }


def calibration_curve():
    """Predicted confidence vs actual win rate, in 10-point buckets.
    A well-calibrated model sits on the diagonal."""
    c = _c()
    rows = c.execute("""
        SELECT confidence_pct, outcome FROM bets
        WHERE outcome IN ('win','loss') AND confidence_pct IS NOT NULL""").fetchall()
    c.close()
    buckets = {}
    for r in rows:
        b = int(r["confidence_pct"] // 10) * 10
        buckets.setdefault(b, {"n": 0, "w": 0, "conf_sum": 0.0})
        buckets[b]["n"] += 1
        buckets[b]["w"] += 1 if r["outcome"] == "win" else 0
        buckets[b]["conf_sum"] += r["confidence_pct"]
    out = []
    for b in sorted(buckets):
        d = buckets[b]
        out.append({
            "bucket": f"{b}-{b+9}%",
            "n": d["n"],
            "predicted": round(d["conf_sum"] / d["n"], 1),
            "actual": round(100 * d["w"] / d["n"], 1),
            "gap": round(100 * d["w"] / d["n"] - d["conf_sum"] / d["n"], 1),
        })
    return out


def bookmaker_pl():
    """Realised P/L per bet channel, straight from the bankroll ledger."""
    c = _c()
    rows = c.execute("""
        SELECT kind, COUNT(*) n, ROUND(SUM(delta),2) pl, ROUND(SUM(stake),2) staked
        FROM bankroll WHERE delta IS NOT NULL GROUP BY kind""").fetchall()
    c.close()
    label = {"chain_win": "Chain (SportyBet)", "chain_loss": "Chain (SportyBet)",
             "acc_win": "Kelly/Acc (1xBet)", "acc_loss": "Kelly/Acc (1xBet)",
             "longshot_win": "Long shot (Bet9ja)", "longshot_loss": "Long shot (Bet9ja)"}
    agg = {}
    for r in rows:
        ch = label.get(r["kind"], r["kind"] or "other")
        a = agg.setdefault(ch, {"channel": ch, "n": 0, "pl": 0.0, "staked": 0.0})
        a["n"] += r["n"]; a["pl"] += r["pl"] or 0; a["staked"] += r["staked"] or 0
    out = list(agg.values())
    for a in out:
        a["pl"] = round(a["pl"], 2)
        a["roi_pct"] = round(100 * a["pl"] / a["staked"], 1) if a["staked"] else None
    return sorted(out, key=lambda x: x["pl"])
