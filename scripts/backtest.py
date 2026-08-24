#!/usr/bin/env python3
"""backtest.py — measure how good the predictor actually is.

Reads settled picks from bets.db and reports, in plain language plus dev metrics:
  - real win rate vs the confidence we claimed
  - Brier score & log-loss (calibration quality; lower = better)
  - calibration table (does "70%" really win ~70%?) -> stored in `calibration`
  - Closing Line Value (CLV) where closing odds were captured (the sharpest edge signal)
Usage:
  python3 backtest.py                 # overall + per sport
  python3 backtest.py --sport soccer  # filter
  python3 backtest.py --json          # machine-readable
"""
import argparse, json, math, sqlite3
from datetime import datetime, timezone

DB = "~.openclaw/workspace/data/bets.db"

def _rows(sport=None):
    con = sqlite3.connect(DB); con.row_factory = sqlite3.Row
    q = ("SELECT sport,market,pick,odds,our_prob,confidence_pct,outcome,"
         "closing_odds,clv FROM bets WHERE outcome IN ('win','loss')")
    a = []
    if sport:
        q += " AND lower(sport) LIKE ?"; a.append(f"%{sport.lower()}%")
    rows = con.execute(q, a).fetchall(); con.close()
    return rows

def _p(r):
    v = r["confidence_pct"] if r["confidence_pct"] is not None else r["our_prob"]
    return (v / 100.0) if isinstance(v, (int, float)) else None

def metrics(rows):
    n = won = 0
    brier = ll = 0.0; usable = 0
    clvs = []
    for r in rows:
        n += 1
        actual = 1 if r["outcome"] == "win" else 0
        won += actual
        p = _p(r)
        if p is not None:
            p = min(max(p, 0.001), 0.999)
            brier += (p - actual) ** 2
            ll    += -(actual * math.log(p) + (1 - actual) * math.log(1 - p))
            usable += 1
        if r["clv"] is not None:
            clvs.append(r["clv"])
    return {
        "n": n,
        "win_rate": round(100 * won / n, 1) if n else None,
        "brier": round(brier / usable, 4) if usable else None,
        "log_loss": round(ll / usable, 4) if usable else None,
        "avg_clv_pct": round(sum(clvs) / len(clvs), 2) if clvs else None,
        "clv_n": len(clvs),
    }

def calibration(rows, persist=True):
    buckets = {}
    for r in rows:
        p = _p(r)
        if p is None: continue
        lo = int(p * 10) * 10
        key = f"{lo}-{lo+10}"
        b = buckets.setdefault(key, {"n": 0, "won": 0, "psum": 0.0})
        b["n"] += 1; b["won"] += 1 if r["outcome"] == "win" else 0; b["psum"] += p
    out = []
    for key in sorted(buckets):
        b = buckets[key]
        out.append({
            "bucket": key, "n": b["n"],
            "predicted": round(100 * b["psum"] / b["n"], 1),
            "actual": round(100 * b["won"] / b["n"], 1),
        })
    if persist and out:
        con = sqlite3.connect(DB)
        now = datetime.now(timezone.utc).isoformat()
        for o in out:
            con.execute("INSERT INTO calibration(computed_at,sport,market,bucket,n,predicted,actual)"
                        " VALUES(?,?,?,?,?,?,?)",
                        (now, "ALL", "ALL", o["bucket"], o["n"], o["predicted"], o["actual"]))
        con.commit(); con.close()
    return out

def plain_summary(m, cal):
    L = []
    if not m["n"]:
        return "No settled picks yet — once results come in, accuracy will show here."
    L.append(f"Settled picks: {m['n']}. Actual win rate: {m['win_rate']}%.")
    if m["brier"] is not None:
        quality = ("excellent" if m["brier"] < 0.18 else
                   "good" if m["brier"] < 0.22 else
                   "fair" if m["brier"] < 0.25 else "weak")
        L.append(f"Forecast quality: {quality} (calibration score {m['brier']}, lower is better).")
    if m["avg_clv_pct"] is not None:
        verdict = "beating the closing price (genuine edge)" if m["avg_clv_pct"] > 0 else "behind the closing price"
        L.append(f"On {m['clv_n']} picks we are {verdict}: average {m['avg_clv_pct']:+.2f}%.")
    # calibration honesty
    off = [c for c in cal if abs(c["predicted"] - c["actual"]) > 12 and c["n"] >= 5]
    if off:
        worst = max(off, key=lambda c: abs(c["predicted"] - c["actual"]))
        L.append(f"Note: when we say ~{worst['predicted']}% it actually hits {worst['actual']}% "
                 f"({worst['n']} picks) — confidence is being recalibrated.")
    return " ".join(L)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sport", default=None)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--no-persist", action="store_true")
    a = ap.parse_args()
    rows = _rows(a.sport)
    m = metrics(rows)
    cal = calibration(rows, persist=not a.no_persist)
    if a.json:
        print(json.dumps({"metrics": m, "calibration": cal}, indent=2)); return
    print("=== Predictor accuracy ===")
    print(plain_summary(m, cal))
    print()
    if cal:
        print("Calibration (claimed % vs real %):")
        for c in cal:
            print(f"  {c['bucket']:>7}  predicted {c['predicted']:>5}%  actual {c['actual']:>5}%  (n={c['n']})")
    print()
    print(f"[dev] win_rate={m['win_rate']} brier={m['brier']} log_loss={m['log_loss']} "
          f"avg_clv={m['avg_clv_pct']} (n={m['n']}, clv_n={m['clv_n']})")

if __name__ == "__main__":
    main()
