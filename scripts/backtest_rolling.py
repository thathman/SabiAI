#!/usr/bin/env python3
"""backtest_rolling.py — rolling-origin (walk-forward) backtest of the Dixon-Coles
engine against the bookmaker market, on football-data.co.uk history.

This is the GO-LIVE GATE for dixon_coles.py. The existing backtest.py measures
settled *live* bets after the fact; this one re-runs history honestly:

  - expanding training window, refit every `--retrain-days`
  - predict only matches strictly AFTER the training cutoff (no leakage)
  - devig market odds -> fair market probability (the baseline to beat)
  - bet flat 1u when model EV = p_model * odds - 1 >= --min-ev
  - settle on the real result; report ROI, yield, hit-rate, bet count
  - Brier(model) vs Brier(market) — is the model better CALIBRATED than the book?

Markets: 1X2 (H/D/A) and Over/Under 2.5. Pure numpy + scipy via dixon_coles.

Usage:
  python3 backtest_rolling.py --league E0 --seasons 5 --min-ev 0.05
  python3 backtest_rolling.py --league SP1 --seasons 6 --half-life 150 --json
"""
from __future__ import annotations
import argparse, json
from datetime import timedelta

import numpy as np

import dixon_coles as dc


# ── market odds helpers (column-name variants across FDCO eras) ──────────────

def _f(row, *keys):
    for k in keys:
        v = row.get(k)
        if v not in (None, ""):
            try:
                return float(v)
            except (ValueError, TypeError):
                pass
    return None


def market_1x2(row, mode="max"):
    """Decimal odds for home/draw/away.
    mode='max' = best price across books (mirrors the live finder's best_price,
    strips most/all overround — the real edge source). mode='avg' = consensus."""
    if mode == "max":
        h = _f(row, "MaxH", "BbMxH"); d = _f(row, "MaxD", "BbMxD"); a = _f(row, "MaxA", "BbMxA")
        if h and d and a:
            return {"home": h, "draw": d, "away": a}
    h = _f(row, "AvgH", "BbAvH", "B365H")
    d = _f(row, "AvgD", "BbAvD", "B365D")
    a = _f(row, "AvgA", "BbAvA", "B365A")
    if h and d and a:
        return {"home": h, "draw": d, "away": a}
    return None


def market_ou25(row, mode="max"):
    if mode == "max":
        o = _f(row, "Max>2.5", "BbMx>2.5"); u = _f(row, "Max<2.5", "BbMx<2.5")
        if o and u:
            return {"over": o, "under": u}
    o = _f(row, "Avg>2.5", "BbAv>2.5", "B365>2.5", "P>2.5")
    u = _f(row, "Avg<2.5", "BbAv<2.5", "B365<2.5", "P<2.5")
    if o and u:
        return {"over": o, "under": u}
    return None


def market_consensus_1x2(row):
    """Always the consensus (avg) — used to devig for the no-vig fair baseline,
    independent of the price we actually bet at."""
    h = _f(row, "AvgH", "BbAvH", "B365H")
    d = _f(row, "AvgD", "BbAvD", "B365D")
    a = _f(row, "AvgA", "BbAvA", "B365A")
    return {"home": h, "draw": d, "away": a} if (h and d and a) else None


def market_consensus_ou25(row):
    o = _f(row, "Avg>2.5", "BbAv>2.5", "B365>2.5", "P>2.5")
    u = _f(row, "Avg<2.5", "BbAv<2.5", "B365<2.5", "P<2.5")
    return {"over": o, "under": u} if (o and u) else None


def devig(odds_dict):
    """{name: decimal odds} -> {name: no-vig fair prob}."""
    raw = {k: 1.0 / v for k, v in odds_dict.items()}
    s = sum(raw.values())
    return {k: v / s for k, v in raw.items()} if s > 0 else None


# ── settlement ──────────────────────────────────────────────────────────────

def result_1x2(hg, ag):
    return "home" if hg > ag else ("away" if ag > hg else "draw")


def result_ou25(hg, ag):
    return "over" if hg + ag > 2.5 else "under"


# ── backtest ────────────────────────────────────────────────────────────────

def run(matches, half_life, min_ev, retrain_days, min_train_frac, max_goals,
        odds_mode="max", blend_w=1.0, agree=False):
    matches = [m for m in matches if m.get("date")]
    matches.sort(key=lambda m: m["date"])
    if len(matches) < 200:
        raise ValueError(f"too few dated matches to backtest ({len(matches)})")

    # raw rows carry the odds; keep them aligned with parsed matches via index
    n = len(matches)
    start_i = int(n * min_train_frac)
    cutoff_date = matches[start_i]["date"]

    model = None
    next_refit = None
    bets = []          # each: {market, ev, odds, won, p_model, p_market}
    brier_model = []   # (p_model_of_actual, market) tuples per graded outcome
    brier_mkt = []

    fitted_until = None
    for i in range(start_i, n):
        m = matches[i]
        d = m["date"]
        # (re)fit on everything strictly before this match's date
        if model is None or next_refit is None or d >= next_refit:
            train = [x for x in matches[:i] if x["date"] and x["date"] < d]
            try:
                model = dc.DixonColes(max_goals=max_goals)
                model.fit(train, ref_date=d, half_life_days=half_life)
                fitted_until = d
                next_refit = d + timedelta(days=retrain_days)
            except ValueError:
                continue

        row = m.get("_row", {})
        hg, ag = m["hg"], m["ag"]
        pred = model.predict(m["home"], m["away"])
        if not pred:
            continue  # team unseen in training window

        # ---- 1X2 ----
        mk = market_1x2(row, odds_mode)            # price we'd actually bet at
        cons = market_consensus_1x2(row)           # consensus for the no-vig fair
        if mk and cons:
            fair = devig(cons)
            actual = result_1x2(hg, ag)
            # calibration on the BLENDED prob actually used (fair comparison vs market)
            blended = {s: blend_w * pred["1x2"][s] + (1.0 - blend_w) * fair[s]
                       for s in ("home", "draw", "away")}
            brier_model.append((1.0, blended[actual]))
            brier_mkt.append((1.0, fair[actual]))
            for side in ("home", "draw", "away"):
                p_dc = pred["1x2"][side]
                p = blended[side]   # shrink toward market
                odds = mk[side]
                ev = p * odds - 1.0
                # agreement filter: only fade the book when DC also leans this side
                if agree and p_dc <= fair[side]:
                    continue
                if ev >= min_ev:
                    bets.append({
                        "market": "1X2", "pick": side, "ev": ev, "odds": odds,
                        "won": side == actual, "p_model": p, "p_market": fair[side],
                    })

        # ---- O/U 2.5 ----
        mou = market_ou25(row, odds_mode)
        cou = market_consensus_ou25(row)
        if mou and cou:
            fair = devig(cou)
            actual = result_ou25(hg, ag)
            pm = pred["over_under"]["2.5"]
            blended = {s: blend_w * pm[s] + (1.0 - blend_w) * fair[s]
                       for s in ("over", "under")}
            brier_model.append((1.0, blended[actual]))
            brier_mkt.append((1.0, fair[actual]))
            for side in ("over", "under"):
                p_dc = pm[side]
                p = blended[side]
                odds = mou[side]
                ev = p * odds - 1.0
                if agree and p_dc <= fair[side]:
                    continue
                if ev >= min_ev:
                    bets.append({
                        "market": "O/U2.5", "pick": side, "ev": ev, "odds": odds,
                        "won": side == actual, "p_model": p, "p_market": fair[side],
                    })

    return _report(bets, brier_model, brier_mkt, len(matches) - start_i, cutoff_date)


def _brier(pairs):
    # pairs are (actual=1, p_of_actual). Brier on the multiclass-by-outcome basis:
    # we stored prob assigned to the realised outcome; (1-p)^2 is its contribution.
    if not pairs:
        return None
    return float(np.mean([(1.0 - p) ** 2 for _a, p in pairs]))


def _report(bets, bm, bk, n_test, cutoff):
    by_market = {}
    for b in bets:
        by_market.setdefault(b["market"], []).append(b)

    def block(bl):
        if not bl:
            return {"n": 0}
        staked = len(bl)
        rets = np.array([(b["odds"] - 1.0) if b["won"] else -1.0 for b in bl])
        pnl = float(rets.sum())
        wins = int((rets > 0).sum())
        sd = float(rets.std())
        sharpe = round(float(rets.mean() / sd), 3) if sd > 0 else None
        return {
            "n": staked, "wins": wins, "hit_rate": round(wins / staked, 4),
            "pnl_units": round(pnl, 2), "roi_pct": round(100 * pnl / staked, 2),
            "sharpe": sharpe,
            "avg_odds": round(float(np.mean([b["odds"] for b in bl])), 3),
            "avg_ev_pct": round(100 * float(np.mean([b["ev"] for b in bl])), 2),
        }

    return {
        "test_matches": n_test,
        "test_start": cutoff.date().isoformat() if cutoff else None,
        "overall": block(bets),
        "by_market": {k: block(v) for k, v in by_market.items()},
        "calibration": {
            "brier_model": _brier(bm), "brier_market": _brier(bk),
            "model_better": (_brier(bm) is not None and _brier(bk) is not None
                             and _brier(bm) < _brier(bk)),
            "graded_outcomes": len(bm),
        },
    }


def _attach_rows(league_code, seasons):
    """Reload with raw rows attached so we keep the odds columns."""
    matches = []
    for code in dc._season_codes(seasons):
        rows = dc._fetch_csv(f"{dc.FDCO_BASE}/{code}/{league_code}.csv")
        for r in rows:
            parsed = dc.parse_matches([r])
            if parsed:
                p = parsed[0]; p["_row"] = r
                matches.append(p)
    return matches


def main():
    ap = argparse.ArgumentParser(description="Walk-forward backtest of Dixon-Coles vs market.")
    ap.add_argument("--league", default="E0")
    ap.add_argument("--seasons", type=int, default=5)
    ap.add_argument("--half-life", type=float, default=dc.DEFAULT_HALF_LIFE)
    ap.add_argument("--min-ev", type=float, default=0.05, help="min model EV to place a bet")
    ap.add_argument("--retrain-days", type=int, default=14)
    ap.add_argument("--min-train-frac", type=float, default=0.4,
                    help="fraction of history reserved as initial training")
    ap.add_argument("--max-goals", type=int, default=dc.MAX_GOALS)
    ap.add_argument("--odds", choices=("max", "avg"), default="max",
                    help="max = best price across books (live behaviour); avg = consensus")
    ap.add_argument("--blend-w", type=float, default=1.0,
                    help="DC weight in p = w*DC + (1-w)*market_novig (1.0 = pure DC)")
    ap.add_argument("--agree", action="store_true",
                    help="only bet a side when DC also leans it vs the no-vig market")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    matches = _attach_rows(args.league, args.seasons)
    rep = run(matches, args.half_life, args.min_ev, args.retrain_days,
              args.min_train_frac, args.max_goals,
              odds_mode=args.odds, blend_w=args.blend_w, agree=args.agree)
    rep["league"] = args.league
    rep["params"] = {"seasons": args.seasons, "half_life": args.half_life,
                     "min_ev": args.min_ev, "retrain_days": args.retrain_days,
                     "odds": args.odds, "blend_w": args.blend_w, "agree": args.agree}

    if args.json:
        print(json.dumps(rep, indent=2)); return

    o = rep["overall"]
    print(f"\n=== Dixon-Coles walk-forward backtest: {args.league} "
          f"({args.seasons} seasons, half-life {args.half_life:.0f}d, min-EV {args.min_ev:.0%}, "
          f"odds={args.odds}, blend_w={args.blend_w}, agree={args.agree}) ===")
    print(f"Test window from {rep['test_start']} · {rep['test_matches']} matches")
    if not o.get("n"):
        print("No bets cleared the EV threshold."); return
    print(f"\nOVERALL: {o['n']} bets · hit {o['hit_rate']:.1%} · "
          f"ROI {o['roi_pct']:+.2f}% · {o['pnl_units']:+.1f}u · "
          f"Sharpe {o['sharpe']} · avg odds {o['avg_odds']} · avg EV {o['avg_ev_pct']:+.1f}%")
    for mk, b in rep["by_market"].items():
        if b.get("n"):
            print(f"  {mk:8s}: {b['n']:4d} bets · hit {b['hit_rate']:.1%} · "
                  f"ROI {b['roi_pct']:+.2f}% · {b['pnl_units']:+.1f}u")
    c = rep["calibration"]
    if c["brier_model"] is not None:
        verdict = "MODEL better calibrated ✓" if c["model_better"] else "market better calibrated ✗"
        print(f"\nCalibration (Brier, lower=better): model {c['brier_model']:.4f} "
              f"vs market {c['brier_market']:.4f}  -> {verdict}")
        print(f"  ({c['graded_outcomes']} graded outcomes)")


if __name__ == "__main__":
    main()
