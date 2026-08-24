#!/usr/bin/env python3
"""
sabiai_v2.py — Main SabiAI v2 pipeline.

Orchestrates: data → features → Dixon-Coles → value → rationale → picks.
Replaces value_bet_finder.py.

Usage:
    python3 sabiai_v2.py                    # scan today's picks
    python3 sabiai_v2.py --league E0        # EPL only
    python3 sabiai_v2.py --max-picks 5      # up to 5 picks
    python3 sabiai_v2.py --format telegram  # Telegram output
    python3 sabiai_v2.py --update-data      # download fresh data first
"""

import os
import sys
import json
import sqlite3
import argparse
from datetime import datetime, timezone, timedelta
from typing import Dict, List

# Add scripts dir to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data_pipeline import DataPipeline, LEAGUES
from features import FeatureFactory
from dixon_coles import DixonColesModel
from value_engine import ValueEngine
from rationale import RationaleGenerator

DB_PATH = os.path.expanduser("~/.openclaw/workspace-sabi-ai/data/sabiai_v2.db")
DATA_DIR = os.path.expanduser("~/.openclaw/workspace-sabi-ai/data")
PREDICTIONS_DB = os.path.expanduser("~/.openclaw/workspace-sabi-ai/data/predictions.db")


def current_season_start(now: datetime = None) -> int:
    """Return the start year for the active European football season."""
    now = now or datetime.utcnow()
    return now.year if now.month >= 7 else now.year - 1


def init_predictions_db():
    """Create predictions tracking table."""
    os.makedirs(DATA_DIR, exist_ok=True)
    with sqlite3.connect(PREDICTIONS_DB) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT,
                league TEXT,
                home TEXT,
                away TEXT,
                market TEXT,
                pick TEXT,
                odds REAL,
                p_model REAL,
                p_market REAL,
                ev REAL,
                kelly REAL,
                confidence_score INTEGER,
                confidence_label TEXT,
                result TEXT,
                pnl REAL,
                created_at TEXT
            )
        """)
        conn.commit()


def get_upcoming_fixtures_espn(league_code: str) -> list:
    """
    Fetch upcoming fixtures from ESPN API.
    Returns list of dicts with home, away, date, league.
    """
    import urllib.request

    # Map football-data.co.uk code to ESPN slug
    ESPN_MAP = {
        'E0': 'eng.1', 'E1': 'eng.2', 'SP1': 'esp.1', 'I1': 'ita.1',
        'D1': 'ger.1', 'F1': 'fra.1', 'N1': 'ned.1', 'P1': 'por.1',
        'T1': 'tur.1', 'B1': 'bel.1', 'SC0': 'sco.1', 'G1': 'gre.1',
    }

    espn_slug = ESPN_MAP.get(league_code)
    if not espn_slug:
        return []

    url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{espn_slug}/scoreboard"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'SabiAI/2.0'})
        resp = urllib.request.urlopen(req, timeout=15)
        data = json.loads(resp.read())
    except Exception as e:
        print(f"ESPN fetch failed for {league_code}: {e}")
        return []

    fixtures = []
    for event in data.get('events', []):
        try:
            comp = event['competitions'][0]
            if comp.get('status', {}).get('type', {}).get('completed'):
                continue

            teams = comp.get('competitors', [])
            if len(teams) < 2:
                continue

            home_team = None
            away_team = None
            for t in teams:
                if t.get('homeAway') == 'home':
                    home_team = t['team']['displayName']
                else:
                    away_team = t['team']['displayName']

            if not home_team or not away_team:
                continue

            # Parse date
            start = event.get('date', '')
            try:
                dt = datetime.fromisoformat(start.replace('Z', '+00:00'))
                date_str = dt.strftime('%Y-%m-%d')
            except Exception:
                continue

            # Extract odds if available
            odds_h = odds_d = odds_a = None
            for odd in comp.get('odds', []):
                if odd.get('details', {}).get('name') == 'Moneyline':
                    odds_h = odd.get('homeTeamOdds', {}).get('decimalOdds', {}).get('value')
                    odds_a = odd.get('awayTeamOdds', {}).get('decimalOdds', {}).get('value')
                    # Draw odds from spread or overUnder
                    break
                # Try overUnder for O/U 2.5
                ou_over = odd.get('overUnder')

            fixtures.append({
                'home': home_team,
                'away': away_team,
                'date': date_str,
                'league': league_code,
                'odds_h': odds_h,
                'odds_a': odds_a,
            })

        except Exception:
            continue

    return fixtures


def get_odds_from_db(pipeline: DataPipeline, home: str, away: str,
                     league: str) -> dict:
    """
    Try to get odds from the most recent match between these teams,
    or from league average odds.
    """
    with sqlite3.connect(pipeline.db_path) as conn:
        conn.row_factory = sqlite3.Row
        # Look for odds in recent matches for these teams
        rows = conn.execute("""
            SELECT odds_h, odds_d, odds_a FROM matches
            WHERE league = ? AND odds_h IS NOT NULL
            ORDER BY date DESC LIMIT 50
        """, (league,)).fetchall()

    if rows:
        # Average recent odds for the league
        h_vals = [r['odds_h'] for r in rows if r['odds_h']]
        d_vals = [r['odds_d'] for r in rows if r['odds_d']]
        a_vals = [r['odds_a'] for r in rows if r['odds_a']]
        avg_h = sum(h_vals) / len(h_vals) if h_vals else 2.20
        avg_d = sum(d_vals) / len(d_vals) if d_vals else 3.30
        avg_a = sum(a_vals) / len(a_vals) if a_vals else 3.30
        return {'home': avg_h, 'draw': avg_d, 'away': avg_a}

    # Default neutral odds
    return {'home': 2.20, 'draw': 3.30, 'away': 3.30}


def fit_model(pipeline: DataPipeline, league: str,
              seasons_back: int = 3) -> DixonColesModel:
    """
    Fit Dixon-Coles model for a league using historical data.

    Args:
        pipeline: DataPipeline instance.
        league: League code.
        seasons_back: How many seasons to use for training.
    """
    season_start = current_season_start()
    seasons = []
    for i in range(seasons_back):
        year = season_start - i
        seasons.append(f"{year}-{year+1}")

    matches = []
    for season in seasons:
        rows = pipeline.get_matches(league=league, season=season)
        for r in rows:
            if r.get('hg') is not None and r.get('ag') is not None:
                matches.append({
                    'home': r['home'],
                    'away': r['away'],
                    'home_goals': r['hg'],
                    'away_goals': r['ag'],
                    'date': r['date'],
                })

    if len(matches) < 20:
        print(f"  Warning: Only {len(matches)} matches for {league} — model may be weak")

    model = DixonColesModel()
    if matches:
        model.fit(matches, time_decay_half_life=300.0)

    return model


def scan_league(pipeline: DataPipeline, league: str, value_engine: ValueEngine,
                rationale_gen: RationaleGenerator, max_picks: int = 3) -> list:
    """
    Scan one league for value picks.

    Returns list of pick dicts with rationale.
    """
    league_name = LEAGUES.get(league, league)
    print(f"\n📊 Scanning {league_name}...")

    # Get upcoming fixtures
    fixtures = get_upcoming_fixtures_espn(league)
    if not fixtures:
        print(f"  No upcoming fixtures found")
        return []

    print(f"  Found {len(fixtures)} upcoming fixtures")

    # Fit model
    model = fit_model(pipeline, league)
    if not model.fitted:
        print(f"  Model not fitted — skipping")
        return []

    picks = []
    for fix in fixtures:
        home = fix['home']
        away = fix['away']
        match_date = fix['date']

        # Build features
        features = FeatureFactory(pipeline.db_path)
        feat = features.build_features(home, away, league, match_date, include_elo=True)

        # Get team stats for rationale
        home_stats = pipeline.get_team_stats(home, league, last_n=5)
        away_stats = pipeline.get_team_stats(away, league, last_n=5)

        # Dixon-Coles prediction
        try:
            probs = model.predict(home, away)
        except Exception as e:
            print(f"  Model prediction failed for {home} vs {away}: {e}")
            continue

        # Get odds
        odds_data = get_odds_from_db(pipeline, home, away, league)

        # Find best pick
        best = value_engine.find_best_pick(home, away, probs, odds_data)
        if not best:
            print(f"  {home} vs {away}: No value found")
            continue

        # Generate rationale
        h2h = pipeline.get_h2h(home, away)
        rat = rationale_gen.generate(best, feat, h2h, home_stats, away_stats, probs)

        best['rationale'] = rat
        best['_league'] = league
        best['features'] = {
            'h_form5': home_stats.get('pts_per_game', 0),
            'a_form5': away_stats.get('pts_per_game', 0),
            'h_sot': home_stats.get('avg_sot', 0),
            'a_sot': away_stats.get('avg_sot', 0),
            'elo_diff': feat.get('elo_diff'),
        }
        best['model_probs'] = probs
        picks.append(best)
        print(f"  ✅ {home} vs {away}: {best['pick']} (EV: {best['ev']*100:.1f}%)")

    # Sort by EV and limit
    picks = sorted(picks, key=lambda x: -x['ev'])[:max_picks]
    return picks


def log_prediction(pick: Dict, league: str):
    """Log a prediction to the tracking database."""
    with sqlite3.connect(PREDICTIONS_DB) as conn:
        conn.execute("""
            INSERT INTO predictions
            (date, league, home, away, market, pick, odds,
             p_model, p_market, ev, kelly,
             confidence_score, confidence_label, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            datetime.utcnow().strftime('%Y-%m-%d'),
            league,
            pick.get('match', '').split(' vs ')[0],
            pick.get('match', '').split(' vs ')[-1],
            pick.get('market'),
            pick.get('pick'),
            pick.get('odds'),
            pick.get('p_model'),
            pick.get('p_market'),
            pick.get('ev'),
            pick.get('kelly'),
            pick.get('confidence', {}).get('score'),
            pick.get('confidence', {}).get('label'),
            datetime.utcnow().isoformat(),
        ))
        conn.commit()


def format_telegram_output(picks: list, league: str) -> str:
    """Format picks for Telegram delivery."""
    if not picks:
        return f"🟢 *SabiAI v2* — No value picks found today"

    league_name = LEAGUES.get(league, league)
    now = datetime.utcnow().strftime('%a %d %b %Y')

    lines = [f"🟢 *SabiAI v2 — {now}*", f"📊 {league_name}", ""]

    for i, pick in enumerate(picks, 1):
        conf = pick.get('confidence', {})
        emoji = '🟢' if conf.get('label') == 'STRONG' else \
                '🟡' if conf.get('label') == 'SOLID' else '⚪'

        lines.append(f"{emoji} *{pick.get('match', '?')}*")
        lines.append(f"📌 {pick['market']}: {pick['pick']}")
        lines.append(f"📊 Odds: {pick['odds']} | Model: {pick['p_model']*100:.0f}%")
        lines.append(f"💰 EV: {pick['ev']*100:.1f}% | Kelly: {pick['kelly']*100:.1f}%")
        lines.append(f"⭐ {conf.get('score', 0)}/100 ({conf.get('label', '?')})")

        # Brief rationale
        feat = pick.get('features', {})
        if feat:
            parts = []
            if feat.get('h_form5'):
                parts.append(f"Home form: {feat['h_form5']} pts/g")
            if feat.get('a_form5'):
                parts.append(f"Away form: {feat['a_form5']} pts/g")
            if feat.get('elo_diff'):
                parts.append(f"Elo diff: {feat['elo_diff']:.0f}")
            if parts:
                lines.append("📋 " + " | ".join(parts))

        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description='SabiAI v2 — Stats-based football value finder')
    parser.add_argument('--league', type=str, help='League code (e.g., E0)')
    parser.add_argument('--max-picks', type=int, default=3, help='Max picks per league')
    parser.add_argument('--min-ev', type=float, default=0.03, help='Minimum EV threshold')
    parser.add_argument('--format', choices=['telegram', 'plain', 'json'], default='plain')
    parser.add_argument('--update-data', action='store_true', help='Download fresh data first')
    parser.add_argument('--backfill', action='store_true', help='Backfill DB for all leagues')
    args = parser.parse_args()

    os.makedirs(DATA_DIR, exist_ok=True)
    pipeline = DataPipeline(DB_PATH)
    init_predictions_db()

    if args.update_data or args.backfill:
        leagues = [args.league] if args.league else list(LEAGUES.keys())
        pipeline.update(leagues=leagues, seasons_back=3)
        print("\n✅ Data update complete")

    if args.backfill:
        return

    # Determine leagues to scan
    if args.league:
        leagues = [args.league]
    else:
        # Default: scan top 5 European leagues
        leagues = ['E0', 'SP1', 'I1', 'D1', 'F1']

    value_engine = ValueEngine(min_ev=args.min_ev)
    rationale_gen = RationaleGenerator(DB_PATH)

    all_picks = []
    for league in leagues:
        picks = scan_league(pipeline, league, value_engine, rationale_gen,
                            max_picks=args.max_picks)
        for p in picks:
            log_prediction(p, league)
        all_picks.extend(picks)

    # Dedup across leagues (one pick per unique match)
    seen_matches = set()
    deduped = []
    for p in sorted(all_picks, key=lambda x: -x['ev']):
        match = p.get('match', '')
        if match not in seen_matches:
            seen_matches.add(match)
            deduped.append(p)

    # Output
    if args.format == 'telegram':
        for league in leagues:
            league_picks = [p for p in deduped if p.get('_league') == league]
            if league_picks:
                print(format_telegram_output(league_picks, league))

    elif args.format == 'json':
        print(json.dumps(deduped, indent=2, default=str))

    else:
        if not deduped:
            print("No value picks found today.")
        else:
            print(f"\n{'='*50}")
            print(f"SabiAI v2 — {len(deduped)} picks found")
            print(f"{'='*50}")
            for p in deduped:
                print(f"\n{p.get('rationale', '')}")


if __name__ == '__main__':
    main()
