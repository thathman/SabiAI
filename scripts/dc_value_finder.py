#!/usr/bin/env python3
"""Quick DC (Double Chance) value bet finder using Elo model + FDCO odds."""
import sys, os, json, math, datetime, urllib.request

sys.path.insert(0, os.path.dirname(__file__))
from value_bet_finder import elo_probs, get_elo, _load_intl_elo

API_KEY = os.environ.get("ODDS_API_KEY", "")
SEASONS = {
    "E0": "4", "E1": "4", "SP1": "4", "I1": "4", "D1": "4", "F1": "4",
    "N1": "4", "P1": "4", "B1": "4", "T1": "4", "SC0": "4",
    "E2": "4", "SP2": "4", "I2": "4", "D2": "4", "F2": "4",
}

FDCO_BASE = "https://www.football-data.co.uk/mmz4281"

DC_LABELS = {
    ("home", "draw"): "1X", ("away", "draw"): "X2", ("home", "away"): "12"
}

def fetch_odds(fdco_code):
    season = SEASONS.get(fdco_code, "4")
    url = f"{FDCO_BASE}/{season}/{fdco_code}.csv"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        resp = urllib.request.urlopen(req, timeout=15)
        lines = resp.read().decode("utf-8", errors="replace").split("\n")
        return lines
    except Exception as e:
        return []

def parse_csv(lines):
    """Parse FDCO CSV. Find headers with DC odds (AvgH, AvgD, AvgA for 1X2; plus DC columns if available)."""
    import csv, io
    if not lines or len(lines) < 3:
        return []
    
    # Find header row (starts with Div)
    header_idx = None
    for i, line in enumerate(lines):
        if line.startswith("Div,"):
            header_idx = i
            break
    if header_idx is None:
        return []
    
    reader = csv.DictReader(lines[header_idx:])
    matches = []
    for row in reader:
        try:
            div = row.get("Div", "")
            home = row.get("HomeTeam", "").strip()
            away = row.get("AwayTeam", "").strip()
            if not home or not away:
                continue
            
            # 1X2 odds
            h_odds = row.get("AvgH", "") or row.get("B365H", "")
            d_odds = row.get("AvgD", "") or row.get("B365D", "")
            a_odds = row.get("AvgA", "") or row.get("B365A", "")
            
            if not all([h_odds, d_odds, a_odds]):
                continue
            
            h_odds = float(h_odds)
            d_odds = float(d_odds)
            a_odds = float(a_odds)
            
            # Check for kickoff (Date, Time columns)
            date_str = row.get("Date", "")
            time_str = row.get("Time", "")
            
            matches.append({
                "div": div, "home": home, "away": away,
                "h_odds": h_odds, "d_odds": d_odds, "a_odds": a_odds,
                "date": date_str, "time": time_str,
            })
        except (ValueError, KeyError):
            continue
    return matches

def compute_dc_odds(win_price, draw_price):
    """Fair DC odds from 1X2 prices (harmonic combination)."""
    if win_price <= 1 or draw_price <= 1:
        return 0
    return round(1.0 / (1.0 / win_price + 1.0 / draw_price), 4)

def main():
    all_picks = []
    now = datetime.datetime.utcnow()
    
    for code in SEASONS:
        lines = fetch_odds(code)
        if not lines:
            continue
        matches = parse_csv(lines)
        
        for m in matches:
            home, away = m["home"], m["away"]
            h_odds, d_odds, a_odds = m["h_odds"], m["d_odds"], m["a_odds"]
            
            # Get model probabilities
            try:
                probs = elo_probs(home, away)
            except Exception:
                continue
            
            p_home = probs["home"]
            p_draw = probs["draw"]
            p_away = probs["away"]
            
            if p_home is None or p_draw is None or p_away is None:
                continue
            
            # Compute implied probabilities from odds
            imp_h = 1.0 / h_odds
            imp_d = 1.0 / d_odds
            imp_a = 1.0 / a_odds
            margin = imp_h + imp_d + imp_a - 1.0
            
            # Remove margin proportionally
            norm_h = imp_h / (1 + margin)
            norm_d = imp_d / (1 + margin)
            norm_a = imp_a / (1 + margin)
            
            # DC fair odds from bookmaker
            dc_1x_odds = compute_dc_odds(h_odds, d_odds)
            dc_x2_odds = compute_dc_odds(d_odds, a_odds)
            dc_12_odds = compute_dc_odds(h_odds, a_odds)
            
            # DC probabilities from model
            dc_1x_prob = p_home + p_draw
            dc_x2_prob = p_draw + p_away
            dc_12_prob = p_home + p_away
            
            # DC implied probs from bookmaker
            dc_1x_imp = norm_h + norm_d
            dc_x2_imp = norm_d + norm_a
            dc_12_imp = norm_h + norm_a
            
            results = []
            for label, model_prob, book_prob, book_odds in [
                ("1X", dc_1x_prob, dc_1x_imp, dc_1x_odds),
                ("X2", dc_x2_prob, dc_x2_imp, dc_x2_odds),
                ("12", dc_12_prob, dc_12_imp, dc_12_odds),
            ]:
                if book_odds <= 1 or book_prob <= 0:
                    continue
                ev = (model_prob * book_odds) - 1.0
                kelly = (model_prob * book_odds - 1.0) / (book_odds - 1.0) if book_odds > 1 else 0
                
                if ev > 0.01:  # At least 1% EV
                    results.append({
                        "dc": label,
                        "model_prob": round(model_prob * 100, 1),
                        "book_odds": book_odds,
                        "ev": round(ev * 100, 1),
                        "kelly": round(kelly * 100, 1),
                    })
            
            if results:
                best = max(results, key=lambda x: x["ev"])
                all_picks.append({
                    "match": f"{home} vs {away}",
                    "league": m["div"],
                    "date": m["date"],
                    "time": m["time"],
                    "best_dc": best,
                    "all_dcs": sorted(results, key=lambda x: -x["ev"]),
                    "model_1x2": {"home": round(p_home*100,1), "draw": round(p_draw*100,1), "away": round(p_away*100,1)},
                    "odds_1x2": {"home": h_odds, "draw": d_odds, "away": a_odds},
                })
    
    # Sort by EV
    all_picks.sort(key=lambda x: -x["best_dc"]["ev"])
    
    print(f"\n{'='*60}")
    print(f"  DOUBLE CHANCE VALUE BETS — {now.strftime('%Y-%m-%d %H:%M')} UTC")
    print(f"{'='*60}\n")
    
    if not all_picks:
        print("No DC value bets found across all leagues.")
        return
    
    for i, p in enumerate(all_picks[:15], 1):
        dc = p["best_dc"]
        m = p["model_1x2"]
        o = p["odds_1x2"]
        print(f"{i}. {p['match']} ({p['league']}) [{p['date']} {p['time']}]")
        print(f"   DC Pick: {dc['dc']} | Odds: {dc['book_odds']} | EV: +{dc['ev']}% | Kelly: {dc['kelly']}%")
        print(f"   Model: H {m['home']}% D {m['draw']}% A {m['away']}%")
        print(f"   Book odds: H {o['home']} D {o['draw']} A {o['away']}")
        if len(p["all_dcs"]) > 1:
            alt = p["all_dcs"][1]
            print(f"   Alt: {alt['dc']} @ {alt['book_odds']} (EV +{alt['ev']}%)")
        print()
    
    print(f"Total DC value picks: {len(all_picks)}")

if __name__ == "__main__":
    main()
