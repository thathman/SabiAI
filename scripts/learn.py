#!/usr/bin/env python3
"""learn.py — SabiAI's learning loop (the part that makes picks evolve from use).

The chain:
  1. value_bet_finder.py logs picks to bets.db.
  2. settle / auto-settle marks each pick won/lost from real results.
  3. sabiai_analyze.py reads settled bets and calls write_adjustments() here —
     turning "what actually happened" into per-category corrections.
  4. value_bet_finder.py calls apply() on every fresh pick, so today's picks are
     shaped by everything we've learned so far.

One table: learned_adjustments. Most-specific scope wins (sport_market > sport > market).

  scope     'sport' | 'market' | 'sport_market'
  key       e.g. 'Soccer', 'Total Goals', 'Soccer|Total Goals'
  confidence_multiplier   recalibration factor for shown confidence (clamped)
  status    'active' | 'boost' | 'caution' | 'avoid'
            avoid → stop surfacing this category until it recovers.
"""
import sqlite3
from datetime import datetime, timezone

DB = "~.openclaw/workspace/data/bets.db"

MULT_FLOOR, MULT_CEIL = 0.60, 1.15     # never swing confidence more than this
MIN_N_ADJUST = 8                        # samples before we trust a calibration nudge
MIN_N_AVOID = 15                        # samples before we'll bench a category
AVOID_ROI = -0.15                       # ROI below this (with enough n) → bench it
BOOST_ROI = 0.10                        # ROI above this + well-calibrated → boost


def _conn():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    c.execute("""CREATE TABLE IF NOT EXISTS learned_adjustments(
        scope TEXT, key TEXT,
        confidence_multiplier REAL DEFAULT 1.0,
        status TEXT DEFAULT 'active',
        sample_size INTEGER DEFAULT 0,
        win_rate REAL, roi REAL,
        note TEXT, updated_at TEXT,
        PRIMARY KEY(scope, key))""")
    return c


def _clamp(x, lo, hi):
    return max(lo, min(hi, x))


def norm_key(s):
    """Canonical category key: strip emoji/symbol prefixes, lowercase.
    '⚾ MLB', 'MLB' and 'mlb' must all learn into the same bucket."""
    s = (s or "").strip()
    while s and not (s[0].isalnum()):
        s = s[1:].lstrip()
    return s.lower()


# ---------- read side (used by value_bet_finder) ----------
def get_adjustments():
    """Return {(scope,key): row-dict}. Cheap; safe to call once per scan."""
    c = _conn()
    out = {}
    for r in c.execute("SELECT * FROM learned_adjustments"):
        out[(r["scope"], norm_key(r["key"]))] = dict(r)
    c.close()
    return out


def _lookup(adj, sport, market):
    sport = norm_key(sport)
    market = norm_key(market)
    for scope, key in (("sport_market", f"{sport}|{market}"),
                       ("sport", sport),
                       ("market", market)):
        row = adj.get((scope, key))
        if row:
            return row
    return None


def apply(bet, adj=None):
    """Mutate a pick dict in place with what we've learned.
    - sets bet['confidence_override'] = recalibrated confidence (plain_render reads it)
    - sets bet['_learn_status']
    Returns False if the pick should be DROPPED (benched category), else True.
    """
    if adj is None:
        adj = get_adjustments()
    row = _lookup(adj, bet.get("sport"), bet.get("market"))
    if not row:
        return True
    if row["status"] == "avoid":
        bet["_learn_status"] = "avoid"
        return False
    raw = bet.get("our_prob")
    if isinstance(raw, (int, float)):
        adjusted = _clamp(raw * (row["confidence_multiplier"] or 1.0), 1.0, 99.0)
        bet["confidence_override"] = adjusted
    bet["_learn_status"] = row["status"]
    return True


# ---------- write side (used by sabiai_analyze) ----------
def _status_for(mult, roi, n):
    if n >= MIN_N_AVOID and roi is not None and roi < AVOID_ROI:
        return "avoid"
    if n >= MIN_N_AVOID and roi is not None and roi > BOOST_ROI and mult >= 0.95:
        return "boost"
    if mult < 0.90:
        return "caution"
    return "active"


def _upsert(c, scope, key, mult, status, n, wr, roi, note):
    c.execute("""INSERT INTO learned_adjustments
        (scope,key,confidence_multiplier,status,sample_size,win_rate,roi,note,updated_at)
        VALUES (?,?,?,?,?,?,?,?,?)
        ON CONFLICT(scope,key) DO UPDATE SET
          confidence_multiplier=excluded.confidence_multiplier,
          status=excluded.status, sample_size=excluded.sample_size,
          win_rate=excluded.win_rate, roi=excluded.roi,
          note=excluded.note, updated_at=excluded.updated_at""",
        (scope, key, mult, status, n, wr, roi, note,
         datetime.now(timezone.utc).isoformat()))


def write_adjustments(by_sport, by_market):
    """Given sabiai_analyze's per-category tallies, learn corrections.

    Each tally dict: {key: {w,l,profit,stake, predicted_sum, ...}}. We recalibrate
    shown confidence toward reality: multiplier = actual_win_rate / predicted_avg.
    """
    c = _conn()
    written = []
    for scope, tally in (("sport", by_sport), ("market", by_market)):
        for key, v in tally.items():
            n = v.get("w", 0) + v.get("l", 0)
            if n < MIN_N_ADJUST:
                continue
            wr = v["w"] / n
            roi = v.get("profit", 0.0) / max(1.0, v.get("stake", 0.0))
            pred_avg = (v.get("predicted_sum", 0.0) / n) if v.get("predicted_sum") else None
            if pred_avg and pred_avg > 0:
                mult = _clamp(wr / pred_avg, MULT_FLOOR, MULT_CEIL)
            else:
                mult = 1.0
            status = _status_for(mult, roi, n)
            note = (f"n={n}, win {wr:.0%}, roi {roi:+.0%}"
                    + (f", predicted {pred_avg:.0%}→{wr:.0%}" if pred_avg else ""))
            _upsert(c, scope, key, round(mult, 3), status, n, round(wr, 3),
                    round(roi, 3), note)
            written.append({"scope": scope, "key": key, "multiplier": round(mult, 3),
                            "status": status, "n": n})
    c.commit()
    c.close()
    return written


def summary():
    """Human-readable current state of what SabiAI has learned."""
    c = _conn()
    rows = [dict(r) for r in c.execute(
        "SELECT * FROM learned_adjustments ORDER BY scope, key")]
    c.close()
    return rows


if __name__ == "__main__":
    import json, sys
    if len(sys.argv) > 1 and sys.argv[1] == "show":
        rows = summary()
        if not rows:
            print("Nothing learned yet — no settled bets have been analysed.")
        for r in rows:
            print(f"[{r['status']:>7}] {r['scope']}/{r['key']}: "
                  f"x{r['confidence_multiplier']} ({r['note']})")
    else:
        print(json.dumps(summary(), indent=2))
