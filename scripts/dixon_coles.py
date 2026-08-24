#!/usr/bin/env python3
"""
dixon_coles.py — Dixon-Coles scoreline probability model for football.

Implements the 1997 Dixon & Coles method:
- Attack/defence strength parameters per team
- Home advantage parameter
- Low-score correlation adjustment (rho)
- Time-decay weighting (recent matches weighted more heavily)

No bookmaker input. Pure statistical model from historical goals.

Usage:
    model = DixonColesModel()
    model.fit(matches_df, league='EPL')
    probs = model.predict('Arsenal', 'Chelsea')
    # {'home_win': 0.48, 'draw': 0.26, 'away_win': 0.26,
    #  'ou_25_over': 0.52, 'ou_25_under': 0.48, 'btts_yes': 0.58, ...}
"""

import math
import numpy as np
from scipy.optimize import minimize
from scipy.special import gamma as gamma_fn
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from collections import defaultdict


def _poisson_pmf(k: int, lam: float) -> float:
    """Poisson probability mass function. P(X=k) = e^-λ * λ^k / k!"""
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return math.exp(-lam) * (lam ** k) / math.factorial(k)


def _tau(x: int, y: int, lambda_x: float, lambda_y: float, rho: float) -> float:
    """
    Dixon-Coles tau adjustment for low-scoring correlation.
    Adjusts the independence assumption for 0-0, 1-0, 0-1, 1-1 scorelines.
    """
    if x == 0 and y == 0:
        return 1 - lambda_x * lambda_y * rho
    elif x == 0 and y == 1:
        return 1 + lambda_x * rho
    elif x == 1 and y == 0:
        return 1 + lambda_y * rho
    elif x == 1 and y == 1:
        return 1 - rho
    else:
        return 1.0


class DixonColesModel:
    """
    Dixon-Coles football scoreline model.

    Fits attack/defence ratings per team from historical match results,
    with time-decay weighting and low-score correlation correction.
    """

    def __init__(self, max_goals: int = 8, rho_bounds: float = 0.3):
        """
        Args:
            max_goals: Maximum goals to consider in scoreline matrix.
            rho_bounds: Bounds for rho parameter (correlation adjustment).
        """
        self.max_goals = max_goals
        self.rho_bounds = rho_bounds
        self.params: Dict[str, float] = {}
        self.teams: List[str] = []
        self.fitted = False
        self.n_matches = 0

    def _build_params(self, teams: List[str]) -> Dict[str, float]:
        """Build parameter vector: home_adv, rho, attack[team], defence[team]."""
        params = {}
        params['home_adv'] = 0.25  # log-odds home advantage
        params['rho'] = -0.13  # low-score correlation
        for team in teams:
            params[f'attack_{team}'] = 0.0
            params[f'defence_{team}'] = 0.0
        return params

    def _unpack(self, params: Dict[str, float], home: str, away: str):
        """Extract lambda_home and lambda_away from parameter vector."""
        home_adv = params['home_adv']
        rho = params['rho']
        atk_h = params.get(f'attack_{home}', 0.0)
        def_h = params.get(f'defence_{home}', 0.0)
        atk_a = params.get(f'attack_{away}', 0.0)
        def_a = params.get(f'defence_{away}', 0.0)

        lambda_h = math.exp(home_adv + atk_h + def_a)
        lambda_a = math.exp(atk_a + def_h)
        return lambda_h, lambda_a, rho

    def _log_likelihood(self, params_vec: np.ndarray, param_names: List[str],
                        matches: List[Dict], time_weights: np.ndarray) -> float:
        """Negative log-likelihood for optimization (minimized)."""
        params = {name: float(params_vec[i]) for i, name in enumerate(param_names)}

        ll = 0.0
        for idx, match in enumerate(matches):
            home = match['home']
            away = match['away']
            hg = match['home_goals']
            ag = match['away_goals']
            w = time_weights[idx]

            lambda_h, lambda_a, rho = self._unpack(params, home, away)

            # Dixon-Coles adjusted probability
            p = _poisson_pmf(hg, lambda_h) * _poisson_pmf(ag, lambda_a)
            tau_val = max(1e-10, _tau(hg, ag, lambda_h, lambda_a, rho))
            p_adj = p * tau_val

            if p_adj <= 0:
                p_adj = 1e-10

            ll += w * math.log(p_adj)

        return -ll  # minimize negative log-likelihood

    def fit(self, matches: List[Dict], time_decay_half_life: float = 365.0):
        """
        Fit the model on historical match data.

        Args:
            matches: List of dicts with keys: home, away, home_goals, away_goals, date
                     date should be ISO format string or datetime.
            time_decay_half_life: Half-life in days for time-decay weighting.
                                  More recent matches weighted more heavily.
        """
        # Collect all teams
        team_set = set()
        for m in matches:
            team_set.add(m['home'])
            team_set.add(m['away'])
        self.teams = sorted(team_set)

        # Parse dates and compute time weights
        now = datetime.now(timezone.utc)
        time_weights = np.ones(len(matches))
        for i, m in enumerate(matches):
            if isinstance(m['date'], str):
                try:
                    dt = datetime.fromisoformat(m['date'].replace('Z', '+00:00'))
                except ValueError:
                    dt = now
            elif isinstance(m['date'], datetime):
                dt = m['date']
            else:
                dt = now

            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)

            days_ago = max(0, (now - dt).total_seconds() / 86400)
            time_weights[i] = 0.5 ** (days_ago / time_decay_half_life)

        # Build parameter vector
        param_dict = self._build_params(self.teams)
        param_names = sorted(param_dict.keys())
        x0 = np.array([param_dict[n] for n in param_names])

        # Optimize
        # Optimize with bounds to keep rho reasonable
        bounds = []
        for name in param_names:
            if name == 'rho':
                bounds.append((-0.5, 0.5))
            elif name == 'home_adv':
                bounds.append((-1.0, 1.0))
            else:
                bounds.append((-5.0, 5.0))

        result = minimize(
            self._log_likelihood,
            x0,
            args=(param_names, matches, time_weights),
            method='L-BFGS-B',
            bounds=bounds,
            options={'maxiter': 2000, 'ftol': 1e-10}
        )

        # Store fitted parameters
        self.params = {name: float(result.x[i]) for i, name in enumerate(param_names)}
        self.fitted = True
        self.n_matches = len(matches)

        return self

    def predict(self, home: str, away: str) -> Dict[str, float]:
        """
        Predict match outcome probabilities.

        Args:
            home: Home team name.
            away: Away team name.

        Returns:
            Dict with probabilities for various markets:
            - home_win, draw, away_win (1X2)
            - ou_X5_over, ou_X5_under for X in [0.5, 1.5, 2.5, 3.5, 4.5]
            - btts_yes, btts_no
            - scorelines: dict of (h, a) → probability
        """
        if not self.fitted:
            raise RuntimeError("Model not fitted. Call fit() first.")

        lambda_h, lambda_a, rho = self._unpack(self.params, home, away)

        # Build and normalize the complete scoreline probability matrix first.
        # All derived markets must come from the same normalized matrix.
        scorelines = {}

        for hg in range(self.max_goals + 1):
            for ag in range(self.max_goals + 1):
                p = _poisson_pmf(hg, lambda_h) * _poisson_pmf(ag, lambda_a)
                tau_val = _tau(hg, ag, lambda_h, lambda_a, rho)
                p_adj = max(0, p * tau_val)
                scorelines[(hg, ag)] = p_adj

        matrix_total = sum(scorelines.values())
        if matrix_total <= 0:
            raise RuntimeError("Scoreline matrix has zero probability mass")
        scorelines = {score: p / matrix_total for score, p in scorelines.items()}

        home_win = sum(p for (hg, ag), p in scorelines.items() if hg > ag)
        draw = sum(p for (hg, ag), p in scorelines.items() if hg == ag)
        away_win = sum(p for (hg, ag), p in scorelines.items() if hg < ag)
        btts_yes = sum(p for (hg, ag), p in scorelines.items() if hg > 0 and ag > 0)
        ou_totals = {
            line: sum(p for (hg, ag), p in scorelines.items() if hg + ag > line)
            for line in (0.5, 1.5, 2.5, 3.5, 4.5)
        }

        result = {
            'home_win': round(home_win, 4),
            'draw': round(draw, 4),
            'away_win': round(away_win, 4),
            'btts_yes': round(btts_yes, 4),
            'btts_no': round(1 - btts_yes, 4),
            'expected_home_goals': round(lambda_h, 2),
            'expected_away_goals': round(lambda_a, 2),
            'scorelines': {f'{h}-{a}': round(p, 4) for (h, a), p in
                           sorted(scorelines.items(), key=lambda x: -x[1])[:10]}
        }

        for line, p in ou_totals.items():
            result[f'ou_{line}_over'] = round(p, 4)
            result[f'ou_{line}_under'] = round(1 - p, 4)

        return result

    def get_team_ratings(self) -> Dict[str, Dict[str, float]]:
        """Get fitted attack/defence ratings for all teams."""
        if not self.fitted:
            return {}
        ratings = {}
        for team in self.teams:
            ratings[team] = {
                'attack': round(self.params.get(f'attack_{team}', 0.0), 4),
                'defence': round(self.params.get(f'defence_{team}', 0.0), 4),
            }
        return ratings
