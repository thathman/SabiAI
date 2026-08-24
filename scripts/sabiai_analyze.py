#!/usr/bin/env python3
"""
sabiai_analyze.py — SabiAI self-improving analysis.

Runs weekly (and on restrategy). Analyzes settled bets to find:
  - Win rate by sport, market, odds band, confidence bucket
  - ROI by sport, market
  - Confidence calibration (predicted vs actual)
  - Best/worst categories
  - Recommendations for the next cycle

Writes a summary to sabiai_insights table. Triggers a restrategy
recommendation if losses are clustering in a specific area.
"""
import argparse, json, os, sqlite3, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import learn
from collections import defaultdict
from datetime import datetime, timezone, timedelta

DB = "/home/hendrix/.openclaw/workspace/data/bets.db"


def analyze(period_days=30):
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    since = (datetime.now(timezone.utc) - timedelta(days=period_days)).isoformat()
    rows = c.execute(
        "SELECT * FROM bets WHERE settled_at >= ? AND outcome IN ('win','loss')",
        (since,),
    ).fetchall()
    if not rows:
        return {"empty": True, "message": "no settled bets in window", "period_days": period_days}

    by_sport = defaultdict(lambda: {"w": 0, "l": 0, "profit": 0.0, "stake": 0.0, "predicted_sum": 0.0})
    by_market = defaultdict(lambda: {"w": 0, "l": 0, "profit": 0.0, "stake": 0.0, "predicted_sum": 0.0})
    by_odds = defaultdict(lambda: {"w": 0, "l": 0, "profit": 0.0, "stake": 0.0})
    calib = defaultdict(lambda: {"predicted": 0.0, "actual_w": 0, "n": 0})

    total_w = total_l = total_profit = total_stake = 0
    for r in rows:
        sport = learn.norm_key(r["sport"]) or "unknown"
        market = learn.norm_key(r["market"]) or "unknown"
        odds = float(r["odds"] or 0)
        # Stake/profit aren't on the bet row directly — use CLV + a synthetic stake
        # of 1000 NGN per pick as a relative scale for ROI ranking. Real stake
        # is logged in bankroll table; cross-reference if absolute P&L is needed.
        stake = 1000.0
        if r["outcome"] == "win":
            profit = stake * (odds - 1.0)
        elif r["outcome"] == "loss":
            profit = -stake
        else:
            continue
        conf = float(r["confidence_pct"] or 0) / 100.0
        won = r["outcome"] == "win"
        bucket = f"{odds:.2f}"
        for d, key in ((by_sport, sport), (by_market, market)):
            d[key]["w" if won else "l"] += 1
            d[key]["profit"] += profit
            d[key]["stake"] += stake
            d[key]["predicted_sum"] += conf
        by_odds[bucket]["w" if won else "l"] += 1
        by_odds[bucket]["profit"] += profit
        by_odds[bucket]["stake"] += stake
        if conf:
            cb = f"{int(conf*100)//10}0s"
            calib[cb]["predicted"] += conf
            calib[cb]["actual_w"] += 1 if won else 0
            calib[cb]["n"] += 1
        total_w += 1 if won else 0
        total_l += 1 if not won else 0
        total_profit += profit
        total_stake += stake

    def rank(d, key="roi"):
        out = []
        for k, v in d.items():
            wr = v["w"] / max(1, v["w"] + v["l"])
            roi = v["profit"] / max(1.0, v["stake"])
            out.append({"key": k, "win_rate": wr, "roi": roi, **v})
        return sorted(out, key=lambda x: x.get(key, 0), reverse=True)

    sport_rank = rank(by_sport)
    market_rank = rank(by_market)
    odds_rank = rank(by_odds)
    calib_out = {
        k: {"predicted_avg": v["predicted"] / max(1, v["n"]),
            "actual_win_rate": v["actual_w"] / max(1, v["n"]),
            "n": v["n"]}
        for k, v in calib.items() if v["n"] >= 5
    }
    summary = {
        "period_days": period_days,
        "total_bets": len(rows),
        "wins": total_w, "losses": total_l,
        "win_rate": total_w / max(1, len(rows)),
        "profit": total_profit, "stake": total_stake,
        "roi": total_profit / max(1.0, total_stake),
        "best_sport": sport_rank[0]["key"] if sport_rank else None,
        "worst_sport": sport_rank[-1]["key"] if sport_rank else None,
        "best_market": market_rank[0]["key"] if market_rank else None,
        "worst_market": market_rank[-1]["key"] if market_rank else None,
        "best_odds_band": odds_rank[0]["key"] if odds_rank else None,
        "worst_odds_band": odds_rank[-1]["key"] if odds_rank else None,
        "calibration": calib_out,
        "by_sport_top5": sport_rank[:5],
        "by_sport_bottom5": sport_rank[-5:],
        "by_market_top5": market_rank[:5],
        "_by_sport": dict(by_sport),
        "_by_market": dict(by_market),
    }
    return summary


def save_insight(summary):
    if summary.get("empty"):
        return None
    c = sqlite3.connect(DB)
    now = datetime.now(timezone.utc).isoformat()
    period_end = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    period_start = (datetime.now(timezone.utc) - timedelta(days=summary["period_days"])).strftime("%Y-%m-%d")
    c.execute("""INSERT INTO sabiai_insights
      (generated_at, period_start, period_end, total_bets, win_rate, roi,
       best_sport, worst_sport, best_market, worst_market,
       best_odds_band, worst_odds_band, calibration_notes, recommendations, raw_json)
      VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
      (now, period_start, period_end, summary["total_bets"], summary["win_rate"],
       summary["roi"], summary["best_sport"], summary["worst_sport"],
       summary["best_market"], summary["worst_market"],
       summary["best_odds_band"], summary["worst_odds_band"],
       json.dumps(summary.get("calibration", {})),
       _recommendations(summary), json.dumps(summary)))
    c.commit()
    c.close()
    return summary


def _recommendations(s):
    recs = []
    if s["win_rate"] < 0.45:
        recs.append("Overall win rate below 45% — review pick quality threshold.")
    if s["best_sport"] and s["worst_sport"] and s["best_sport"] != s["worst_sport"]:
        recs.append(f"Lean into {s['best_sport']}, reduce exposure to {s['worst_sport']}.")
    for bucket, c in s.get("calibration", {}).items():
        if c["n"] >= 10 and abs(c["predicted_avg"] - c["actual_win_rate"]) > 0.10:
            direction = "overconfident" if c["predicted_avg"] > c["actual_win_rate"] else "underconfident"
            recs.append(f"Model is {direction} in {bucket} bucket: predicted {c['predicted_avg']:.0%}, actual {c['actual_win_rate']:.0%}.")
    if s["roi"] < -0.10:
        recs.append("ROI below -10% — consider tighter minimum EV or pause.")
    return "\n".join(recs) if recs else "No adjustments recommended."


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    s = analyze(args.days)
    if s.get("empty"):
        if not args.quiet:
            print(s["message"])
        return
    saved = save_insight(s)
    # Close the loop: turn this analysis into corrections future scans will apply.
    learned = learn.write_adjustments(s.get("_by_sport", {}), s.get("_by_market", {}))
    if not args.quiet:
        print(json.dumps({
            "period": f"{saved.get('total_bets',0)} bets over {args.days} days",
            "win_rate": f"{saved['win_rate']:.1%}",
            "roi": f"{saved['roi']:.1%}",
            "best_sport": saved["best_sport"],
            "worst_sport": saved["worst_sport"],
            "recommendations": _recommendations(saved),
            "learned_adjustments": learned,
        }, indent=2))


if __name__ == "__main__":
    main()
