#!/usr/bin/env python3
"""
data_pipeline.py — Football data loader from football-data.co.uk.

Downloads, parses, and stores match results with stats (shots, corners, cards).
All historical data is cached locally in SQLite for fast access.

Usage:
    pipeline = DataPipeline()
    pipeline.update()  # download latest CSVs
    matches = pipeline.get_matches(league='E0', season='2025-2026')
    upcoming = pipeline.get_upcoming(league='E0')
"""

import os
import csv
import io
import sqlite3
import requests
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

DB_PATH = os.path.expanduser("~/.openclaw/workspace-sabi-ai/data/sabiai_v2.db")
FDCO_BASE = "https://www.football-data.co.uk/mmz4281"

# League codes: football-data.co.uk → name mapping
LEAGUES = {
    'E0': 'Premier League',
    'E1': 'Championship',
    'E2': 'League One',
    'E3': 'League Two',
    'SP1': 'La Liga',
    'SP2': 'La Liga 2',
    'I1': 'Serie A',
    'I2': 'Serie B',
    'D1': 'Bundesliga',
    'D2': '2. Bundesliga',
    'F1': 'Ligue 1',
    'F2': 'Ligue 2',
    'N1': 'Eredivisie',
    'P1': 'Primeira Liga',
    'T1': 'Super Lig',
    'B1': 'Belgian Pro League',
    'SC0': 'Scottish Premiership',
    'G1': 'Greek Super League',
}

# Column mapping: football-data.co.uk uses different headers across seasons
# We normalize to: home, away, hg, ag, shots_h, shots_a, sot_h, sot_a,
# corners_h, corners_a, cards_h, cards_a, ref, date
COLUMN_MAP = {
    # Goals
    'FTHG': 'hg', 'HomeTeam': 'home', 'AwayTeam': 'away',
    'FTAG': 'ag', 'FTR': 'result',
    # Shots
    'HS': 'shots_h', 'AS': 'shots_a',
    'HST': 'sot_h', 'AST': 'sot_a',
    # Corners
    'HC': 'corners_h', 'AC': 'corners_a',
    # Cards
    'HY': 'cards_h', 'AY': 'cards_a',
    'HR': 'red_h', 'AR': 'red_a',
    # Referee
    'Referee': 'referee',
    # Date
    'Date': 'date',
    # Odds (we store raw, process in value_engine)
    'B365H': 'odds_h_b365', 'B365D': 'odds_d_b365', 'B365A': 'odds_a_b365',
    'BWH': 'odds_h_bw', 'BWD': 'odds_d_bw', 'BWA': 'odds_a_bw',
    'IWH': 'odds_h_iw', 'IWD': 'odds_d_iw', 'IWA': 'odds_a_iw',
    'PSH': 'odds_h_ps', 'PSD': 'odds_d_ps', 'PSA': 'odds_a_ps',
    'WHH': 'odds_h_wh', 'WHD': 'odds_d_wh', 'WHA': 'odds_a_wh',
    'AvgH': 'odds_h_avg', 'AvgD': 'odds_d_avg', 'AvgA': 'odds_a_avg',
    'BbMxH': 'odds_h_max', 'BbMxD': 'odds_d_max', 'BbMxA': 'odds_a_max',
    'BbAvH': 'odds_h_avg2', 'BbAvD': 'odds_d_avg2', 'BbAvA': 'odds_a_avg2',
    # O/U odds
    'BbAv>2.5': 'ou25_avg_over', 'BbAv<2.5': 'ou25_avg_under',
    'BbMx>2.5': 'ou25_max_over', 'BbMx<2.5': 'ou25_max_under',
}


def _season_code(year: int) -> str:
    """Generate season code like '2526' for 2025-2026 season."""
    yy = year % 100
    return f"{yy}{yy+1:02d}"


def _parse_date(date_str: str) -> Optional[str]:
    """Parse various date formats from football-data.co.uk to ISO format."""
    if not date_str or not date_str.strip():
        return None
    date_str = date_str.strip()
    for fmt in ('%d/%m/%Y', '%d/%m/%y', '%Y-%m-%d', '%d-%m-%Y'):
        try:
            return datetime.strptime(date_str, fmt).strftime('%Y-%m-%d')
        except ValueError:
            continue
    return None


class DataPipeline:
    """Download, parse, and cache football-data.co.uk match data."""

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_db()

    def _init_db(self):
        """Create tables if they don't exist."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS matches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    league TEXT,
                    season TEXT,
                    date TEXT,
                    home TEXT,
                    away TEXT,
                    hg INTEGER,
                    ag INTEGER,
                    result TEXT,
                    shots_h INTEGER,
                    shots_a INTEGER,
                    sot_h INTEGER,
                    sot_a INTEGER,
                    corners_h INTEGER,
                    corners_a INTEGER,
                    cards_h INTEGER,
                    cards_a INTEGER,
                    red_h INTEGER,
                    red_a INTEGER,
                    referee TEXT,
                    odds_h REAL,
                    odds_d REAL,
                    odds_a REAL,
                    ou25_over REAL,
                    ou25_under REAL,
                    UNIQUE(league, season, date, home, away)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS upcoming (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    league TEXT,
                    season TEXT,
                    date TEXT,
                    home TEXT,
                    away TEXT,
                    odds_h REAL,
                    odds_d REAL,
                    odds_a REAL,
                    ou25_over REAL,
                    ou25_under REAL,
                    scraped_at TEXT,
                    UNIQUE(league, season, date, home, away)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS update_log (
                    league TEXT,
                    season TEXT,
                    last_updated TEXT,
                    rows_added INTEGER,
                    PRIMARY KEY (league, season)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS odds_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    match_id INTEGER,
                    league TEXT,
                    season TEXT,
                    date TEXT,
                    home TEXT,
                    away TEXT,
                    odds_h REAL,
                    odds_d REAL,
                    odds_a REAL,
                    ou25_over REAL,
                    ou25_under REAL,
                    source TEXT,
                    captured_at TEXT,
                    UNIQUE(league, season, date, home, away, source, captured_at)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS team_match_features (
                    match_id INTEGER,
                    league TEXT,
                    season TEXT,
                    date TEXT,
                    team TEXT,
                    opponent TEXT,
                    is_home INTEGER,
                    form_window INTEGER,
                    matches_played INTEGER,
                    points REAL,
                    goals_for REAL,
                    goals_against REAL,
                    shots_for REAL,
                    shots_against REAL,
                    sot_for REAL,
                    sot_against REAL,
                    corners_for REAL,
                    corners_against REAL,
                    clean_sheet_pct REAL,
                    PRIMARY KEY (match_id, team, form_window)
                )
            """)
            conn.commit()

    def download_csv(self, league: str, season_code: str) -> Optional[str]:
        """Download a CSV from football-data.co.uk."""
        url = f"{FDCO_BASE}/{season_code}/{league}.csv"
        try:
            resp = requests.get(url, timeout=30)
            if resp.status_code == 200 and len(resp.text) > 100:
                return resp.text
        except Exception as e:
            print(f"Download failed for {url}: {e}")
        return None

    def parse_csv(self, csv_text: str) -> List[Dict]:
        """Parse CSV text into normalized match dicts."""
        reader = csv.DictReader(io.StringIO(csv_text))
        matches = []
        for row in reader:
            # Only completed matches (have result)
            result = row.get('FTR', '').strip()
            if not result or result not in ('H', 'D', 'A'):
                continue

            match = {}
            for csv_col, our_col in COLUMN_MAP.items():
                val = row.get(csv_col, '').strip()
                if our_col in ('hg', 'ag', 'shots_h', 'shots_a', 'sot_h', 'sot_a',
                               'corners_h', 'corners_a', 'cards_h', 'cards_a',
                               'red_h', 'red_a'):
                    try:
                        match[our_col] = int(val) if val else None
                    except ValueError:
                        match[our_col] = None
                elif our_col in ('odds_h_b365', 'odds_d_b365', 'odds_a_b365',
                                 'odds_h_avg', 'odds_d_avg', 'odds_a_avg',
                                 'odds_h_max', 'odds_d_max', 'odds_a_max',
                                 'ou25_avg_over', 'ou25_avg_under'):
                    try:
                        match[our_col] = float(val) if val else None
                    except ValueError:
                        match[our_col] = None
                else:
                    match[our_col] = val if val else None

            # Skip if no teams or no goals
            if not match.get('home') or not match.get('away'):
                continue
            if match.get('hg') is None or match.get('ag') is None:
                continue

            # Parse date
            match['date'] = _parse_date(match.get('date', ''))
            if not match['date']:
                continue

            # Resolve odds: prefer average, fallback to B365
            match['odds_h'] = match.get('odds_h_avg') or match.get('odds_h_b365')
            match['odds_d'] = match.get('odds_d_avg') or match.get('odds_d_b365')
            match['odds_a'] = match.get('odds_a_avg') or match.get('odds_a_b365')
            match['ou25_over'] = match.get('ou25_avg_over')
            match['ou25_under'] = match.get('ou25_avg_under')

            matches.append(match)

        return matches

    def store_matches(self, league: str, season: str, matches: List[Dict]) -> int:
        """Store parsed matches in SQLite. Returns rows added."""
        added = 0
        with sqlite3.connect(self.db_path) as conn:
            for m in matches:
                try:
                    cur = conn.execute("""
                        INSERT OR IGNORE INTO matches
                        (league, season, date, home, away, hg, ag, result,
                         shots_h, shots_a, sot_h, sot_a,
                         corners_h, corners_a, cards_h, cards_a,
                         red_h, red_a, referee,
                         odds_h, odds_d, odds_a, ou25_over, ou25_under)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?,
                                ?, ?, ?, ?,
                                ?, ?, ?, ?,
                                ?, ?, ?,
                                ?, ?, ?, ?, ?)
                    """, (
                        league, season, m['date'], m['home'], m['away'],
                        m['hg'], m['ag'], m.get('result'),
                        m.get('shots_h'), m.get('shots_a'),
                        m.get('sot_h'), m.get('sot_a'),
                        m.get('corners_h'), m.get('corners_a'),
                        m.get('cards_h'), m.get('cards_a'),
                        m.get('red_h'), m.get('red_a'),
                        m.get('referee'),
                        m.get('odds_h'), m.get('odds_d'), m.get('odds_a'),
                        m.get('ou25_over'), m.get('ou25_under'),
                    ))
                    if cur.rowcount:
                        added += 1
                    match_id = conn.execute("""
                        SELECT id FROM matches
                        WHERE league = ? AND season = ? AND date = ? AND home = ? AND away = ?
                    """, (league, season, m['date'], m['home'], m['away'])).fetchone()
                    if match_id and any(m.get(k) for k in ('odds_h', 'odds_d', 'odds_a',
                                                           'ou25_over', 'ou25_under')):
                        conn.execute("""
                            INSERT OR IGNORE INTO odds_snapshots
                            (match_id, league, season, date, home, away, odds_h, odds_d,
                             odds_a, ou25_over, ou25_under, source, captured_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            match_id[0], league, season, m['date'], m['home'], m['away'],
                            m.get('odds_h'), m.get('odds_d'), m.get('odds_a'),
                            m.get('ou25_over'), m.get('ou25_under'),
                            'football-data.co.uk', datetime.utcnow().isoformat(),
                        ))
                except sqlite3.IntegrityError:
                    pass

            # Update log
            conn.execute("""
                INSERT OR REPLACE INTO update_log (league, season, last_updated, rows_added)
                VALUES (?, ?, ?, ?)
            """, (league, season, datetime.utcnow().isoformat(), added))
            conn.commit()

        return added

    def build_rolling_features(self, windows: Tuple[int, ...] = (5, 10)) -> None:
        """
        Persist pre-match rolling team features for each match.

        Rows are processed chronologically and each feature row is based only on
        matches already seen before the current fixture, equivalent to shift(1).
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = [dict(r) for r in conn.execute("""
                SELECT * FROM matches ORDER BY date ASC, id ASC
            """).fetchall()]
            conn.execute("DELETE FROM team_match_features")
            history: Dict[Tuple[str, str], List[Dict]] = {}

            def team_view(match: Dict, team: str) -> Dict:
                is_home = match['home'] == team
                return {
                    'points': 3 if ((match['hg'] > match['ag']) == is_home and match['hg'] != match['ag'])
                    else 1 if match['hg'] == match['ag'] else 0,
                    'goals_for': match['hg'] if is_home else match['ag'],
                    'goals_against': match['ag'] if is_home else match['hg'],
                    'shots_for': match.get('shots_h') if is_home else match.get('shots_a'),
                    'shots_against': match.get('shots_a') if is_home else match.get('shots_h'),
                    'sot_for': match.get('sot_h') if is_home else match.get('sot_a'),
                    'sot_against': match.get('sot_a') if is_home else match.get('sot_h'),
                    'corners_for': match.get('corners_h') if is_home else match.get('corners_a'),
                    'corners_against': match.get('corners_a') if is_home else match.get('corners_h'),
                    'clean_sheet': 1 if (match['ag'] if is_home else match['hg']) == 0 else 0,
                }

            def summarize(prev: List[Dict], window: int) -> Dict:
                sample = prev[-window:]
                n = len(sample)
                if not n:
                    return defaultdict(float, {'matches_played': 0})
                out = {'matches_played': n}
                for key in ('points', 'goals_for', 'goals_against', 'shots_for',
                            'shots_against', 'sot_for', 'sot_against',
                            'corners_for', 'corners_against'):
                    out[key] = sum((m.get(key) or 0) for m in sample) / n
                out['clean_sheet_pct'] = sum(m.get('clean_sheet', 0) for m in sample) / n * 100
                return out

            for match in rows:
                for team, opponent, is_home in (
                    (match['home'], match['away'], 1),
                    (match['away'], match['home'], 0),
                ):
                    prev = history.get((match['league'], team), [])
                    for window in windows:
                        stats = summarize(prev, window)
                        conn.execute("""
                            INSERT OR REPLACE INTO team_match_features
                            (match_id, league, season, date, team, opponent, is_home,
                             form_window, matches_played, points, goals_for, goals_against,
                             shots_for, shots_against, sot_for, sot_against,
                             corners_for, corners_against, clean_sheet_pct)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            match['id'], match['league'], match['season'], match['date'],
                            team, opponent, is_home, window, stats['matches_played'],
                            stats['points'], stats['goals_for'], stats['goals_against'],
                            stats['shots_for'], stats['shots_against'], stats['sot_for'],
                            stats['sot_against'], stats['corners_for'],
                            stats['corners_against'], stats['clean_sheet_pct'],
                        ))
                history.setdefault((match['league'], match['home']), []).append(team_view(match, match['home']))
                history.setdefault((match['league'], match['away']), []).append(team_view(match, match['away']))
            conn.commit()

    def update(self, leagues: Optional[List[str]] = None, seasons_back: int = 2):
        """
        Download and store latest data for all configured leagues.

        Args:
            leagues: List of league codes. None = all leagues.
            seasons_back: How many past seasons to download.
        """
        now = datetime.utcnow()
        current_year = now.year if now.month >= 7 else now.year - 1

        target_leagues = leagues or list(LEAGUES.keys())

        for league in target_leagues:
            for i in range(seasons_back):
                year = current_year - i
                sc = _season_code(year)
                season_str = f"{year}-{year+1}"

                print(f"Downloading {LEAGUES.get(league, league)} {season_str}...")
                csv_text = self.download_csv(league, sc)
                if csv_text:
                    matches = self.parse_csv(csv_text)
                    added = self.store_matches(league, season_str, matches)
                    print(f"  → {len(matches)} matches parsed, {added} stored")
                else:
                    print(f"  → No data available")
        self.build_rolling_features()

    def get_matches(self, league: Optional[str] = None,
                    season: Optional[str] = None,
                    since: Optional[str] = None) -> List[Dict]:
        """
        Retrieve matches from database.

        Args:
            league: Filter by league code.
            season: Filter by season string.
            since: Only matches after this date (ISO format).

        Returns:
            List of match dicts sorted by date.
        """
        query = "SELECT * FROM matches WHERE 1=1"
        params = []

        if league:
            query += " AND league = ?"
            params.append(league)
        if season:
            query += " AND season = ?"
            params.append(season)
        if since:
            query += " AND date >= ?"
            params.append(since)

        query += " ORDER BY date ASC"

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query, params).fetchall()

        return [dict(row) for row in rows]

    def get_team_matches(self, team: str, league: Optional[str] = None,
                         limit: int = 10) -> List[Dict]:
        """Get last N matches for a team (home or away)."""
        query = """SELECT * FROM matches
                   WHERE (home = ? OR away = ?)"""
        params = [team, team]

        if league:
            query += " AND league = ?"
            params.append(league)

        query += " ORDER BY date DESC LIMIT ?"
        params.append(limit)

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query, params).fetchall()

        return [dict(row) for row in rows]

    def get_team_stats(self, team: str, league: Optional[str] = None,
                       last_n: int = 10) -> Dict:
        """
        Compute rolling stats for a team over last N matches.

        Returns:
            Dict with: wins, draws, losses, goals_for, goals_against,
                       shots_per_game, sot_per_game, corners_per_game,
                       cards_per_game, clean_sheets, btts_pct,
                       home_record, away_record, avg_odds_h, avg_odds_a
        """
        matches = self.get_team_matches(team, league, last_n)

        stats = {
            'matches_played': 0, 'wins': 0, 'draws': 0, 'losses': 0,
            'goals_for': 0, 'goals_against': 0,
            'shots_for': 0, 'shots_against': 0,
            'sot_for': 0, 'sot_against': 0,
            'corners_for': 0, 'corners_against': 0,
            'cards_for': 0, 'cards_against': 0,
            'clean_sheets': 0, 'btts': 0,
            'home_matches': 0, 'home_wins': 0, 'home_goals_for': 0,
            'away_matches': 0, 'away_wins': 0, 'away_goals_for': 0,
        }

        for m in matches:
            is_home = m['home'] == team
            gf = m['hg'] if is_home else m['ag']
            ga = m['ag'] if is_home else m['hg']

            stats['matches_played'] += 1
            stats['goals_for'] += gf
            stats['goals_against'] += ga

            if gf > ga:
                stats['wins'] += 1
            elif gf == ga:
                stats['draws'] += 1
            else:
                stats['losses'] += 1

            # Shots
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

            # Home/away splits
            if is_home:
                stats['home_matches'] += 1
                if gf > ga:
                    stats['home_wins'] += 1
                stats['home_goals_for'] += gf
            else:
                stats['away_matches'] += 1
                if gf > ga:
                    stats['away_wins'] += 1
                stats['away_goals_for'] += gf

        n = max(1, stats['matches_played'])
        stats['avg_goals_for'] = round(stats['goals_for'] / n, 2)
        stats['avg_goals_against'] = round(stats['goals_against'] / n, 2)
        stats['avg_shots'] = round(stats['shots_for'] / n, 1)
        stats['avg_sot'] = round(stats['sot_for'] / n, 1)
        stats['avg_corners'] = round(stats['corners_for'] / n, 1)
        stats['avg_cards'] = round(stats['cards_for'] / n, 1)
        stats['clean_sheet_pct'] = round(stats['clean_sheets'] / n * 100, 1)
        stats['btts_pct'] = round(stats['btts'] / n * 100, 1)
        stats['pts_per_game'] = round((stats['wins'] * 3 + stats['draws']) / n, 2)

        return stats

    def get_h2h(self, home: str, away: str, last_n: int = 10) -> Dict:
        """Get head-to-head record between two teams."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT * FROM matches
                WHERE (home = ? AND away = ?) OR (home = ? AND away = ?)
                ORDER BY date DESC LIMIT ?
            """, (home, away, away, home, last_n)).fetchall()

        matches = [dict(row) for row in rows]
        if not matches:
            return {'matches': 0, 'home_wins': 0, 'draws': 0, 'away_wins': 0,
                    'avg_total_goals': 0, 'btts_pct': 0}

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
            'matches': n,
            'home_wins': h_wins,
            'draws': d,
            'away_wins': a_wins,
            'avg_total_goals': round(total_goals / n, 2),
            'btts_pct': round(btts / n * 100, 1),
            'results': [f"{m['home']} {m['hg']}-{m['ag']} {m['away']}" for m in matches[:5]]
        }

    def get_league_code(self, league_name: str) -> Optional[str]:
        """Find league code from partial name match."""
        name_lower = league_name.lower()
        for code, name in LEAGUES.items():
            if name_lower in name.lower() or name.lower() in name_lower:
                return code
        return None
