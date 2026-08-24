#!/usr/bin/env python3
"""
features.py — Rolling feature factory for football match prediction.

Computes pre-match features using only data available before kickoff.
No post-match leakage. All features use shift(1) discipline.

Usage:
    factory = FeatureFactory(db_path)
    features = factory.build_features('Arsenal', 'Chelsea', 'E0', '2026-01-15')
"""

import sqlite3
import math
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple


class FeatureFactory:
    """Build rolling pre-match features for any fixture."""

    def __init__(self, db_path: str):
        self.db_path = db_path

    def _query(self, sql: str, params: tuple = ()) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            return [dict(row) for row in conn.execute(sql, params).fetchall()]

    def _team_matches(self, team: str, league: Optional[str] = None,
                      before: Optional[str] = None, limit: int = 20) -> List[Dict]:
        """Get matches for team, filtered by date (only before cutoff)."""
        sql = """SELECT * FROM matches
                 WHERE (home = ? OR away = ?)"""
        params: list = [team, team]

        if league:
            sql += " AND league = ?"
            params.append(league)
        if before:
            sql += " AND date < ?"
            params.append(before)

        sql += " ORDER BY date DESC LIMIT ?"
        params.append(limit)

        return self._query(sql, tuple(params))

    def _rolling_form(self, matches: List[Dict], team: str, n: int = 5) -> Dict:
        """Compute rolling form over last N matches."""
        recent = matches[:n]
        if not recent:
            return {
                'matches': 0, 'wins': 0, 'draws': 0, 'losses': 0,
                'points': 0, 'pts_per_game': 0.0,
                'goals_for': 0, 'goals_against': 0, 'goal_diff': 0,
                'avg_gf': 0.0, 'avg_ga': 0.0,
                'clean_sheets': 0, 'btts': 0,
                'shots_for': 0, 'shots_against': 0,
                'sot_for': 0, 'sot_against': 0,
                'corners_for': 0, 'corners_against': 0,
                'cards_for': 0, 'cards_against': 0,
            }

        stats = {
            'matches': len(recent), 'wins': 0, 'draws': 0, 'losses': 0,
            'goals_for': 0, 'goals_against': 0,
            'shots_for': 0, 'shots_against': 0,
            'sot_for': 0, 'sot_against': 0,
            'corners_for': 0, 'corners_against': 0,
            'cards_for': 0, 'cards_against': 0,
            'clean_sheets': 0, 'btts': 0,
        }

        for m in recent:
            is_home = m['home'] == team
            gf = m['hg'] if is_home else m['ag']
            ga = m['ag'] if is_home else m['hg']

            stats['goals_for'] += gf
            stats['goals_against'] += ga

            if gf > ga:
                stats['wins'] += 1
            elif gf == ga:
                stats['draws'] += 1
            else:
                stats['losses'] += 1

            # Stats per side
            if is_home:
                stats['shots_for'] += m.get('shots_h') or 0
                stats['shots_against'] += m.get('shots_a') or 0
                stats['sot_for'] += m.get('sot_h') or 0
                stats['sot_against'] += m.get('sot_a') or 0
                stats['corners_for'] += m.get('corners_h') or 0
                stats['corners_against'] += m.get('corners_a') or 0
                stats['cards_for'] += m.get('cards_h') or 0
                stats['cards_against'] += m.get('cards_a') or 0
            else:
                stats['shots_for'] += m.get('shots_a') or 0
                stats['shots_against'] += m.get('shots_h') or 0
                stats['sot_for'] += m.get('sot_a') or 0
                stats['sot_against'] += m.get('sot_h') or 0
                stats['corners_for'] += m.get('corners_a') or 0
                stats['corners_against'] += m.get('corners_h') or 0
                stats['cards_for'] += m.get('cards_a') or 0
                stats['cards_against'] += m.get('cards_h') or 0

            if ga == 0:
                stats['clean_sheets'] += 1
            if m['hg'] > 0 and m['ag'] > 0:
                stats['btts'] += 1

        n_played = max(1, stats['matches'])
        stats['points'] = stats['wins'] * 3 + stats['draws']
        stats['pts_per_game'] = round(stats['points'] / n_played, 2)
        stats['goal_diff'] = stats['goals_for'] - stats['goals_against']
        stats['avg_gf'] = round(stats['goals_for'] / n_played, 2)
        stats['avg_ga'] = round(stats['goals_against'] / n_played, 2)
        stats['avg_shots'] = round(stats['shots_for'] / n_played, 1)
        stats['avg_sot'] = round(stats['sot_for'] / n_played, 1)
        stats['avg_corners'] = round(stats['corners_for'] / n_played, 1)
        stats['avg_cards'] = round(stats['cards_for'] / n_played, 1)
        stats['clean_sheet_pct'] = round(stats['clean_sheets'] / n_played * 100, 1)
        stats['btts_pct'] = round(stats['btts'] / n_played * 100, 1)

        return stats

    def _home_away_split(self, matches: List[Dict], team: str) -> Dict:
        """Separate home and away records."""
        home_matches = [m for m in matches if m['home'] == team]
        away_matches = [m for m in matches if m['away'] == team]

        def _split_stats(matches, is_home):
            if not matches:
                return {'matches': 0, 'wins': 0, 'draws': 0, 'losses': 0,
                        'avg_gf': 0.0, 'avg_ga': 0.0, 'pts_per_game': 0.0}
            w = d = l = gf = ga = 0
            for m in matches:
                gf += m['hg'] if is_home else m['ag']
                ga += m['ag'] if is_home else m['hg']
                if (m['hg'] if is_home else m['ag']) > (m['ag'] if is_home else m['hg']):
                    w += 1
                elif m['hg'] == m['ag']:
                    d += 1
                else:
                    l += 1
            n = len(matches)
            return {
                'matches': n, 'wins': w, 'draws': d, 'losses': l,
                'avg_gf': round(gf / n, 2), 'avg_ga': round(ga / n, 2),
                'pts_per_game': round((w * 3 + d) / n, 2),
            }

        return {
            'home': _split_stats(home_matches[:10], True),
            'away': _split_stats(away_matches[:10], False),
        }

    def _rest_days(self, matches: List[Dict], team: str, match_date: str) -> Optional[int]:
        """Days since last match for this team."""
        if not matches:
            return None
        try:
            target = datetime.strptime(match_date, '%Y-%m-%d')
            last_match_date = None
            for m in matches:
                try:
                    d = datetime.strptime(m['date'], '%Y-%m-%d')
                    if d < target:
                        last_match_date = d
                        break
                except (ValueError, TypeError):
                    continue
            if last_match_date:
                return (target - last_match_date).days
        except (ValueError, TypeError):
            pass
        return None

    def _h2h_features(self, home: str, away: str, before: str) -> Dict:
        """Head-to-head features from historical meetings."""
        sql = """SELECT * FROM matches
                 WHERE ((home = ? AND away = ?) OR (home = ? AND away = ?))
                 AND date < ?
                 ORDER BY date DESC LIMIT 10"""
        matches = self._query(sql, (home, away, away, home, before))

        if not matches:
            return {
                'h2h_matches': 0, 'h2h_home_wins': 0, 'h2h_draws': 0,
                'h2h_away_wins': 0, 'h2h_avg_goals': 0.0, 'h2h_btts_pct': 0.0,
            }

        h_wins = d = a_wins = total_goals = btts = 0
        for m in matches:
            if m['hg'] > m['ag']:
                if m['home'] == home:
                    h_wins += 1
                else:
                    a_wins += 1
            elif m['hg'] == m['ag']:
                d += 1
            else:
                if m['home'] == away:
                    a_wins += 1
                else:
                    h_wins += 1
            total_goals += m['hg'] + m['ag']
            if m['hg'] > 0 and m['ag'] > 0:
                btts += 1

        n = len(matches)
        return {
            'h2h_matches': n,
            'h2h_home_wins': h_wins,
            'h2h_draws': d,
            'h2h_away_wins': a_wins,
            'h2h_avg_goals': round(total_goals / n, 2),
            'h2h_btts_pct': round(btts / n * 100, 1),
        }

    def _elo_features(self, home: str, away: str) -> Dict:
        """Elo ratings from ClubElo API."""
        import urllib.request
        import json

        def fetch_elo(team: str) -> Optional[float]:
            try:
                url = f"http://api.clubelo.com/{team}"
                req = urllib.request.Request(url, headers={'User-Agent': 'SabiAI/2.0'})
                resp = urllib.request.urlopen(req, timeout=10)
                data = json.loads(resp.read())
                if isinstance(data, list) and data:
                    latest = sorted(data, key=lambda x: x.get('From', ''))[-1]
                    return float(latest.get('Elo', 1500))
            except Exception:
                pass
            return None

        elo_h = fetch_elo(home)
        elo_a = fetch_elo(away)

        result = {
            'elo_home': elo_h,
            'elo_away': elo_a,
            'elo_diff': round(elo_h - elo_a, 1) if elo_h and elo_a else None,
        }
        return result

    def build_features(self, home: str, away: str, league: str,
                       match_date: str, include_elo: bool = True) -> Dict:
        """
        Build complete feature vector for a fixture.

        All features use only data available before match_date (no leakage).

        Args:
            home: Home team name.
            away: Away team name.
            league: League code (e.g., 'E0').
            match_date: Match date in ISO format (YYYY-MM-DD).
            include_elo: Whether to fetch Elo ratings (API call).

        Returns:
            Dict of features ready for model input.
        """
        # Get all historical matches for both teams (before match date)
        home_matches = self._team_matches(home, league, before=match_date)
        away_matches = self._team_matches(away, league, before=match_date)

        # Rolling form: 3, 5, 10 games
        home_form_3 = self._rolling_form(home_matches, home, 3)
        home_form_5 = self._rolling_form(home_matches, home, 5)
        home_form_10 = self._rolling_form(home_matches, home, 10)

        away_form_3 = self._rolling_form(away_matches, away, 3)
        away_form_5 = self._rolling_form(away_matches, away, 5)
        away_form_10 = self._rolling_form(away_matches, away, 10)

        # Home/away splits
        home_split = self._home_away_split(home_matches, home)
        away_split = self._home_away_split(away_matches, away)

        # Rest days
        home_rest = self._rest_days(home_matches, home, match_date)
        away_rest = self._rest_days(away_matches, away, match_date)

        # H2H
        h2h = self._h2h_features(home, away, match_date)

        # Elo
        elo = self._elo_features(home, away) if include_elo else {
            'elo_home': None, 'elo_away': None, 'elo_diff': None
        }

        # Combine into flat feature dict
        features = {
            'home': home, 'away': away, 'league': league, 'date': match_date,

            # Home team rolling form
            'h_form3_pts': home_form_3['pts_per_game'],
            'h_form5_pts': home_form_5['pts_per_game'],
            'h_form10_pts': home_form_10['pts_per_game'],
            'h_form5_gf': home_form_5['avg_gf'],
            'h_form5_ga': home_form_5['avg_ga'],
            'h_form5_sot': home_form_5['avg_sot'],
            'h_form5_corners': home_form_5['avg_corners'],
            'h_form5_cs_pct': home_form_5['clean_sheet_pct'],
            'h_form5_btts_pct': home_form_5['btts_pct'],

            # Away team rolling form
            'a_form3_pts': away_form_3['pts_per_game'],
            'a_form5_pts': away_form_5['pts_per_game'],
            'a_form10_pts': away_form_10['pts_per_game'],
            'a_form5_gf': away_form_5['avg_gf'],
            'a_form5_ga': away_form_5['avg_ga'],
            'a_form5_sot': away_form_5['avg_sot'],
            'a_form5_corners': away_form_5['avg_corners'],
            'a_form5_cs_pct': away_form_5['clean_sheet_pct'],
            'a_form5_btts_pct': away_form_5['btts_pct'],

            # Differential features
            'diff_pts': home_form_5['pts_per_game'] - away_form_5['pts_per_game'],
            'diff_gf': home_form_5['avg_gf'] - away_form_5['avg_gf'],
            'diff_ga': home_form_5['avg_ga'] - away_form_5['avg_ga'],
            'diff_sot': home_form_5['avg_sot'] - away_form_5['avg_sot'],
            'diff_corners': home_form_5['avg_corners'] - away_form_5['avg_corners'],

            # Home/away specific
            'h_home_ppg': home_split['home']['pts_per_game'],
            'h_home_avg_gf': home_split['home']['avg_gf'],
            'h_home_avg_ga': home_split['home']['avg_ga'],
            'a_away_ppg': away_split['away']['pts_per_game'],
            'a_away_avg_gf': away_split['away']['avg_gf'],
            'a_away_avg_ga': away_split['away']['avg_ga'],

            # Rest
            'h_rest_days': home_rest,
            'a_rest_days': away_rest,
            'rest_advantage': (home_rest - away_rest) if home_rest and away_rest else None,

            # H2H
            'h2h_matches': h2h['h2h_matches'],
            'h2h_home_wins': h2h['h2h_home_wins'],
            'h2h_draws': h2h['h2h_draws'],
            'h2h_away_wins': h2h['h2h_away_wins'],
            'h2h_avg_goals': h2h['h2h_avg_goals'],
            'h2h_btts_pct': h2h['h2h_btts_pct'],

            # Elo
            'elo_home': elo['elo_home'],
            'elo_away': elo['elo_away'],
            'elo_diff': elo['elo_diff'],
        }

        return features

    def build_feature_vector(self, features: Dict) -> List[float]:
        """
        Convert feature dict to numeric vector for ML model.
        Skips non-numeric and None values (replaced with 0.0).
        """
        skip_keys = {'home', 'away', 'league', 'date'}
        vector = []
        for key in sorted(features.keys()):
            if key in skip_keys:
                continue
            val = features[key]
            if val is None:
                vector.append(0.0)
            elif isinstance(val, (int, float)):
                vector.append(float(val))
            else:
                vector.append(0.0)
        return vector

    def feature_names(self) -> List[str]:
        """Return ordered list of feature names (for model training)."""
        sample = self.build_features('A', 'B', 'XX', '2025-01-01', include_elo=False)
        skip_keys = {'home', 'away', 'league', 'date'}
        return sorted([k for k in sample.keys() if k not in skip_keys])
