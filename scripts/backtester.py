#!/usr/bin/env python3
"""
backtester.py — Rolling-origin backtester for SabiAI v2.

Tests the model on historical data using time-series splits.
Never uses future data. Reports ROI, yield, calibration, Brier score.

Usage:
    python3 backtester.py --league E0 --seasons 3
    python3 backtester.py --all
"""

import os
import sys
import sqlite3
import argparse
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data_pipeline import DataPipeline, LEAGUES
from dixon_coles import DixonColesModel
from value_engine import ValueEngine, strip_vig, ev

DB_PATH = os.path.expanduser("~/.openclaw/workspace-sabi-ai/data/sabiai_v2.db")


class Backtester:
    """
    Rolling-origin backtest for Dixon-Coles model.

    For each historical fixture:
    1. Train on all matches before that fixture's date
    2. Predict the fixture
    3. Compare prediction to actual result
    4. Track ROI, yield, calibration
    """

    def __init__(self, pipeline: DataPipeline, min_ev: float = 0.03):
        self.pipeline = pipeline
        self.value_engine = ValueEngine(min_ev=min_ev)
        self.results = []

    def run(self, league: str, seasons_back: int = 3,
            min_matches: int = 100, verbose: bool = False) -> Dict:
        """
        Run rolling-origin backtest for one league.

        Args:
            league: League code (e.g., 'E0').
            seasons_back: Number of seasons to test on.
            min_matches: Minimum training matches before predictions start.
            verbose: Print each prediction.

        Returns:
            Dict of backtest metrics.
        """
        # Load all matches for the league
        all_matches = []
        now = datetime.utcnow()
        for i in range(seasons_back + 2):  # extra season for training buffer
            year = now.year - i
            season = f"{year}-{year+1}"
            rows = self.pipeline.get_matches(league=league, season=season)
            all_matches.extend(rows)

        # Sort by date
        all_matches.sort(key=lambda x: x.get('date', ''))

        if len(all_matches) < min_matches:
            return {'error': f'Only {len(all_matches)} matches — need {min_matches}'}

        # Rolling prediction
        bets = []
        total_bets = 0
        wins = 0
        total_ev = 0.0
        total_roi = 0.0
        brier_scores = []
        calibration_bins = defaultdict(lambda: {'predicted': 0, 'actual': 0, 'count': 0})
        market_breakdown = defaultdict(lambda: {'bets': 0, 'wins': 0, 'profit': 0.0})

        # Use last 30% of matches as test set
        split_idx = int(len(all_matches) * 0.7)
        test_matches = all_matches[split_idx:]
        baselines = self._baseline_results(test_matches)

        for i, test_match in enumerate(test_matches):
            # Training data: all matches before this one
            train_matches = all_matches[:split_idx + i]

            if len(train_matches) < min_matches:
                continue

            # Fit model on training data
            model_data = []
            for m in train_matches:
                if m.get('hg') is not None and m.get('ag') is not None:
                    model_data.append({
                        'home': m['home'],
                        'away': m['away'],
                        'home_goals': m['hg'],
                        'away_goals': m['ag'],
                        'date': m['date'],
                    })

            if len(model_data) < min_matches:
                continue

            model = DixonColesModel()
            try:
                model.fit(model_data, time_decay_half_life=300.0)
            except Exception:
                continue

            if not model.fitted:
                continue

            # Predict
            home = test_match['home']
            away = test_match['away']

            try:
                probs = model.predict(home, away)
            except Exception:
                continue

            # Get odds (from the match itself — historical odds)
            odds_h = test_match.get('odds_h')
            odds_d = test_match.get('odds_d')
            odds_a = test_match.get('odds_a')

            if not all([odds_h, odds_d, odds_a]):
                continue

            odds_data = {'home': odds_h, 'draw': odds_d, 'away': odds_a}

            # Find value
            best = self.value_engine.find_best_pick(home, away, probs, odds_data)
            if not best:
                continue

            total_bets += 1

            # Settle the bet
            actual = test_match.get('result', '')
            pick = best['pick']

            won = False
            if pick == home and actual == 'H':
                won = True
            elif pick == 'Draw' and actual == 'D':
                won = True
            elif pick == away and actual == 'A':
                won = True

            if won:
                wins += 1
                profit = best['odds'] - 1.0
            else:
                profit = -1.0

            total_ev += best['ev']
            total_roi += profit
            market_breakdown[best['market']]['bets'] += 1
            market_breakdown[best['market']]['wins'] += 1 if won else 0
            market_breakdown[best['market']]['profit'] += profit

            # Brier score for this pick
            p_model = best['p_model']
            actual_prob = 1.0 if won else 0.0
            brier = (p_model - actual_prob) ** 2
            brier_scores.append(brier)

            # Calibration bin
            bin_idx = int(p_model * 10) / 10  # round to nearest 0.1
            calibration_bins[bin_idx]['predicted'] += p_model
            calibration_bins[bin_idx]['actual'] += actual_prob
            calibration_bins[bin_idx]['count'] += 1

            bets.append({
                'match': f"{home} vs {away}",
                'date': test_match['date'],
                'market': best['market'],
                'pick': pick,
                'odds': best['odds'],
                'p_model': p_model,
                'ev': best['ev'],
                'won': won,
                'profit': profit,
            })

            if verbose:
                result_emoji = "✅" if won else "❌"
                print(f"  {result_emoji} {home} vs {away}: {pick} @ {best['odds']:.2f} "
                      f"(model: {p_model:.1%}, EV: {best['ev']:.1%}) → {'WIN' if won else 'LOSS'}")

        # Compute metrics
        if total_bets == 0:
            return {'error': 'No bets placed', 'league': league}

        hit_rate = wins / total_bets
        avg_ev = total_ev / total_bets
        roi_pct = (total_roi / total_bets) * 100
        avg_brier = sum(brier_scores) / len(brier_scores) if brier_scores else 0
        avg_odds = sum(b['odds'] for b in bets) / total_bets

        # Calibration data
        calibration = {}
        for bin_val, data in sorted(calibration_bins.items()):
            if data['count'] > 0:
                calibration[f"{bin_val:.1f}"] = {
                    'predicted_avg': round(data['predicted'] / data['count'], 3),
                    'actual_rate': round(data['actual'] / data['count'], 3),
                    'count': data['count'],
                }

        return {
            'league': league,
            'league_name': LEAGUES.get(league, league),
            'test_matches': len(test_matches),
            'total_bets': total_bets,
            'wins': wins,
            'losses': total_bets - wins,
            'hit_rate': round(hit_rate, 4),
            'avg_odds': round(avg_odds, 2),
            'avg_ev': round(avg_ev, 4),
            'roi_pct': round(roi_pct, 2),
            'total_profit_units': round(total_roi, 2),
            'avg_brier': round(avg_brier, 4),
            'calibration': calibration,
            'market_breakdown': {
                market: {
                    'bets': data['bets'],
                    'wins': data['wins'],
                    'hit_rate': round(data['wins'] / data['bets'], 4) if data['bets'] else 0,
                    'roi_pct': round(data['profit'] / data['bets'] * 100, 2) if data['bets'] else 0,
                    'profit_units': round(data['profit'], 2),
                }
                for market, data in market_breakdown.items()
            },
            'baselines': baselines,
            'bets': bets,
        }

    def _baseline_results(self, matches: List[Dict]) -> Dict[str, Dict[str, float]]:
        """Compute favourite and over-2.5 baselines on the same test rows."""
        favourite_profit = 0.0
        favourite_bets = 0
        favourite_wins = 0
        over_profit = 0.0
        over_bets = 0
        over_wins = 0

        for m in matches:
            odds = {'H': m.get('odds_h'), 'D': m.get('odds_d'), 'A': m.get('odds_a')}
            if all(odds.values()):
                pick = min(odds, key=lambda k: odds[k])
                favourite_bets += 1
                if m.get('result') == pick:
                    favourite_wins += 1
                    favourite_profit += odds[pick] - 1.0
                else:
                    favourite_profit -= 1.0

            over_odds = m.get('ou25_over')
            if over_odds and m.get('hg') is not None and m.get('ag') is not None:
                over_bets += 1
                if m['hg'] + m['ag'] > 2.5:
                    over_wins += 1
                    over_profit += over_odds - 1.0
                else:
                    over_profit -= 1.0

        def pack(bets: int, wins: int, profit: float) -> Dict[str, float]:
            return {
                'bets': bets,
                'wins': wins,
                'hit_rate': round(wins / bets, 4) if bets else 0.0,
                'roi_pct': round(profit / bets * 100, 2) if bets else 0.0,
                'profit_units': round(profit, 2),
            }

        return {
            'favourite': pack(favourite_bets, favourite_wins, favourite_profit),
            'over_2_5': pack(over_bets, over_wins, over_profit),
        }


def print_report(result: Dict):
    """Print a formatted backtest report."""
    if 'error' in result:
        print(f"❌ {result['error']}")
        return

    print(f"\n{'='*55}")
    print(f"  BACKTEST: {result['league_name']} ({result['league']})")
    print(f"{'='*55}")
    print(f"  Test matches:    {result['test_matches']}")
    print(f"  Bets placed:     {result['total_bets']}")
    print(f"  Wins / Losses:   {result['wins']} / {result['losses']}")
    print(f"  Hit rate:        {result['hit_rate']:.1%}")
    print(f"  Average odds:    {result['avg_odds']:.2f}")
    print(f"  Average EV:      {result['avg_ev']:.1%}")
    print(f"  ROI:             {result['roi_pct']:+.1f}%")
    print(f"  Profit (units):  {result['total_profit_units']:+.2f}u")
    print(f"  Brier score:     {result['avg_brier']:.4f}")
    print(f"{'='*55}")

    # Calibration
    if result.get('calibration'):
        print(f"\n  Calibration (predicted vs actual):")
        print(f"  {'Bin':<8} {'Predicted':<12} {'Actual':<12} {'Count':<8}")
        print(f"  {'-'*40}")
        for bin_val, data in result['calibration'].items():
            print(f"  {bin_val:<8} {data['predicted_avg']:<12.3f} "
                  f"{data['actual_rate']:<12.3f} {data['count']:<8}")

    if result.get('market_breakdown'):
        print(f"\n  Per-market breakdown:")
        for market, data in result['market_breakdown'].items():
            print(f"  {market:<10} bets={data['bets']:<4} hit={data['hit_rate']:.1%} "
                  f"roi={data['roi_pct']:+.1f}%")

    # Top wins and losses
    bets = result.get('bets', [])
    if bets:
        wins = [b for b in bets if b['won']]
        losses = [b for b in bets if not b['won']]

        if wins:
            print(f"\n  Top 3 wins:")
            for b in sorted(wins, key=lambda x: -x['profit'])[:3]:
                print(f"    ✅ {b['match']}: {b['pick']} @ {b['odds']:.2f} "
                      f"(+{b['profit']:.2f}u)")

        if losses:
            print(f"\n  Top 3 losses:")
            for b in sorted(losses, key=lambda x: x['profit'])[:3]:
                print(f"    ❌ {b['match']}: {b['pick']} @ {b['odds']:.2f} "
                      f"({b['profit']:.2f}u)")

    # Baseline comparison
    baselines = result.get('baselines', {})
    fav = baselines.get('favourite', {})
    over = baselines.get('over_2_5', {})
    print(f"\n  Baseline comparison:")
    print(f"  If you bet the favourite every time: {fav.get('roi_pct', 0):+.1f}% ROI")
    print(f"  If you bet Over 2.5 every time:      {over.get('roi_pct', 0):+.1f}% ROI")
    print(f"  Our model:                           {result['roi_pct']:+.1f}% ROI")


def main():
    parser = argparse.ArgumentParser(description='SabiAI v2 Backtester')
    parser.add_argument('--league', type=str, help='League code')
    parser.add_argument('--all', action='store_true', help='Test all leagues')
    parser.add_argument('--seasons', type=int, default=3, help='Seasons to test')
    parser.add_argument('--min-ev', type=float, default=0.03, help='Min EV threshold')
    parser.add_argument('--verbose', action='store_true', help='Print each bet')
    args = parser.parse_args()

    pipeline = DataPipeline(DB_PATH)

    if args.all:
        leagues = list(LEAGUES.keys())
    elif args.league:
        leagues = [args.league]
    else:
        leagues = ['E0', 'SP1', 'I1', 'D1', 'F1']

    bt = Backtester(pipeline, min_ev=args.min_ev)

    all_results = []
    for league in leagues:
        print(f"\nTesting {LEAGUES.get(league, league)}...")
        result = bt.run(league, seasons_back=args.seasons, verbose=args.verbose)
        all_results.append(result)
        print_report(result)

    # Overall summary
    valid = [r for r in all_results if 'error' not in r]
    if valid:
        total_bets = sum(r['total_bets'] for r in valid)
        total_wins = sum(r['wins'] for r in valid)
        avg_roi = sum(r['roi_pct'] * r['total_bets'] for r in valid) / total_bets

        print(f"\n{'='*55}")
        print(f"  OVERALL SUMMARY ({len(valid)} leagues)")
        print(f"{'='*55}")
        print(f"  Total bets:   {total_bets}")
        print(f"  Total wins:   {total_wins}")
        print(f"  Hit rate:     {total_wins/total_bets:.1%}")
        print(f"  Weighted ROI: {avg_roi:+.1f}%")
        print(f"{'='*55}")


if __name__ == '__main__':
    main()
