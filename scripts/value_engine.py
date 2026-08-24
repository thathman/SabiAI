#!/usr/bin/env python3
"""
value_engine.py — Value detection and Kelly staking for SabiAI.

Compares model probabilities against bookmaker odds to find value bets.
One pick per match. Uses fractional Kelly for stake sizing.

Usage:
    engine = ValueEngine()
    picks = engine.find_value(model_probs, odds_data)
"""

from typing import Dict, List, Optional, Tuple
import math


def strip_vig(odds_list: List[float]) -> List[float]:
    """
    Remove bookmaker overround from a set of odds to get fair probabilities.

    Args:
        odds_list: Decimal odds for all outcomes (e.g., [2.10, 3.40, 3.60])

    Returns:
        List of fair probabilities summing to 1.0.
    """
    if not odds_list or any(o <= 1.0 for o in odds_list):
        return [1.0 / len(odds_list)] * len(odds_list)

    # Implied probabilities
    implied = [1.0 / o for o in odds_list]
    total_implied = sum(implied)

    # Normalize to remove vig
    fair = [p / total_implied for p in implied]
    return fair


def ev(p_model: float, odds: float) -> float:
    """
    Expected value: p_model × decimal_odds − 1.

    Positive EV = the model thinks this bet is profitable.
    """
    return p_model * odds - 1.0


def kelly_fraction(p_model: float, odds: float, max_fraction: float = 0.25) -> float:
    """
    Fractional Kelly criterion for stake sizing.

    Kelly = (p × odds − 1) / (odds − 1)
    Uses 1/4 Kelly and caps the final bankroll fraction at max_fraction.

    Returns fraction of bankroll to stake (0.0 if no edge).
    """
    edge = p_model * odds - 1.0
    if edge <= 0:
        return 0.0

    odds_minus_1 = odds - 1.0
    if odds_minus_1 <= 0:
        return 0.0

    full_kelly = edge / odds_minus_1
    quarter_kelly = full_kelly * 0.25
    return min(quarter_kelly, max_fraction)


def confidence_score(p_model: float, p_market: Optional[float],
                     edge: float, odds: Optional[float]) -> Dict:
    """
    Score confidence in a pick based on multiple signals.

    Returns:
        Dict with score (0-100), label, and breakdown.
    """
    score = 50  # base
    reasons = []

    # Edge size
    if edge >= 0.10:
        score += 20
        reasons.append(f"Large edge ({edge*100:.1f}%)")
    elif edge >= 0.05:
        score += 10
        reasons.append(f"Moderate edge ({edge*100:.1f}%)")
    elif edge >= 0.03:
        score += 5
        reasons.append(f"Small edge ({edge*100:.1f}%)")

    # Model certainty
    if p_model >= 0.70:
        score += 15
        reasons.append(f"Strong model probability ({p_model*100:.1f}%)")
    elif p_model >= 0.60:
        score += 8
        reasons.append(f"Decent model probability ({p_model*100:.1f}%)")

    # Market divergence
    if p_market and abs(p_model - p_market) >= 0.10:
        score += 10
        reasons.append(f"Significant divergence from market")

    # Odds quality (lower odds = more likely outcome, tighter market)
    if odds and odds <= 1.80:
        score += 5
        reasons.append("Short price — higher likelihood")

    # Penalize if model is less than 50%
    if p_model < 0.50:
        score -= 20
        reasons.append("Model below 50% — weak conviction")

    score = max(0, min(100, score))

    if score >= 75:
        label = "STRONG"
    elif score >= 60:
        label = "SOLID"
    elif score >= 50:
        label = "LEAN"
    else:
        label = "WEAK"

    return {
        'score': score,
        'label': label,
        'reasons': reasons,
    }


class ValueEngine:
    """
    Find value bets by comparing model probabilities to bookmaker odds.

    One pick per match. Highest EV wins.
    """

    def __init__(self, min_ev: float = 0.03, min_confidence: int = 50,
                 max_kelly: float = 0.25):
        """
        Args:
            min_ev: Minimum EV threshold (default 3%).
            min_confidence: Minimum confidence score to include pick.
            max_kelly: Maximum Kelly fraction (default 1/4 Kelly).
        """
        self.min_ev = min_ev
        self.min_confidence = min_confidence
        self.max_kelly = max_kelly

    def compute_market_probs(self, odds_data: Dict[str, float]) -> Dict[str, float]:
        """
        Compute no-vig market probabilities from odds.

        Args:
            odds_data: Dict like {'home': 2.10, 'draw': 3.40, 'away': 3.60}
                       or {'over': 1.85, 'under': 2.00}

        Returns:
            Dict of fair probabilities keyed the same way.
        """
        keys = list(odds_data.keys())
        odds_list = [odds_data[k] for k in keys]
        fair_probs = strip_vig(odds_list)
        return {k: round(p, 4) for k, p in zip(keys, fair_probs)}

    def evaluate_pick(self, market: str, pick: str, p_model: float,
                      odds: Optional[float], market_prob: Optional[float],
                      match_context: Optional[Dict] = None) -> Optional[Dict]:
        """
        Evaluate a single potential pick.

        Returns pick dict if it passes all filters, None otherwise.
        """
        if odds is None or odds <= 1.0:
            return None

        edge = p_model - (market_prob or 0)
        ev_val = ev(p_model, odds)

        if ev_val < self.min_ev:
            return None

        conf = confidence_score(p_model, market_prob, edge, odds)
        if conf['score'] < self.min_confidence:
            return None

        kelly_stake = kelly_fraction(p_model, odds, self.max_kelly)

        return {
            'market': market,
            'pick': pick,
            'odds': round(odds, 2),
            'p_model': round(p_model, 4),
            'p_market': round(market_prob, 4) if market_prob else None,
            'edge': round(edge, 4),
            'ev': round(ev_val, 4),
            'kelly': round(kelly_stake, 4),
            'confidence': conf,
        }

    def find_value_1x2(self, home: str, away: str,
                       model_probs: Dict[str, float],
                       odds_data: Dict[str, float]) -> List[Dict]:
        """
        Find value in 1X2 market.

        Args:
            home: Home team name.
            away: Away team name.
            model_probs: {'home_win': 0.48, 'draw': 0.26, 'away_win': 0.26}
            odds_data: {'home': 2.10, 'draw': 3.40, 'away': 3.60}

        Returns:
            List of value picks (sorted by EV, best first).
        """
        market_probs = self.compute_market_probs(odds_data)
        results = []

        mapping = {
            'home': ('home_win', home),
            'draw': ('draw', 'Draw'),
            'away': ('away_win', away),
        }

        for key, (model_key, label) in mapping.items():
            p = model_probs.get(model_key, 0)
            o = odds_data.get(key)
            mp = market_probs.get(key)

            pick = self.evaluate_pick('1X2', label, p, o, mp)
            if pick:
                pick['match'] = f"{home} vs {away}"
                results.append(pick)

        return sorted(results, key=lambda x: -x['ev'])

    def find_value_ou(self, home: str, away: str,
                      model_probs: Dict[str, float],
                      odds_data: Dict[str, float]) -> List[Dict]:
        """
        Find value in Over/Under market.

        Args:
            model_probs: {'ou_25_over': 0.52, 'ou_25_under': 0.48}
            odds_data: {'over': 1.85, 'under': 2.00}
        """
        market_probs = self.compute_market_probs(odds_data)
        results = []

        for side, model_key in [('over', 'ou_25_over'), ('under', 'ou_25_under')]:
            p = model_probs.get(model_key, 0)
            o = odds_data.get(side)
            mp = market_probs.get(side)

            label = f"{'Over' if side == 'over' else 'Under'} 2.5"
            pick = self.evaluate_pick('O/U 2.5', label, p, o, mp)
            if pick:
                pick['match'] = f"{home} vs {away}"
                results.append(pick)

        return sorted(results, key=lambda x: -x['ev'])

    def find_value_btts(self, home: str, away: str,
                        model_probs: Dict[str, float],
                        odds_data: Dict[str, float]) -> List[Dict]:
        """
        Find value in Both Teams to Score market.

        Args:
            model_probs: {'btts_yes': 0.58, 'btts_no': 0.42}
            odds_data: {'yes': 1.75, 'no': 2.10}
        """
        market_probs = self.compute_market_probs(odds_data)
        results = []

        for side, model_key in [('yes', 'btts_yes'), ('no', 'btts_no')]:
            p = model_probs.get(model_key, 0)
            o = odds_data.get(side)
            mp = market_probs.get(side)

            label = "BTTS Yes" if side == 'yes' else "BTTS No"
            pick = self.evaluate_pick('BTTS', label, p, o, mp)
            if pick:
                pick['match'] = f"{home} vs {away}"
                results.append(pick)

        return sorted(results, key=lambda x: -x['ev'])

    def find_best_pick(self, home: str, away: str,
                       model_probs: Dict[str, float],
                       odds_data: Dict[str, float]) -> Optional[Dict]:
        """
        Find the single best pick for a match across all markets.

        Returns the pick with highest EV, or None if no value found.
        """
        all_picks = []
        all_picks.extend(self.find_value_1x2(home, away, model_probs, odds_data))

        # O/U odds
        if 'over' in odds_data and 'under' in odds_data:
            all_picks.extend(self.find_value_ou(home, away, model_probs, odds_data))

        # BTTS odds
        if 'btts_yes' in odds_data and 'btts_no' in odds_data:
            btts_odds = {'yes': odds_data['btts_yes'], 'no': odds_data['btts_no']}
            all_picks.extend(self.find_value_btts(home, away, model_probs, btts_odds))

        if not all_picks:
            return None

        # Return best by EV
        return sorted(all_picks, key=lambda x: -x['ev'])[0]

    def format_pick(self, pick: Dict) -> str:
        """Format a pick for display."""
        conf = pick.get('confidence', {})
        emoji = '🟢' if conf.get('label') == 'STRONG' else \
                '🟡' if conf.get('label') == 'SOLID' else '⚪'

        lines = [
            f"{emoji} *{pick['match']}*",
            f"📌 {pick['market']}: {pick['pick']}",
            f"📊 Odds: {pick['odds']}",
            f"🎯 Model: {pick['p_model']*100:.1f}% | Market: {pick.get('p_market', 0)*100:.1f}%" if pick.get('p_market') else f"🎯 Model: {pick['p_model']*100:.1f}%",
            f"💰 EV: {pick['ev']*100:.1f}% | Kelly: {pick['kelly']*100:.1f}%",
            f"⭐ Confidence: {conf.get('score', 0)}/100 ({conf.get('label', '?')})",
        ]

        if conf.get('reasons'):
            lines.append("📋 " + " | ".join(conf['reasons'][:3]))

        return "\n".join(lines)
