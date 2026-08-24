#!/usr/bin/env python3
"""
Fast backtest: fit on N-1 seasons, predict on the latest season.
One fit per league, not per match.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data_pipeline import DataPipeline, LEAGUES
from dixon_coles import DixonColesModel
from value_engine import ValueEngine

DB_PATH = os.path.expanduser("~/.openclaw/workspace-sabi-ai/data/sabiai_v2.db")
pipeline = DataPipeline(DB_PATH)

def fast_backtest(league, verbose=False):
    ve = ValueEngine(min_ev=0.03)

    # Get all matches
    all_matches = []
    for i in range(4):
        year = 2026 - i
        season = f"{year}-{year+1}"
        rows = pipeline.get_matches(league=league, season=season)
        for r in rows:
            if r.get('hg') is not None and r.get('ag') is not None:
                all_matches.append({
                    'home': r['home'], 'away': r['away'],
                    'home_goals': r['hg'], 'away_goals': r['ag'],
                    'date': r['date'],
                    'odds_h': r.get('odds_h'), 'odds_d': r.get('odds_d'), 'odds_a': r.get('odds_a'),
                })

    all_matches.sort(key=lambda x: x['date'])

    # Split: train on first 2 seasons, test on last 2
    split_idx = len(all_matches) // 2
    train = all_matches[:split_idx]
    test = all_matches[split_idx:]

    # Fit model ONCE on training data
    model = DixonColesModel()
    model.fit(train, time_decay_half_life=300)

    print(f"\n{'='*55}")
    print(f"  FAST BACKTEST: {LEAGUES.get(league, league)} ({league})")
    print(f"{'='*55}")
    print(f"  Training: {len(train)} matches | Testing: {len(test)} matches")
    print(f"  Model params: alpha={model.params.get('home_adv',0):.3f} rho={model.params.get('rho',0):.3f}")

    # Predict on test set
    bets = []
    for m in test:
        odds_h = m.get('odds_h')
        odds_d = m.get('odds_d')
        odds_a = m.get('odds_a')
        if not all([odds_h, odds_d, odds_a]):
            continue

        try:
            probs = model.predict(m['home'], m['away'])
        except Exception:
            continue

        best = ve.find_best_pick(m['home'], m['away'], probs,
                                  {'home': odds_h, 'draw': odds_d, 'away': odds_a})
        if not best:
            continue

        # Settle
        actual = 'H' if m['home_goals'] > m['away_goals'] else ('D' if m['home_goals'] == m['away_goals'] else 'A')
        pick = best['pick']
        won = (pick == m['home'] and actual == 'H') or \
              (pick == 'Draw' and actual == 'D') or \
              (pick == m['away'] and actual == 'A')

        profit = (best['odds'] - 1) if won else -1
        bets.append({
            'match': f"{m['home']} vs {m['away']}",
            'date': m['date'],
            'pick': pick,
            'odds': best['odds'],
            'p_model': best['p_model'],
            'ev': best['ev'],
            'won': won,
            'profit': profit,
            'actual': actual,
        })

        if verbose:
            e = "✅" if won else "❌"
            print(f"  {e} {m['date']} {m['home'][:10]} vs {m['away'][:10]}: "
                  f"{pick} @ {best['odds']:.2f} → {'WIN' if won else 'LOSS'}")

    # Metrics
    if not bets:
        print("  No bets placed")
        return

    wins = sum(1 for b in bets if b['won'])
    total_profit = sum(b['profit'] for b in bets)
    avg_odds = sum(b['odds'] for b in bets) / len(bets)
    avg_ev = sum(b['ev'] for b in bets) / len(bets)
    roi = (total_profit / len(bets)) * 100

    print(f"\n  RESULTS:")
    print(f"  Bets: {len(bets)} | Wins: {wins} | Losses: {len(bets)-wins}")
    print(f"  Hit rate: {wins/len(bets):.1%}")
    print(f"  Average odds: {avg_odds:.2f}")
    print(f"  Average EV: {avg_ev:.1%}")
    print(f"  ROI: {roi:+.1f}%")
    print(f"  Profit: {total_profit:+.2f} units")

    # Per market breakdown
    markets = {}
    for b in bets:
        # Reconstruct market from pick
        if b['pick'] == 'Draw':
            mk = '1X2'
        elif b['pick'] in [m['home'] for m in test]:
            mk = '1X2'
        else:
            mk = '1X2'
        if mk not in markets:
            markets[mk] = {'bets': 0, 'wins': 0, 'profit': 0}
        markets[mk]['bets'] += 1
        markets[mk]['wins'] += b['won']
        markets[mk]['profit'] += b['profit']

    print(f"\n  Top 5 wins:")
    for b in sorted(bets, key=lambda x: -x['profit'])[:5]:
        print(f"    ✅ {b['match'][:30]}: {b['pick']} @ {b['odds']:.2f} (+{b['profit']:.2f}u)")

    print(f"\n  Top 5 losses:")
    for b in sorted(bets, key=lambda x: x['profit'])[:5]:
        print(f"    ❌ {b['match'][:30]}: {b['pick']} @ {b['odds']:.2f} ({b['profit']:.2f}u)")

    print(f"\n{'='*55}")
    return {'bets': len(bets), 'wins': wins, 'roi': roi, 'profit': total_profit}

# Run EPL
fast_backtest('E0', verbose=True)
