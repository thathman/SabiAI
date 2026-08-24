#!/usr/bin/env python3
"""
value_bet_finder.py — Multi-sport value bet scanner with context intelligence.

Sources:
  - The Odds API       → live bookmaker odds (main + special markets)
  - ESPN hidden API    → team form, recent results
  - ClubElo API        → football Elo strength ratings
  - football-data.co.uk CSV → BTTS%, Over/Under%, corners, cards averages
  - Exa search API     → injury/suspension news

Value method:
  1. Strip vig from consensus → fair probability
  2. Build model probability (Elo + form + injury adjustments for football)
  3. EV = model_prob × best_odds − 1
  4. Kelly ¼ fraction for stake sizing

Special bets (football):
  - BTTS (from API btts market + historical BTTS% model)
  - Alternate goal totals (from API alternate_totals market)
  - Corners O/U model (from historical CSV, no API line needed)
  - Cards O/U model (from historical CSV, no API line needed)

Usage:
  python3 value_bet_finder.py                   # Mon–Sun current week, all sports
  python3 value_bet_finder.py --min-ev 0.05     # 5%+ edge only
  python3 value_bet_finder.py --sport soccer    # football only
  python3 value_bet_finder.py --format telegram # Telegram output
"""

import sys, os, json, csv, io, math, argparse, sqlite3, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import plain_render
import learn
import apifootball as APIF
import sofascore as SOFA
import sportsbook as SBOOK
import nfl_elo as NFLELO
import sportsgambler as SGAMBLER
import bettingstats as BSTATS
try:
    import sportybet_odds as SBODDS   # read-only odds for non-Rundown leagues
except Exception:
    SBODDS = None
import urllib.request, urllib.parse
from datetime import datetime, timezone, timedelta
from collections import defaultdict

# ── Config ────────────────────────────────────────────────────────────────────

RUNDOWN_BASE   = "https://therundown.io/api/v2"
ESPN_BASE      = "https://site.api.espn.com/apis/site/v2/sports/soccer"
CLUBELO_BASE   = "http://api.clubelo.com"
EXA_BASE       = "https://api.exa.ai/search"
FDCO_BASE      = "https://www.football-data.co.uk/mmz4281"

KELLY_FRACTION = 0.25
DEFAULT_MIN_EV = 0.03
MAX_EV_PCT = 30.0        # drop picks with EV > this — model is wildly wrong
MAX_PROB_DIVERGENCE = 25.0  # drop picks where |our_prob - market_prob| > this%


def _sanity_filter(bets):
    """Drop picks with absurd EV or excessive model/market divergence.
    Model-only picks (no live odds) pass through unchanged."""
    out = []
    for b in bets:
        if b.get("is_model_only") or b.get("ev") is None:
            out.append(b)
            continue
        if b["ev"] > MAX_EV_PCT:
            continue
        our = b.get("our_prob")
        mkt = b.get("market_prob")
        if our is not None and mkt is not None and abs(our - mkt) > MAX_PROB_DIVERGENCE:
            continue
        out.append(b)
    return out

# Dynamic sport groups — at runtime, ALL active API sports in these groups are scanned.
# This covers: any tennis tournament (ATP/WTA 250/500/1000/Slam), any boxing card,
# any MMA event, without needing to hardcode each tournament.
DYNAMIC_GROUPS = {
    "Tennis":           {"label_prefix": "🎾", "specials": False},
    "Boxing":           {"label_prefix": "🥊", "specials": False},
    "Mixed Martial Arts": {"label_prefix": "🥊", "specials": False},
}

# Sports to scan → Odds API key, ESPN slug, FDCO code, label, specials flag
# "specials": True = fetch event-level btts/alt_totals (football only, costs more credits)
# Season notes are for awareness — scanner skips automatically when no events are live
SPORTS_CONFIG = {
    # ═══════════════════════════════════════════════════════════════════════════
    # FOOTBALL / SOCCER — All accessible leagues worldwide
    # espn       = league slug used in soccer ESPN URL + form/Elo fetchers
    # espn_path  = full path for generic ESPN scoreboard (all sports)
    # ═══════════════════════════════════════════════════════════════════════════

    # ── Europe Tier 1 ──────────────────────────────────────────────────────
    "soccer_epl":                      {"espn": "eng.1",              "espn_path": "soccer/eng.1",              "fdco": "E0",  "label": "⚽ EPL",                    "specials": True},
    "soccer_england_championship":     {"espn": "eng.2",              "espn_path": "soccer/eng.2",              "fdco": "E1",  "label": "⚽ ENG Championship",        "specials": False},
    "soccer_england_league_one":       {"espn": "eng.3",              "espn_path": "soccer/eng.3",              "fdco": "E2",  "label": "⚽ ENG League One",          "specials": False},
    "soccer_england_league_two":       {"espn": "eng.4",              "espn_path": "soccer/eng.4",              "fdco": "E3",  "label": "⚽ ENG League Two",          "specials": False},
    "soccer_spain_la_liga":            {"espn": "esp.1",              "espn_path": "soccer/esp.1",              "fdco": "SP1", "label": "⚽ La Liga",                 "specials": True},
    "soccer_spain_segunda_division":   {"espn": "esp.2",              "espn_path": "soccer/esp.2",              "fdco": "SP2", "label": "⚽ La Liga 2",               "specials": False},
    "soccer_italy_serie_a":            {"espn": "ita.1",              "espn_path": "soccer/ita.1",              "fdco": "I1",  "label": "⚽ Serie A",                 "specials": True},
    "soccer_italy_serie_b":            {"espn": "ita.2",              "espn_path": "soccer/ita.2",              "fdco": "I2",  "label": "⚽ Serie B",                 "specials": False},
    "soccer_germany_bundesliga":       {"espn": "ger.1",              "espn_path": "soccer/ger.1",              "fdco": "D1",  "label": "⚽ Bundesliga",              "specials": True},
    "soccer_germany_bundesliga2":      {"espn": "ger.2",              "espn_path": "soccer/ger.2",              "fdco": "D2",  "label": "⚽ 2. Bundesliga",           "specials": False},
    "soccer_france_ligue_one":         {"espn": "fra.1",              "espn_path": "soccer/fra.1",              "fdco": "F1",  "label": "⚽ Ligue 1",                "specials": True},
    "soccer_france_ligue_two":         {"espn": "fra.2",              "espn_path": "soccer/fra.2",              "fdco": "F2",  "label": "⚽ Ligue 2",                "specials": False},
    "soccer_netherlands_eredivisie":   {"espn": "ned.1",              "espn_path": "soccer/ned.1",              "fdco": "N1",  "label": "⚽ Eredivisie",              "specials": False},
    "soccer_portugal_primeira_liga":   {"espn": "por.1",              "espn_path": "soccer/por.1",              "fdco": "P1",  "label": "⚽ Primeira Liga",           "specials": False},
    "soccer_scotland_premiership":     {"espn": "sco.1",              "espn_path": "soccer/sco.1",              "fdco": "SC0", "label": "⚽ Scottish Prem",           "specials": False},
    "soccer_turkey_super_lig":         {"espn": "tur.1",              "espn_path": "soccer/tur.1",              "fdco": "T1",  "label": "⚽ Suer Lig",              "specials": False},
    "soccer_belgium_first_div_a":      {"espn": "bel.1",              "espn_path": "soccer/bel.1",              "fdco": "B1",  "label": "⚽ Belgian Pro League",      "specials": False},
    "soccer_greece_super_league":      {"espn": "gre.1",              "espn_path": "soccer/gre.1",              "fdco": "G1",  "label": "⚽ Greek Super League",      "specials": False},
    "soccer_austria_bundesliga":       {"espn": "aut.1",              "espn_path": "soccer/aut.1",              "fdco": None,  "label": "⚽ Austrian Bundesliga",     "specials": False},
    "soccer_czech_liga":               {"espn": "cze.1",              "espn_path": "soccer/cze.1",              "fdco": None,  "label": "⚽ Czech Liga",              "specials": False},
    "soccer_russia_premier_league":    {"espn": "rus.1",              "espn_path": "soccer/rus.1",              "fdco": None,  "label": "⚽ Russian Premier",         "specials": False},
    "soccer_denmark_superliga":        {"espn": "den.1",              "espn_path": "soccer/den.1",              "fdco": None,  "label": "⚽ Danish Superliga",        "specials": False},
    "soccer_sweden_allsvenskan":       {"espn": "swe.1",              "espn_path": "soccer/swe.1",              "fdco": None,  "label": "⚽ Allsvenskan",             "specials": False},
    "soccer_norway_eliteserien":       {"espn": "nor.1",              "espn_path": "soccer/nor.1",              "fdco": None,  "label": "⚽ Eliteserien",             "specials": False},
    "soccer_switzerland_super_league": {"espn": "sui.1",              "espn_path": "soccer/sui.1",              "fdco": None,  "label": "⚽ Swiss Super League",      "specials": False},
    "soccer_croatia_hnl":              {"espn": "cro.1",              "espn_path": "soccer/cro.1",              "fdco": None,  "label": "⚽ Croatian HNL",            "specials": False},
    "soccer_serbia_superliga":         {"espn": "srb.1",              "espn_path": "soccer/srb.1",              "fdco": None,  "label": "⚽ Serbian SuperLiga",       "specials": False},
    "soccer_ukraine_premier_league":   {"espn": "ukr.1",              "espn_path": "soccer/ukr.1",              "fdco": None,  "label": "⚽ Ukrainian Premier",       "specials": False},
    "soccer_romania_liga_1":           {"espn": "rou.1",              "espn_path": "soccer/rou.1",              "fdco": None,  "label": "⚽ Liga 1 Romania",          "specials": False},
    "soccer_poland_ekstraklasa":       {"espn": "pol.1",              "espn_path": "soccer/pol.1",              "fdco": None,  "label": "⚽ Ekstraklasa",             "specials": False},
    "soccer_hungary_nb1":              {"espn": "hun.1",              "espn_path": "soccer/hun.1",              "fdco": None,  "label": "⚽ Hungarian NB1",           "specials": False},
    "soccer_slovakia_super_liga":      {"espn": "svk.1",              "espn_path": "soccer/svk.1",              "fdco": None,  "label": "⚽ Slovak Super Liga",       "specials": False},

    # ── Europe Cups ──────────────────────────────────────────────────────
    "soccer_uefa_champs_league":       {"espn": "uefa.champions",     "espn_path": "soccer/uefa.champions",     "fdco": None,  "label": "⚽ UCL",                    "specials": True},
    "soccer_uefa_europa_league":       {"espn": "uefa.europa",        "espn_path": "soccer/uefa.europa",        "fdco": None,  "label": "⚽ UEL",                    "specials": True},
    "soccer_uefa_conf_league":         {"espn": "uefa.europa.conf",   "espn_path": "soccer/uefa.europa.conf",   "fdco": None,  "label": "⚽ UECL",                   "specials": False},
    "soccer_england_fa_cup":           {"espn": "eng.fa",             "espn_path": "soccer/eng.fa",             "fdco": None,  "label": "⚽ FA Cup",                  "specials": False},
    "soccer_england_league_cup":       {"espn": "eng.league_cup",     "espn_path": "soccer/eng.league_cup",     "fdco": None,  "label": "⚽ EFL Cup",                 "specials": False},
    "soccer_spain_copa_del_rey":       {"espn": "esp.copa_del_rey",   "espn_path": "soccer/esp.copa_del_rey",   "fdco": None,  "label": "⚽ Copa del Rey",            "specials": False},
    "soccer_italy_coppa_italia":       {"espn": "ita.coppa_italia",   "espn_path": "soccer/ita.coppa_italia",   "fdco": None,  "label": "⚽ Coppa Italia",            "specials": False},
    "soccer_germany_dfb_pokal":        {"espn": "ger.dfb_pokal",      "espn_path": "soccer/ger.dfb_pokal",      "fdco": None,  "label": "⚽ DFB-Pokal",               "specials": False},
    "soccer_france_coupe_de_france":   {"espn": "fra.coupe_de_france","espn_path": "soccer/fra.coupe_de_france","fdco": None,  "label": "⚽ Coupe de France",         "specials": False},

    # ── Americas ────────────────────────────────────────────────────────
    "soccer_brazil_campeonato":        {"espn": "bra.1",              "espn_path": "soccer/bra.1",              "fdco": None,  "label": "⚽ Brasileirao Serie A",    "specials": False},
    "soccer_brazil_serie_b":           {"espn": "bra.2",              "espn_path": "soccer/bra.2",              "fdco": None,  "label": "⚽ Brasileirao Serie B",    "specials": False},
    "soccer_argentina_primera":        {"espn": "arg.1",              "espn_path": "soccer/arg.1",              "fdco": None,  "label": "⚽ Argentine Primera",       "specials": False},
    "soccer_mexico_liga_mx":           {"espn": "mex.1",              "espn_path": "soccer/mex.1",              "fdco": None,  "label": "⚽ Liga MX",                 "specials": False},
    "soccer_colombia_primera":         {"espn": "col.1",              "espn_path": "soccer/col.1",              "fdco": None,  "label": "⚽ Colombian Primera A",     "specials": False},
    "soccer_chile_primera":            {"espn": "chi.1",              "espn_path": "soccer/chi.1",              "fdco": None,  "label": "⚽ Chilean Primera",         "specials": False},
    "soccer_ecuador_liga_pro":         {"espn": "ecu.1",              "espn_path": "soccer/ecu.1",              "fdco": None,  "label": "⚽ Ecuadorian Liga Pro",     "specials": False},
    "soccer_peru_primera":             {"espn": "per.1",              "espn_path": "soccer/per.1",              "fdco": None,  "label": "⚽ Peruvian Primera",        "specials": False},
    "soccer_uruguay_primera":          {"espn": "uru.1",              "espn_path": "soccer/uru.1",              "fdco": None,  "label": "⚽ Uruguayan Primera",       "specials": False},
    "soccer_venezuela_primera":        {"espn": "ven.1",              "espn_path": "soccer/ven.1",              "fdco": None,  "label": "⚽ Venezuelan Primera",      "specials": False},
    "soccer_paraguay_primera":         {"espn": "par.1",              "espn_path": "soccer/par.1",              "fdco": None,  "label": "⚽ Paraguayan Division",     "specials": False},
    "soccer_usa_mls":                  {"espn": "usa.1",              "espn_path": "soccer/usa.1",              "fdco": None,  "label": "⚽ MLS",                     "specials": False},
    "soccer_usa_usl":                  {"espn": "usa.2",              "espn_path": "soccer/usa.2",              "fdco": None,  "label": "⚽ USL Championship",        "specials": False},
    "soccer_conmebol_libertadores":    {"espn": "conmebol.libertadores","espn_path": "soccer/conmebol.libertadores","fdco": None,"label": "⚽ Copa Libertadores",     "specials": False},
    "soccer_conmebol_copa_sudamericana":{"espn": "conmebol.sudamericana","espn_path": "soccer/conmebol.sudamericana","fdco": None,"label": "⚽ Copa Sudamericana",    "specials": False},
    "soccer_concacaf_champions":       {"espn": "concacaf.champions", "espn_path": "soccer/concacaf.champions", "fdco": None,  "label": "⚽ CONCACAF Champions Cup",  "specials": False},

    # ── Asia / Pacific ───────────────────────────────────────────────────
    "soccer_japan_j1_league":          {"espn": "jpn.1",              "espn_path": "soccer/jpn.1",              "fdco": None,  "label": "⚽ J1 League (Japan)",       "specials": False},
    "soccer_japan_j2_league":          {"espn": "jpn.2",              "espn_path": "soccer/jpn.2",              "fdco": None,  "label": "⚽ J2 League (Japan)",       "specials": False},
    "soccer_south_korea_k_league":     {"espn": "kor.1",              "espn_path": "soccer/kor.1",              "fdco": None,  "label": "⚽ K League 1",              "specials": False},
    "soccer_china_super_league":       {"espn": "chn.1",              "espn_path": "soccer/chn.1",              "fdco": None,  "label": "⚽ Chinese Super League",    "specials": False},
    "soccer_australia_a_league":       {"espn": "aus.1",              "espn_path": "soccer/aus.1",              "fdco": None,  "label": "⚽ A-League (Australia)",    "specials": False},
    "soccer_india_isl":                {"espn": "ind.1",              "espn_path": "soccer/ind.1",              "fdco": None,  "label": "⚽ Indian Super League",     "specials": False},

    # ── Middle East / Africa ─────────────────────────────────────────────
    "soccer_saudi_pro_league":         {"espn": "sau.1",              "espn_path": "soccer/sau.1",              "fdco": None,  "label": "⚽ Saudi Pro League",        "specials": False},
    "soccer_uae_pro_league":           {"espn": "uae.1",              "espn_path": "soccer/uae.1",              "fdco": None,  "label": "⚽ UAE Pro League",          "specials": False},
    "soccer_egypt_premier_league":     {"espn": "egy.1",              "espn_path": "soccer/egy.1",              "fdco": None,  "label": "⚽ Egyptian Premier League", "specials": False},
    "soccer_nigeria_npfl":             {"espn": "nig.1",              "espn_path": "soccer/nig.1",              "fdco": None,  "label": "⚽ NPFL (Nigeria)",          "specials": False},
    "soccer_south_africa_psl":         {"espn": "rsa.1",              "espn_path": "soccer/rsa.1",              "fdco": None,  "label": "⚽ South African PSL",       "specials": False},
    "soccer_morocco_botola":           {"espn": "mar.1",              "espn_path": "soccer/mar.1",              "fdco": None,  "label": "⚽ Moroccan Botola",         "specials": False},

    # ── International / Tournaments ─────────────────────────────────────
    "soccer_fifa_world_cup":           {"espn": "fifa.worldcup",      "espn_path": "soccer/fifa.worldcup",      "fdco": None,  "label": "🌍 World Cup",               "specials": True},
    "soccer_international_friendlies": {"espn": "fifa.friendly",      "espn_path": "soccer/fifa.friendly",      "fdco": None,  "label": "⚽ Intl Friendlies",         "specials": False},
    "soccer_afcon":                    {"espn": "afr.nations",        "espn_path": "soccer/afr.nations",        "fdco": None,  "label": "⚽ AFCON",                   "specials": False},
    "soccer_copa_america":             {"espn": "conmebol.america",   "espn_path": "soccer/conmebol.america",   "fdco": None,  "label": "⚽ Copa America",            "specials": False},
    "soccer_euro":                     {"espn": "uefa.euro",          "espn_path": "soccer/uefa.euro",          "fdco": None,  "label": "⚽ UEFA Euros",              "specials": False},
    "soccer_concacaf_gold_cup":        {"espn": "concacaf.gold",      "espn_path": "soccer/concacaf.gold",      "fdco": None,  "label": "⚽ CONCACAF Gold Cup",       "specials": False},
    "soccer_world_cup_q_europe":       {"espn": "fifa.worldq.uefa",   "espn_path": "soccer/fifa.worldq.uefa",   "fdco": None,  "label": "⚽ WCQ Europe",              "specials": False},
    "soccer_world_cup_q_conmebol":     {"espn": "fifa.worldq.conmebol","espn_path": "soccer/fifa.worldq.conmebol","fdco": None, "label": "⚽ WCQ South America",       "specials": False},
    "soccer_world_cup_q_concacaf":     {"espn": "fifa.worldq.concacaf","espn_path": "soccer/fifa.worldq.concacaf","fdco": None, "label": "⚽ WCQ CONCACAF",            "specials": False},
    "soccer_world_cup_q_africa":       {"espn": "fifa.worldq.caf",    "espn_path": "soccer/fifa.worldq.caf",    "fdco": None,  "label": "⚽ WCQ Africa",              "specials": False},
    "soccer_world_cup_q_asia":         {"espn": "fifa.worldq.afc",    "espn_path": "soccer/fifa.worldq.afc",    "fdco": None,  "label": "⚽ WCQ Asia",                "specials": False},
    "soccer_ucl_qualifying":           {"espn": "uefa.champs.qual",   "espn_path": "soccer/uefa.champs.qual",   "fdco": None,  "label": "⚽ UCL Qualifying",          "specials": False},
    "soccer_uel_qualifying":           {"espn": "uefa.europa.qual",   "espn_path": "soccer/uefa.europa.qual",   "fdco": None,  "label": "⚽ UEL Qualifying",          "specials": False},
    "soccer_nations_league":           {"espn": "uefa.nations",       "espn_path": "soccer/uefa.nations",       "fdco": None,  "label": "⚽ UEFA Nations League",     "specials": False},
    "soccer_women_world_cup":          {"espn": "fifa.wwc",           "espn_path": "soccer/fifa.wwc",           "fdco": None,  "label": "⚽ Women's World Cup",       "specials": False},

    # ═══════════════════════════════════════════════════════════════════════════
    # BASKETBALL
    # ═══════════════════════════════════════════════════════════════════════════
    "basketball_nba":                  {"espn": None, "espn_path": "basketball/nba",                     "fdco": None, "label": "🏀 NBA",                     "specials": False},
    "basketball_nba_playoffs":         {"espn": None, "espn_path": "basketball/nba",                     "fdco": None, "label": "🏀 NBA Playoffs",            "specials": False},
    "basketball_wnba":                 {"espn": None, "espn_path": "basketball/wnba",                    "fdco": None, "label": "🏀 WNBA",                    "specials": False},
    "basketball_ncaab":                {"espn": None, "espn_path": "basketball/mens-college-basketball", "fdco": None, "label": "🏀 NCAAB",                   "specials": False},
    "basketball_euroleague":           {"espn": None, "espn_path": "basketball/euroleague",              "fdco": None, "label": "🏀 EuroLeague",              "specials": False},
    "basketball_nbl_australia":        {"espn": None, "espn_path": "basketball/nbl",                     "fdco": None, "label": "🏀 NBL (Australia)",         "specials": False},
    "basketball_nba_g_league":         {"espn": None, "espn_path": "basketball/nba-g-league",            "fdco": None, "label": "🏀 NBA G-League",            "specials": False},

    # ═══════════════════════════════════════════════════════════════════════════
    # BASEBALL — All countries
    # ═══════════════════════════════════════════════════════════════════════════
    "baseball_mlb":                    {"espn": None, "espn_path": "baseball/mlb",  "fdco": None, "label": "⚾ MLB",                      "specials": False},
    "baseball_mlb_playoffs":           {"espn": None, "espn_path": "baseball/mlb",  "fdco": None, "label": "⚾ MLB Playoffs",             "specials": False},
    "baseball_npb":                    {"espn": None, "espn_path": "baseball/npb",  "fdco": None, "label": "⚾ NPB (Japan)",              "specials": False},
    "baseball_kbo":                    {"espn": None, "espn_path": "baseball/kbo",  "fdco": None, "label": "⚾ KBO (Korea)",              "specials": False},
    "baseball_mexico_lmb":             {"espn": None, "espn_path": "baseball/lmb",  "fdco": None, "label": "⚾ LMB (Mexico)",             "specials": False},

    # ═══════════════════════════════════════════════════════════════════════════
    # ICE HOCKEY — All leagues
    # ═══════════════════════════════════════════════════════════════════════════
    "icehockey_nhl":                   {"espn": None, "espn_path": "hockey/nhl",               "fdco": None, "label": "🏒 NHL",                     "specials": False},
    "icehockey_nhl_playoffs":          {"espn": None, "espn_path": "hockey/nhl",               "fdco": None, "label": "🏒 NHL Playoffs",            "specials": False},
    "icehockey_ahl":                   {"espn": None, "espn_path": "hockey/ahl",               "fdco": None, "label": "🏒 AHL",                     "specials": False},
    "icehockey_khl":                   {"espn": None, "espn_path": "hockey/khl",               "fdco": None, "label": "🏒 KHL (Russia)",            "specials": False},
    "icehockey_shl":                   {"espn": None, "espn_path": "hockey/shl",               "fdco": None, "label": "🏒 SHL (Sweden)",            "specials": False},
    "icehockey_liiga":                 {"espn": None, "espn_path": "hockey/liiga",             "fdco": None, "label": "🏒 Liiga (Finland)",         "specials": False},
    "icehockey_del":                   {"espn": None, "espn_path": "hockey/del",               "fdco": None, "label": "🏒 DEL (Germany)",           "specials": False},
    "icehockey_nl":                    {"espn": None, "espn_path": "hockey/nl",                "fdco": None, "label": "🏒 NL (Switzerland)",        "specials": False},
    "icehockey_extraliga":             {"espn": None, "espn_path": "hockey/extraliga",         "fdco": None, "label": "🏒 Czech Extraliga",         "specials": False},
    "icehockey_hockeyallsvenskan":     {"espn": None, "espn_path": "hockey/hockeyallsvenskan", "fdco": None, "label": "🏒 HockeyAllsvenskan (SWE)","specials": False},
    "icehockey_iihf_worlds":           {"espn": None, "espn_path": "hockey/world-men",         "fdco": None, "label": "🏒 IIHF World Championship", "specials": False},

    # ═══════════════════════════════════════════════════════════════════════════
    # AMERICAN FOOTBALL
    # ═══════════════════════════════════════════════════════════════════════════
    "americanfootball_nfl":            {"espn": None, "espn_path": "football/nfl",             "fdco": None, "label": "🏈 NFL",                     "specials": False},
    "americanfootball_nfl_playoffs":   {"espn": None, "espn_path": "football/nfl",             "fdco": None, "label": "🏈 NFL Playoffs",            "specials": False},
    "americanfootball_ncaaf":          {"espn": None, "espn_path": "football/college-football", "fdco": None, "label": "🏈 NCAAF",                   "specials": False},
    "americanfootball_cfl":            {"espn": None, "espn_path": "football/cfl",             "fdco": None, "label": "🏈 CFL",                     "specials": False},
    "americanfootball_xfl":            {"espn": None, "espn_path": "football/xfl",             "fdco": None, "label": "🏈 XFL",                     "specials": False},

    # ═══════════════════════════════════════════════════════════════════════════
    # RUGBY LEAGUE
    # ═══════════════════════════════════════════════════════════════════════════
    "rugbyleague_nrl":                 {"espn": None, "espn_path": "rugby-league/nrl",         "fdco": None, "label": "🏉 NRL",                     "specials": False},
    "rugbyleague_nrl_state_of_origin": {"espn": None, "espn_path": "rugby-league/nrl",         "fdco": None, "label": "🏉 State of Origin",         "specials": False},
    "rugbyleague_super_league":        {"espn": None, "espn_path": "rugby-league/super-league","fdco": None, "label": "🏉 Super League (Rugby)",    "specials": False},

    # ═══════════════════════════════════════════════════════════════════════════
    # RUGBY UNION
    # ═══════════════════════════════════════════════════════════════════════════
    "rugbyunion_premiership":          {"espn": None, "espn_path": "rugby/premiership",        "fdco": None, "label": "🏉 Rugby Premiership (ENG)", "specials": False},
    "rugbyunion_urc":                  {"espn": None, "espn_path": "rugby/urc",                "fdco": None, "label": "🏉 URC (Rugby)",             "specials": False},
    "rugbyunion_top14":                {"espn": None, "espn_path": "rugby/top14",              "fdco": None, "label": "🏉 Top 14 (France Rugby)",   "specials": False},
    "rugbyunion_super_rugby":          {"espn": None, "espn_path": "rugby/super-rugby",        "fdco": None, "label": "🏉 Super Rugby Pacific",     "specials": False},
    "rugbyunion_test_match":           {"espn": None, "espn_path": "rugby/test-match",         "fdco": None, "label": "🏉 Rugby Test Match",        "specials": False},
    "rugbyunion_champions_cup":        {"espn": None, "espn_path": "rugby/champions-cup",      "fdco": None, "label": "🏉 Rugby Champions Cup",     "specials": False},

    # ═══════════════════════════════════════════════════════════════════════════
    # CRICKET — All formats
    # ═══════════════════════════════════════════════════════════════════════════
    "cricket_ipl":                     {"espn": None, "espn_path": "cricket/ipl",              "fdco": None, "label": "🏏 IPL",                     "specials": False},
    "cricket_t20_blast":               {"espn": None, "espn_path": "cricket/t20_blast",        "fdco": None, "label": "🏏 T20 Blast (England)",     "specials": False},
    "cricket_bbl":                     {"espn": None, "espn_path": "cricket/bbl",              "fdco": None, "label": "🏏 BBL (Australia)",         "specials": False},
    "cricket_psl":                     {"espn": None, "espn_path": "cricket/psl",              "fdco": None, "label": "🏏 PSL (Pakistan)",          "specials": False},
    "cricket_sa20":                    {"espn": None, "espn_path": "cricket/sa20",             "fdco": None, "label": "🏏 SA20 (South Africa)",     "specials": False},
    "cricket_cpl":                     {"espn": None, "espn_path": "cricket/cpl",              "fdco": None, "label": "🏏 CPL (Caribbean)",         "specials": False},
    "cricket_icc_t20_wc":              {"espn": None, "espn_path": "cricket/icc-mens-t20",     "fdco": None, "label": "🏏 ICC T20 World Cup",       "specials": False},
    "cricket_icc_odi_wc":              {"espn": None, "espn_path": "cricket/icc-mens-odi",     "fdco": None, "label": "🏏 ICC ODI World Cup",       "specials": False},
    "cricket_icc_test":                {"espn": None, "espn_path": "cricket/international",    "fdco": None, "label": "🏏 International Cricket",   "specials": False},

    # ═══════════════════════════════════════════════════════════════════════════
    # AUSSIE RULES
    # ═══════════════════════════════════════════════════════════════════════════
    "aussierules_afl":                 {"espn": None, "espn_path": "australian-football/afl",  "fdco": None, "label": "🏑 AFL",                    "specials": False},
    "aussierules_aflw":                {"espn": None, "espn_path": "australian-football/aflw", "fdco": None, "label": "🏑 AFLW",                   "specials": False},

    # ═══════════════════════════════════════════════════════════════════════════
    # COMBAT SPORTS
    # ═══════════════════════════════════════════════════════════════════════════
    "mma_mixed_martial_arts":          {"espn": None, "espn_path": "mma/ufc",                  "fdco": None, "label": "🥊 MMA / UFC",              "specials": False},
    "mma_bellator":                    {"espn": None, "espn_path": "mma/bellator",             "fdco": None, "label": "🥊 Bellator MMA",           "specials": False},
    "mma_one_championship":            {"espn": None, "espn_path": "mma/one",                  "fdco": None, "label": "🥊 ONE Championship",       "specials": False},
    "boxing_boxing":                   {"espn": None, "espn_path": "boxing",                   "fdco": None, "label": "🥊 Boxing",                  "specials": False},

    # ═══════════════════════════════════════════════════════════════════════════
    # TENNIS
    # ═══════════════════════════════════════════════════════════════════════════
    "tennis_atp":                      {"espn": None, "espn_path": "tennis/atp",               "fdco": None, "label": "🎾 ATP",                    "specials": False},
    "tennis_wta":                      {"espn": None, "espn_path": "tennis/wta",               "fdco": None, "label": "🎾 WTA",                    "specials": False},

    # ═══════════════════════════════════════════════════════════════════════════
    # HANDBALL
    # ═══════════════════════════════════════════════════════════════════════════
    "handball_germany_bundesliga":     {"espn": None, "espn_path": None, "fdco": None, "label": "🤾 Handball Bundesliga",      "specials": False},
    "handball_champions_league":       {"espn": None, "espn_path": None, "fdco": None, "label": "🤾 EHF Champions League",    "specials": False},
    "handball_france_starligue":       {"espn": None, "espn_path": None, "fdco": None, "label": "🤾 Starligue (France)",      "specials": False},
    "handball_spain_asobal":           {"espn": None, "espn_path": None, "fdco": None, "label": "🤾 Asobal (Spain)",          "specials": False},
    "handball_denmark_handbold":       {"espn": None, "espn_path": None, "fdco": None, "label": "🤾 Danish Handbold",         "specials": False},
    "handball_world_championship":     {"espn": None, "espn_path": None, "fdco": None, "label": "🤾 Handball World Champ",    "specials": False},

    # ═══════════════════════════════════════════════════════════════════════════
    # VOLLEYBALL
    # ═══════════════════════════════════════════════════════════════════════════
    "volleyball_nations_league":       {"espn": None, "espn_path": None, "fdco": None, "label": "🏐 VNL (Volleyball Nations League)", "specials": False},
    "volleyball_brazil_superliga":     {"espn": None, "espn_path": None, "fdco": None, "label": "🏐 Brazilian Superliga",             "specials": False},
    "volleyball_italy_superlega":      {"espn": None, "espn_path": None, "fdco": None, "label": "🏐 Italian Superlega",               "specials": False},
    "volleyball_champions_league":     {"espn": None, "espn_path": None, "fdco": None, "label": "🏐 CEV Champions League",            "specials": False},
    "volleyball_world_championship":   {"espn": None, "espn_path": None, "fdco": None, "label": "🏐 FIVB World Championship",         "specials": False},
    "volleyball_poland_plusliga":      {"espn": None, "espn_path": None, "fdco": None, "label": "🏐 Polish PlusLiga",                 "specials": False},

    # ═══════════════════════════════════════════════════════════════════════════
    # TABLE TENNIS
    # ═══════════════════════════════════════════════════════════════════════════
    "tabletennis_wtt_contender":       {"espn": None, "espn_path": None, "fdco": None, "label": "🏓 WTT Contender",             "specials": False},
    "tabletennis_wtt_star_contender":  {"espn": None, "espn_path": None, "fdco": None, "label": "🏓 WTT Star Contender",        "specials": False},
    "tabletennis_world_championship":  {"espn": None, "espn_path": None, "fdco": None, "label": "🏓 Table Tennis World Champ",  "specials": False},
    "tabletennis_t_league_japan":      {"espn": None, "espn_path": None, "fdco": None, "label": "🏓 T-League (Japan)",          "specials": False},

    # ═══════════════════════════════════════════════════════════════════════════
    # ESPORTS
    # ═══════════════════════════════════════════════════════════════════════════
    "esports_lol":                     {"espn": None, "espn_path": "esports/lol",              "fdco": None, "label": "🎮 LoL Esports",            "specials": False},
    "esports_cs2":                     {"espn": None, "espn_path": "esports/cs2",              "fdco": None, "label": "🎮 CS2",                    "specials": False},
    "esports_valorant":                {"espn": None, "espn_path": "esports/valorant",         "fdco": None, "label": "🎮 Valorant",               "specials": False},
    "esports_dota2":                   {"espn": None, "espn_path": "esports/dota2",            "fdco": None, "label": "🎮 Dota 2",                 "specials": False},
    "esports_overwatch":               {"espn": None, "espn_path": "esports/overwatch",        "fdco": None, "label": "🎮 Overwatch League",       "specials": False},

    # ═══════════════════════════════════════════════════════════════════════════
    # GOLF
    # ═══════════════════════════════════════════════════════════════════════════
    "golf_pga":                        {"espn": None, "espn_path": "golf/pga",                 "fdco": None, "label": "⛳ PGA Tour",               "specials": False},
    "golf_euro":                       {"espn": None, "espn_path": "golf/euro",                "fdco": None, "label": "⛳ DP World Tour",          "specials": False},
    "golf_lpga":                       {"espn": None, "espn_path": "golf/lpga",                "fdco": None, "label": "⛳ LPGA Tour",              "specials": False},

    # ═══════════════════════════════════════════════════════════════════════════
    # MOTORSPORTS
    # ═══════════════════════════════════════════════════════════════════════════
    "motorsports_f1":                  {"espn": None, "espn_path": "racing/f1",                "fdco": None, "label": "🏎 Formula 1",             "specials": False},
    "motorsports_nascar":              {"espn": None, "espn_path": "racing/nascar",            "fdco": None, "label": "🏎 NASCAR Cup",             "specials": False},
    "motorsports_indycar":             {"espn": None, "espn_path": "racing/indycar",           "fdco": None, "label": "🏎 IndyCar",               "specials": False},
    "motorsports_motogp":              {"espn": None, "espn_path": "racing/motogp",            "fdco": None, "label": "🏎 MotoGP",                "specials": False},

    # ═══════════════════════════════════════════════════════════════════════════
    # DARTS
    # ═══════════════════════════════════════════════════════════════════════════
    "darts_pdc_world":                 {"espn": None, "espn_path": None, "fdco": None, "label": "🎯 PDC World Championship",   "specials": False},
    "darts_pdc_premier_league":        {"espn": None, "espn_path": None, "fdco": None, "label": "🎯 Premier League Darts",     "specials": False},
    "darts_pdc_masters":               {"espn": None, "espn_path": None, "fdco": None, "label": "🎯 Masters Darts",           "specials": False},
    "darts_pdc_players_championship":  {"espn": None, "espn_path": None, "fdco": None, "label": "🎯 Players Championship",    "specials": False},

    # ═══════════════════════════════════════════════════════════════════════════
    # SNOOKER
    # ═══════════════════════════════════════════════════════════════════════════
    "snooker_world_championship":      {"espn": None, "espn_path": None, "fdco": None, "label": "🎱 Snooker World Championship","specials": False},
    "snooker_masters":                 {"espn": None, "espn_path": None, "fdco": None, "label": "🎱 Snooker Masters",          "specials": False},
    "snooker_uk_championship":         {"espn": None, "espn_path": None, "fdco": None, "label": "🎱 UK Championship",          "specials": False},
    "snooker_ranking_events":          {"espn": None, "espn_path": None, "fdco": None, "label": "🎱 Snooker Ranking Events",   "specials": False},

    # ═══════════════════════════════════════════════════════════════════════════
    # CYCLING
    # ═══════════════════════════════════════════════════════════════════════════
    "cycling_tour_de_france":          {"espn": None, "espn_path": "cycling/tour-de-france",   "fdco": None, "label": "🚴 Tour de France",         "specials": False},
    "cycling_giro":                    {"espn": None, "espn_path": "cycling/giro",             "fdco": None, "label": "🚴 Giro d'Italia",          "specials": False},
    "cycling_vuelta":                  {"espn": None, "espn_path": "cycling/vuelta",           "fdco": None, "label": "🚴 Vuelta a Espana",        "specials": False},
}

# Sharp books by TheRundown affiliate key — weighted ×2 in consensus
SHARP_BOOKS = {"pinnacle", "lowvig", "matchbook", "betfair", "unibet_eu"}

# TheRundown V2 sport IDs — primary odds source (403 fallback: ESPN via espn_path)
RUNDOWN_SPORT_IDS = {
    # American Football
    "americanfootball_ncaaf":         1,
    "americanfootball_nfl":           2,
    "americanfootball_nfl_playoffs":  26,
    # Baseball
    "baseball_mlb":                   3,
    "baseball_mlb_playoffs":         31,
    # Basketball
    "basketball_nba":                 4,
    "basketball_nba_playoffs":       24,
    "basketball_ncaab":               5,
    "basketball_wnba":                8,
    "basketball_euroleague":         36,
    # Hockey
    "icehockey_nhl":                  6,
    "icehockey_nhl_playoffs":        28,
    # Combat
    "mma_mixed_martial_arts":         7,
    "boxing_boxing":                  9,
    # Soccer
    "soccer_usa_mls":                10,
    "soccer_epl":                    11,
    "soccer_france_ligue_one":       12,
    "soccer_germany_bundesliga":     13,
    "soccer_spain_la_liga":          14,
    "soccer_italy_serie_a":          15,
    "soccer_uefa_champs_league":     16,
    "soccer_fifa_world_cup":         18,   # Jun–Jul 2026
    "soccer_japan_j1_league":        19,   # Rundown covers J1 — in season Feb–Dec
    "soccer_uefa_europa_league":     33,
    "soccer_netherlands_eredivisie": 34,
    "soccer_portugal_primeira_liga": 35,
    "soccer_australia_a_league":     37,
    # Cricket
    "cricket_ipl":                   20,
    "cricket_t20_blast":             21,
    "cricket_icc_test":              22,
    "cricket_icc_odi_wc":            23,
    # Rugby / Aussie
    "rugbyleague_nrl":               25,
    "aussierules_afl":               27,
    # Tennis: ATP=38, WTA=39 — handled via prefix match in scan_sport
}

# Affiliate IDs → (key, display name). Pinnacle(3), LowVig(11), Matchbook(16) = sharp
RUNDOWN_AFFILIATES = {
    "2":  ("bovada",     "Bovada"),
    "3":  ("pinnacle",   "Pinnacle"),
    "4":  ("sportsbetting", "SportsBetting"),
    "6":  ("betonline",  "BetOnline"),
    "11": ("lowvig",     "LowVig"),
    "12": ("bodog",      "Bodog"),
    "16": ("matchbook",  "Matchbook"),
    "19": ("draftkings", "DraftKings"),
    "21": ("unibet_eu",  "Unibet"),
    "22": ("betmgm",     "BetMGM"),
    "23": ("fanduel",    "FanDuel"),
}

# Affiliates to request — sharp books + major US books. Keeps data-point cost low.
RUNDOWN_AFFILIATE_IDS = "3,11,16,19,21,22,23"

# FDCO team name normalisation (same as fetch_stats.py)
FDCO_TEAM = {
    "paris saint-germain": "Paris SG", "psg": "Paris SG",
    "manchester united": "Man United", "manchester city": "Man City",
    "tottenham hotspur": "Tottenham", "tottenham": "Tottenham",
    "newcastle united": "Newcastle", "west ham united": "West Ham",
    "wolverhampton wanderers": "Wolves", "nottingham forest": "Nott'm Forest",
    "atletico madrid": "Ath Madrid", "athletic bilbao": "Ath Bilbao",
    "inter milan": "Inter", "ac milan": "Milan", "as roma": "Roma",
    "borussia dortmund": "Dortmund", "bayer leverkusen": "Leverkusen",
    "olympique marseille": "Marseille", "olympique lyonnais": "Lyon",
    "as monaco": "Monaco", "stade rennais": "Rennes",
}

# ── Globals / caches ──────────────────────────────────────────────────────────
RUNDOWN_API_KEY = ""   # therundown.io — sign up at therundown.io/api
EXA_API_KEY     = ""
_elo_cache      = {}
_fdco_cache     = {}
_datapoints_left = "?"

SECRETS_FILE = "~.config/systemd/user/openclaw-gateway.service.d/20-secrets.conf"

# ── Utilities ─────────────────────────────────────────────────────────────────

def load_env():
    global RUNDOWN_API_KEY, EXA_API_KEY
    RUNDOWN_API_KEY = os.environ.get("RUNDOWN_API_KEY", "")
    EXA_API_KEY     = os.environ.get("EXA_API_KEY",     "")
    if not RUNDOWN_API_KEY or not EXA_API_KEY:
        try:
            with open(SECRETS_FILE) as f:
                for line in f:
                    if "RUNDOWN_API_KEY" in line and not RUNDOWN_API_KEY:
                        RUNDOWN_API_KEY = line.split("=", 2)[-1].strip().strip('"')
                    if "EXA_API_KEY" in line and not EXA_API_KEY:
                        EXA_API_KEY = line.split("=", 2)[-1].strip().strip('"')
        except Exception:
            pass
    if not RUNDOWN_API_KEY:
        print("[warn] RUNDOWN_API_KEY not set — odds unavailable, model-only picks.")
    # Initialise API-Football and SofaScore fallbacks
    APIF.init()
    SOFA.init()
    SBOOK.init()


_rate_limited_until = 0  # timestamp when rate limit clears

def http_get(url, headers=None, timeout=10):
    global _datapoints_left, _rate_limited_until
    import urllib.error as _ue
    # If we're globally rate-limited, skip immediately
    if _rate_limited_until and time.time() < _rate_limited_until:
        return None
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
            "Accept": "application/json",
            "Accept-Language": "en-US,en;q=0.9",
            **(headers or {})
        })
        with urllib.request.urlopen(req, timeout=timeout) as r:
            dp = r.getheader("x-datapoints-remaining")
            if dp:
                _datapoints_left = dp
            return json.loads(r.read())
    except _ue.HTTPError as e:
        if e.code == 429:
            # Rate limited — back off for 60 seconds
            _rate_limited_until = time.time() + 60
        return None
    except Exception:
        return None


# ── TheRundown V2 odds fetcher ────────────────────────────────────────────────

def american_to_decimal(price):
    """Convert American odds to decimal. 0.0001 = off-board sentinel → skip."""
    if price is None or abs(float(price)) < 1:
        return None
    p = float(price)
    if p > 0:
        return round(p / 100 + 1, 4)
    else:
        return round(100 / abs(p) + 1, 4)


def rundown_to_event(rd):
    """Normalise TheRundown V2 event → internal event dict (Odds API shape)."""
    teams = rd.get("teams", [])
    home_t = next((t for t in teams if t.get("is_home")), None)
    away_t = next((t for t in teams if t.get("is_away")), None)
    if not home_t or not away_t:
        return None

    def full_name(t):
        n, m = t.get("name", ""), t.get("mascot", "")
        return f"{n} {m}".strip() if m and m not in n else n

    home = full_name(home_t)
    away = full_name(away_t)

    # Participant ID → name lookup (needed for MMA/combat where market participant.name is empty)
    team_id_to_name = {t["team_id"]: full_name(t) for t in teams if t.get("team_id")}
    known_team_ids  = {home_t.get("team_id"), away_t.get("team_id")}

    # affiliate_id → {mkt_key: {participant_name: price_or_dict}}
    aff_mkts = defaultdict(lambda: defaultdict(dict))

    for mkt in rd.get("markets", []):
        mid = mkt.get("market_id")
        if mid == 1:
            mkt_key = "h2h"
        elif mid == 2:
            mkt_key = "spreads"
        elif mid == 3:
            mkt_key = "totals"
        else:
            continue

        for participant in mkt.get("participants", []):
            p_id   = participant.get("id")
            p_name = participant.get("name", "") or team_id_to_name.get(p_id, "")
            p_type = participant.get("type", "")

            # For h2h/spreads, skip participants that aren't actual teams in this event
            if mkt_key in ("h2h", "spreads") and p_type == "TYPE_TEAM" and p_id not in known_team_ids:
                continue
            if not p_name:
                continue

            for line in participant.get("lines", []):
                line_val = line.get("value", "")
                for aff_id, pd in line.get("prices", {}).items():
                    if not pd.get("is_main_line", True):
                        continue
                    dec = american_to_decimal(pd.get("price"))
                    if dec is None:
                        continue
                    if mkt_key in ("spreads", "totals"):
                        try:
                            pt = float(line_val)
                        except (ValueError, TypeError):
                            pt = 0.0
                        aff_mkts[aff_id][mkt_key][p_name] = {"price": dec, "point": pt}
                    else:
                        aff_mkts[aff_id][mkt_key][p_name] = dec

    bookmakers = []
    for aff_id, mkts in aff_mkts.items():
        info = RUNDOWN_AFFILIATES.get(str(aff_id))
        bk_key   = info[0] if info else f"book_{aff_id}"
        bk_title = info[1] if info else f"Book {aff_id}"
        markets  = []
        if "h2h" in mkts:
            markets.append({
                "key": "h2h",
                "outcomes": [{"name": k, "price": v} for k, v in mkts["h2h"].items()]
            })
        if "totals" in mkts:
            # Bake the line into the name: "Over"→"Over 2.5". Without this the pick
            # is just "Over" — unspecific to read AND unsettleable (settlement parses
            # the number out of the pick string).
            markets.append({
                "key": "totals",
                "outcomes": [
                    {"name": (f"{k} {v['point']:g}" if isinstance(v, dict) and v.get("point") else k),
                     "price": (v["price"] if isinstance(v, dict) else v),
                     "point": (v.get("point") if isinstance(v, dict) else None)}
                    for k, v in mkts["totals"].items()
                ]
            })
        if "spreads" in mkts:
            markets.append({
                "key": "spreads",
                "outcomes": [
                    {"name": k, "price": v["price"], "point": v["point"]}
                    for k, v in mkts["spreads"].items()
                ]
            })
        if markets:
            bookmakers.append({"key": bk_key, "title": bk_title, "markets": markets})

    return {
        "id":             rd.get("event_id", ""),
        "commence_time":  rd.get("event_date", ""),
        "home_team":      home,
        "away_team":      away,
        "bookmakers":     bookmakers,
    }


def rundown_events(sport_id, mon, sun):
    """
    Fetch events + odds from TheRundown for days in Mon–Sun that have events.
    Uses /dates first to avoid unnecessary API calls (and rate-limit hits).
    """
    if not RUNDOWN_API_KEY:
        return []

    # Skip the /dates discovery call (saves one API hit per sport, avoids rate limit).
    # Query today + tomorrow directly — the hide_no_markets=true param skips empty responses fast.
    from datetime import date as _dt
    today_str = _dt.today().strftime("%Y-%m-%d")
    tmr_str   = (mon + timedelta(days=1)).strftime("%Y-%m-%d")
    target_dates = sorted({mon.strftime("%Y-%m-%d"), today_str, tmr_str})

    # 2. Fetch each relevant date
    events = []
    seen   = set()
    for i, date_str in enumerate(target_dates):
        if i > 0:
            time.sleep(0.6)  # respect rate limit (~1 req/s)
        url = (
            f"{RUNDOWN_BASE}/sports/{sport_id}/events/{date_str}"
            f"?key={RUNDOWN_API_KEY}"
            f"&market_ids=1,2,3&affiliate_ids={RUNDOWN_AFFILIATE_IDS}"
            f"&main_line=true&hide_no_markets=true"
        )
        data = http_get(url)
        rd_events = (data.get("events") if isinstance(data, dict) else None) or []
        for rd in rd_events:
            eid = rd.get("event_id", "")
            if eid in seen:
                continue
            seen.add(eid)
            status = rd.get("score", {}).get("event_status", "")
            if status in ("STATUS_FINAL", "STATUS_CANCELED", "STATUS_POSTPONED"):
                continue
            evt = rundown_to_event(rd)
            if evt:
                events.append(evt)
    return events


def espn_schedule_events(espn_lg, mon, sun):
    """
    Fetch upcoming match schedule from ESPN (free, no key).
    Returns minimal event list — no bookmakers, model-only.
    """
    url = f"{ESPN_BASE}/{espn_lg}/scoreboard"
    data = http_get(url)
    events = []
    for evt in (data or {}).get("events", []):
        comp = (evt.get("competitions") or [{}])[0]
        status = comp.get("status", {}).get("type", {}).get("state", "")
        if status not in ("pre", "in"):
            continue
        date_str = evt.get("date", "")
        try:
            kick_dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            mon_dt = datetime(mon.year, mon.month, mon.day, tzinfo=timezone.utc)
            sun_dt = datetime(sun.year, sun.month, sun.day, tzinfo=timezone.utc)
            if not (mon_dt <= kick_dt <= sun_dt + timedelta(days=1)):
                continue
        except Exception:
            continue
        competitors = comp.get("competitors", [])
        home = next((c["team"]["displayName"] for c in competitors if c.get("homeAway") == "home"), "")
        away = next((c["team"]["displayName"] for c in competitors if c.get("homeAway") == "away"), "")
        if home and away:
            events.append({
                "id":            evt.get("id", ""),
                "commence_time": date_str,
                "home_team":     home,
                "away_team":     away,
                "bookmakers":    [],   # no odds — model-only
            })
    return events


def espn_schedule_events_any(espn_path, mon, sun):
    """Generic ESPN event fetcher for any sport.
    espn_path: full path like 'basketball/nba', 'baseball/mlb', 'hockey/nhl', etc.
    Returns minimal event list (model-only, no bookmakers).
    """
    if not espn_path:
        return []
    url = f"https://site.api.espn.com/apis/site/v2/sports/{espn_path}/scoreboard"
    data = http_get(url)
    events = []
    for evt in (data or {}).get("events", []):
        comp = (evt.get("competitions") or [{}])[0]
        status = comp.get("status", {}).get("type", {}).get("state", "")
        if status not in ("pre", "in"):
            continue
        date_str = evt.get("date", "")
        try:
            kick_dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            mon_dt = datetime(mon.year, mon.month, mon.day, tzinfo=timezone.utc)
            sun_dt = datetime(sun.year, sun.month, sun.day, tzinfo=timezone.utc)
            if not (mon_dt <= kick_dt <= sun_dt + timedelta(days=1)):
                continue
        except Exception:
            continue
        competitors = comp.get("competitors", [])
        home = next((c["team"]["displayName"] for c in competitors if c.get("homeAway") == "home"), "")
        away = next((c["team"]["displayName"] for c in competitors if c.get("homeAway") == "away"), "")
        # Some sports don't have home/away — use first/second competitor
        if not home and not away and len(competitors) >= 2:
            home = competitors[0].get("team", {}).get("displayName", "")
            away = competitors[1].get("team", {}).get("displayName", "")
        if home and away:
            events.append({
                "id":            evt.get("id", ""),
                "commence_time": date_str,
                "home_team":     home,
                "away_team":     away,
                "bookmakers":    [],
            })
    return events


def model_confidence(model_probs, elo_diff, form_h, form_a, h2h_adj):
    """
    Confidence tier from model factors alone — no odds needed.
    Returns: 'HIGH', 'MEDIUM', or 'LOW'
    Signals: Elo gap, form edge, H2H edge, strong favourite probability.
    """
    signals = 0

    # Strong probability lean (best outcome > 65%)
    if model_probs:
        best = max(model_probs.values())
        if best > 0.65:
            signals += 2
        elif best > 0.58:
            signals += 1

    # Elo gap (if available)
    if elo_diff is not None:
        if abs(elo_diff) > 150:
            signals += 2
        elif abs(elo_diff) > 75:
            signals += 1

    # Form edge (win-rate differential)
    if form_h and form_a:
        wr_h = form_h.get("w", 0) / max(1, form_h.get("n", 1))
        wr_a = form_a.get("w", 0) / max(1, form_a.get("n", 1))
        if abs(wr_h - wr_a) > 0.35:
            signals += 1

    # H2H edge (>4% adjustment = meaningful history)
    if h2h_adj is not None and abs(h2h_adj - 1.0) > 0.04:
        signals += 1

    if signals >= 4:
        return "HIGH"
    if signals >= 2:
        return "MEDIUM"
    return "LOW"


# ── Exa search helper ─────────────────────────────────────────────────────────

def exa_search(query, freshness="month", n=4):
    """Search via Exa API with recency filter."""
    if not EXA_API_KEY:
        return ""
    payload = json.dumps({
        "query": query, "numResults": n, "type": "neural",
        "freshness": freshness,
        "contents": {"text": {"maxCharacters": 600}, "highlights": {"numSentences": 2}}
    }).encode()
    try:
        req = urllib.request.Request(
            EXA_BASE,
            data=payload,
            headers={"x-api-key": EXA_API_KEY, "Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=12) as r:
            data = json.loads(r.read())
        snippets = []
        for res in data.get("results", [])[:n]:
            hi = res.get("highlights", {})
            if isinstance(hi, dict):
                h = hi.get("highlights", [])
            elif isinstance(hi, list):
                h = hi
            else:
                h = []
            txt = " | ".join(h[:2]) if h else res.get("text", "")[:200]
            if txt:
                snippets.append(txt)
        return " /// ".join(snippets)
    except Exception:
        return ""

# ── Date window ───────────────────────────────────────────────────────────────

def week_window():
    """Return (monday_utc, sunday_utc) for the current ISO week."""
    now  = datetime.now(timezone.utc)
    mon  = now - timedelta(days=now.weekday())
    mon  = mon.replace(hour=0, minute=0, second=0, microsecond=0)
    sun  = mon + timedelta(days=6, hours=23, minutes=59, seconds=59)
    return mon, sun


def in_window(ts_str, mon, sun):
    dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
    return mon <= dt <= sun

# ── ClubElo ───────────────────────────────────────────────────────────────────


# ── National team ELO (eloratings.net) ───────────────────────────────────────
_INTL_ELO_ISO = {
    "ES": "Spain", "AR": "Argentina", "FR": "France", "EN": "England",
    "BR": "Brazil", "BE": "Belgium", "PT": "Portugal", "NL": "Netherlands",
    "DE": "Germany", "IT": "Italy", "HR": "Croatia", "MX": "Mexico",
    "NG": "Nigeria", "SN": "Senegal", "MA": "Morocco", "US": "United States",
    "CA": "Canada", "JP": "Japan", "KR": "South Korea", "AU": "Australia",
    "EG": "Egypt", "CM": "Cameroon", "GH": "Ghana", "CI": "Ivory Coast",
    "PY": "Paraguay", "PE": "Peru", "UY": "Uruguay", "CO": "Colombia",
    "CL": "Chile", "AT": "Austria", "CH": "Switzerland", "PL": "Poland",
    "DK": "Denmark", "SE": "Sweden", "NO": "Norway", "TR": "Turkey",
    "UA": "Ukraine", "RS": "Serbia", "HU": "Hungary", "CZ": "Czech Republic",
    "RO": "Romania", "SK": "Slovakia", "GR": "Greece", "HT": "Haiti",
    "PR": "Puerto Rico", "IE": "Republic of Ireland", "SA": "Saudi Arabia",
    "ZA": "South Africa", "TN": "Tunisia", "ML": "Mali", "BF": "Burkina Faso",
    "GA": "Gabon", "CD": "DR Congo", "TZ": "Tanzania", "KE": "Kenya",
    "UG": "Uganda", "QA": "Qatar", "IR": "Iran", "IQ": "Iraq",
    "JO": "Jordan", "SY": "Syria", "IN": "India", "TH": "Thailand",
    "VN": "Vietnam", "MY": "Malaysia", "ID": "Indonesia", "NZ": "New Zealand",
    "JM": "Jamaica", "TT": "Trinidad and Tobago", "PA": "Panama",
    "GT": "Guatemala", "HN": "Honduras", "CR": "Costa Rica",
    "SV": "El Salvador", "EC": "Ecuador", "BO": "Bolivia", "VE": "Venezuela",
    "NI": "Nicaragua",
}
_intl_elo_cache: dict = {}

# ESPN display names that differ from eloratings.net names
_INTL_ELO_ALIASES = {
    "usa": "united states", "united states of america": "united states",
    "drc": "dr congo", "congo dr": "dr congo", "democratic republic of congo": "dr congo",
    "ivory coast": "côte d'ivoire", "cote d'ivoire": "côte d'ivoire",
    "south korea": "korea republic", "korea": "korea republic",
    "north korea": "korea dpr",
    "cape verde": "cape verde islands", "cabo verde": "cape verde islands",
    "ireland": "republic of ireland",
    "kyrgyz republic": "kyrgyzstan",
    "china pr": "china", "chinese taipei": "taiwan",
    "uae": "united arab emirates",
    "bosnia-herzegovina": "bosnia and herzegovina", "bosnia": "bosnia and herzegovina",
    "macedonia": "north macedonia",
    "curacao": "curaçao",
    "st. kitts and nevis": "saint kitts and nevis",
    "st. lucia": "saint lucia",
    "st. vincent and the grenadines": "saint vincent and the grenadines",
    "turkiye": "turkey", "türkiye": "turkey",
}

def _load_intl_elo():
    """Fetch eloratings.net ratings for ALL ~330 national teams.
    en.teams.tsv maps the 2-letter code to display name(s); World.tsv has ratings."""
    if _intl_elo_cache:
        return _intl_elo_cache
    try:
        import urllib.request as _ur
        code_to_names: dict = {}
        raw_names = _ur.urlopen("https://eloratings.net/en.teams.tsv", timeout=8).read().decode()
        for line in raw_names.strip().split("\n"):
            cols = line.split("\t")
            if len(cols) >= 2:
                code_to_names[cols[0]] = [c.strip() for c in cols[1:] if c.strip()]

        raw = _ur.urlopen("https://eloratings.net/World.tsv", timeout=8).read().decode()
        for line in raw.strip().split("\n"):
            cols = line.split("\t")
            if len(cols) > 3 and cols[3].isdigit():
                rating = int(cols[3])
                for name in code_to_names.get(cols[2], []):
                    _intl_elo_cache[name.lower()] = rating
        # Legacy hand-map kept as extra aliases (e.g. "DR Congo")
        for code, name in _INTL_ELO_ISO.items():
            if name.lower() not in _intl_elo_cache:
                for cand in code_to_names.get(code, []):
                    if cand.lower() in _intl_elo_cache:
                        _intl_elo_cache[name.lower()] = _intl_elo_cache[cand.lower()]
                        break
    except Exception:
        pass
    return _intl_elo_cache

def get_intl_elo(team_name):
    table = _load_intl_elo()
    key = team_name.lower().strip()
    key = _INTL_ELO_ALIASES.get(key, key)
    return table.get(key)

def get_elo(team):
    if team in _elo_cache:
        return _elo_cache[team]
    name = team.replace(" ", "_")
    data = http_get(f"{CLUBELO_BASE}/{name}")
    if data and isinstance(data, list) and data:
        elo = float(sorted(data, key=lambda x: x.get("From",""))[-1].get("Elo", 1500))
        _elo_cache[team] = elo
        return elo
    _elo_cache[team] = None
    return None


def elo_probs(home, away, home_adv=65):
    eh = get_elo(home) or get_intl_elo(home)
    ea = get_elo(away) or get_intl_elo(away)
    if not eh or not ea:
        return None
    diff = (eh + home_adv) - ea
    pw   = 1 / (1 + 10 ** (-diff / 400))
    close = 1 - abs(pw - 0.5) * 2
    pd   = 0.25 * (0.5 + close * 0.5)
    return {"home": pw*(1-pd), "draw": pd, "away": (1-pw)*(1-pd)}

# ── ESPN form ─────────────────────────────────────────────────────────────────

ESPN_TEAM_IDS = {
    "arsenal": ("359","eng.1"), "paris saint-germain": ("160","fra.1"),
    "psg": ("160","fra.1"), "manchester city": ("382","eng.1"),
    "liverpool": ("364","eng.1"), "chelsea": ("363","eng.1"),
    "manchester united": ("360","eng.1"), "real madrid": ("86","esp.1"),
    "barcelona": ("83","esp.1"), "atletico madrid": ("1068","esp.1"),
    "bayern munich": ("132","ger.1"), "borussia dortmund": ("124","ger.1"),
    "inter milan": ("110","ita.1"), "ac milan": ("103","ita.1"),
    "juventus": ("111","ita.1"), "napoli": ("114","ita.1"),
    "nice": ("186","fra.1"), "saint etienne": ("185","fra.1"),
    "oklahoma city thunder": ("25","nba"), "san antonio spurs": ("26","nba"),
}

def get_form(team_name, espn_league):
    """Returns dict with wins/draws/losses and goals stats from last 5 games."""
    key = team_name.lower()
    team_id, league = ESPN_TEAM_IDS.get(key, (None, espn_league))
    if not team_id:
        return None
    now   = datetime.now(timezone.utc)
    season = now.year if now.month >= 7 else now.year - 1
    data  = http_get(f"https://site.api.espn.com/apis/site/v2/sports/soccer/{league}/teams/{team_id}/schedule?season={season}")
    if not data:
        return None
    events = data.get("events", [])
    done = sorted(
        [e for e in events if e.get("competitions",[{}])[0].get("status",{}).get("type",{}).get("completed")],
        key=lambda x: x.get("date",""), reverse=True
    )[:5]
    if not done:
        return None
    w=d=l=gf=ga=0
    for ev in done:
        comp = ev["competitions"][0]
        teams = comp["competitors"]
        ours  = next((t for t in teams if t["team"]["id"]==team_id), None)
        opp   = next((t for t in teams if t["team"]["id"]!=team_id), None)
        if not ours or not opp:
            continue
        s_us  = int(ours.get("score",{}).get("displayValue",0) or 0)
        s_op  = int(opp.get("score",{}).get("displayValue",0) or 0)
        gf+=s_us; ga+=s_op
        if ours.get("winner"):    w+=1
        elif opp.get("winner"):   l+=1
        else:                     d+=1
    n = w+d+l or 1
    return {"w":w,"d":d,"l":l,"gf":gf,"ga":ga,"n":n,
            "pts_pct": (w*3+d)/(n*3), "avg_gf": gf/n, "avg_ga": ga/n}


def form_adjustment(form):
    """Return a probability multiplier based on recent form. Range ≈ 0.90–1.10."""
    if not form:
        return 1.0
    return 0.90 + form["pts_pct"] * 0.20   # 0.90 at 0% pts → 1.10 at 100% pts


# ── H2H from fetch_stats.py ───────────────────────────────────────────────────

_h2h_cache = {}

def get_h2h(home, away):
    """
    Returns H2H record between two teams using ESPN API (last 2 seasons, cross-competition).
    Imports directly from fetch_stats.py to avoid code duplication.
    """
    key = f"{home}|{away}"
    if key in _h2h_cache:
        return _h2h_cache[key]
    try:
        import importlib.util, sys as _sys
        spec = importlib.util.spec_from_file_location(
            "fetch_stats",
            "~.openclaw/workspace/scripts/fetch_stats.py"
        )
        mod = importlib.util.load_from_spec = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        result = mod.get_h2h(home, away, n=5)
        _h2h_cache[key] = result
        return result
    except Exception:
        _h2h_cache[key] = None
        return None


def h2h_adjustment(h2h_text, home):
    """
    Parse H2H text and return a small probability adjustment for the home team.
    If home team dominates H2H → slight bump. If away dominates → slight drop.
    Range: 0.95–1.05.
    """
    if not h2h_text or "[" in h2h_text:
        return 1.0
    import re
    # Look for "Record: TeamA NW | ND | TeamB NW"
    m = re.search(r'Record:\s*(.*?)\s*(\d+)W.*?(\d+)W', h2h_text)
    if not m:
        return 1.0
    try:
        # simple heuristic: if home appears before away wins > away wins → +2%
        home_first = home.lower() in h2h_text.split("Record:")[1].split("|")[0].lower()
        wins = [int(x) for x in re.findall(r'(\d+)W', h2h_text.split("Record:")[1])]
        if len(wins) >= 2:
            home_w, away_w = (wins[0], wins[1]) if home_first else (wins[1], wins[0])
            total = home_w + away_w
            if total == 0:
                return 1.0
            edge = (home_w - away_w) / (total * 5)   # max ±5% shift
            return max(0.95, min(1.05, 1.0 + edge))
    except Exception:
        pass
    return 1.0


# ── FDCO corners / cards / market stats ───────────────────────────────────────

def fdco_csv(league_code):
    if league_code in _fdco_cache:
        return _fdco_cache[league_code]
    now = datetime.now(timezone.utc)
    season = now.year if now.month >= 7 else now.year - 1
    y1,y2 = str(season)[-2:], str(season+1)[-2:]
    url = f"{FDCO_BASE}/{y1}{y2}/{league_code}.csv"
    data = http_get(url)   # will fail – need raw bytes
    # Use urllib directly for CSV
    try:
        req = urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=12) as r:
            raw = r.read().decode("utf-8-sig", errors="replace")
        rows = list(csv.DictReader(io.StringIO(raw)))
        _fdco_cache[league_code] = rows
        return rows
    except Exception:
        _fdco_cache[league_code] = []
        return []


def fdco_team_name(name):
    return FDCO_TEAM.get(name.lower(), name)


def team_corner_stats(team_name, rows):
    """Avg corners for/against per game from FDCO CSV."""
    tn = fdco_team_name(team_name).lower()
    tf, ta, games = 0, 0, 0
    for r in rows:
        ht = r.get("HomeTeam","").lower()
        at = r.get("AwayTeam","").lower()
        if not (r.get("HC") and r.get("AC")):
            continue
        try:
            hc,ac = int(r["HC"]), int(r["AC"])
        except ValueError:
            continue
        if tn in ht:
            tf+=hc; ta+=ac; games+=1
        elif tn in at:
            tf+=ac; ta+=hc; games+=1
    if not games:
        return None
    return {"for": tf/games, "against": ta/games, "total": (tf+ta)/games, "n": games}


def team_card_stats(team_name, rows):
    """Avg yellow cards for/against per game from FDCO CSV."""
    tn = fdco_team_name(team_name).lower()
    tf, ta, games = 0, 0, 0
    for r in rows:
        ht = r.get("HomeTeam","").lower()
        at = r.get("AwayTeam","").lower()
        if not (r.get("HY") and r.get("AY")):
            continue
        try:
            hy,ay = int(r["HY"]), int(r["AY"])
        except ValueError:
            continue
        if tn in ht:
            tf+=hy; ta+=ay; games+=1
        elif tn in at:
            tf+=ay; ta+=hy; games+=1
    if not games:
        return None
    return {"for": tf/games, "against": ta/games, "total": (tf+ta)/games, "n": games}


def team_market_stats(team_name, rows):
    """BTTS%, Over 2.5%, avg goals from FDCO CSV."""
    tn = fdco_team_name(team_name).lower()
    btts=ou25=gf=ga=games=clean=0
    for r in rows:
        ht = r.get("HomeTeam","").lower()
        at = r.get("AwayTeam","").lower()
        if not (r.get("FTHG") and r.get("FTAG")):
            continue
        try:
            hg,ag = int(r["FTHG"]), int(r["FTAG"])
        except ValueError:
            continue
        if tn in ht:
            our,opp=hg,ag
        elif tn in at:
            our,opp=ag,hg
        else:
            continue
        gf+=our; ga+=opp; games+=1
        if hg>0 and ag>0: btts+=1
        if hg+ag>2: ou25+=1
        if opp==0: clean+=1
    if not games:
        return None
    return {
        "btts_pct": btts/games, "ou25_pct": ou25/games,
        "avg_gf": gf/games, "avg_ga": ga/games,
        "avg_total": (gf+ga)/games, "clean_pct": clean/games,
        "n": games
    }


# Stats-based soccer prop markets. Built from bettingstats.org per-team averages
# (covers 130+ leagues). TheRundown carries no corner/card/foul lines, so these
# publish the model's expected total, the leaning side at the nearest line, our
# probability, and a fair-odds target to shop against. Informational — not logged
# to bets.db (no post-match feed to settle corner/foul counts yet).
# (label, bettingstats key, candidate lines)
SOCCER_PROP_SPECS = [
    ("Corners O/U",         "avg_corners",          [8.5, 9.5, 10.5, 11.5, 12.5]),
    ("Cards O/U",           "avg_cards",            [2.5, 3.5, 4.5, 5.5]),
    ("Fouls O/U",           "avg_fouls",            [18.5, 20.5, 22.5, 24.5, 26.5]),
    ("Offsides O/U",        "avg_offsides",         [2.5, 3.5, 4.5, 5.5]),
    ("Shots O/U",           "avg_shots",            [18.5, 20.5, 22.5, 24.5, 26.5]),
    ("Shots on Target O/U", "avg_shots_on_target",  [6.5, 7.5, 8.5, 9.5, 10.5]),
]


def soccer_stat_props(home, away, ms_h, ms_a):
    """Model-only soccer prop picks from per-team stat averages. Expected match
    total = sum of both teams' per-game averages; Poisson over the nearest line."""
    out = []
    if not ms_h or not ms_a:
        return out
    for label, key, lines in SOCCER_PROP_SPECS:
        vh, va = ms_h.get(key), ms_a.get(key)
        if not isinstance(vh, (int, float)) or not isinstance(va, (int, float)):
            continue
        lam_total = float(vh) + float(va)
        if lam_total <= 0:
            continue
        # The bookmaker line sits near the expected total — read that one.
        line = min(lines, key=lambda L: abs(L - lam_total))
        p_over = poisson_over(lam_total, line)
        side, prob = ("Over", p_over) if p_over >= 0.5 else ("Under", 1.0 - p_over)
        if prob < 0.58:        # skip coin-flips — only surface a real lean
            continue
        out.append({
            "market": f"{label} {line}",
            "pick": f"{side} {line}",
            "odds": None,
            "bookmaker": "model — verify price",
            "our_prob": round(prob * 100, 1),
            "market_prob": None,
            "ev": None, "kelly_stake": None,
            "fair_odds": round(1.0 / prob, 2),
            "model": f"Stats model (exp {lam_total:.1f}/match over {ms_h.get('n','?')}+{ms_a.get('n','?')} games)",
            "is_special": True, "is_model_only": True, "is_prop_model": True,
        })
    return out


def poisson_over(lam, threshold):
    """P(X > threshold) for Poisson(lam)."""
    # P(X <= k) via cumulative Poisson
    k = int(threshold)
    cum = 0.0
    for i in range(k+1):
        cum += math.exp(-lam) * (lam**i) / math.factorial(i)
    return 1.0 - cum

# ── NCAAB via ActionNetwork (free, in-season Nov–Apr) ────────────────────────

def scan_ncaab(min_ev, mon, sun):
    """
    Scan NCAA basketball for value via ActionNetwork's free odds API.
    Returns [] in off-season (May–Oct). Works Nov–Apr.
    """
    url = "https://api.actionnetwork.com/web/v1/games?league=ncaab&period=game&book_ids=15,30,76,123,69&include=odds"
    data = http_get(url, headers={"Accept": "application/json"})
    if not data or not data.get("games"):
        return []

    bets = []
    for game in data["games"]:
        try:
            start = datetime.fromisoformat(game["start_time"].replace("Z", "+00:00"))
        except Exception:
            continue
        if not in_window(game.get("start_time",""), mon, sun):
            continue

        home = game.get("home_team",{}).get("full_name","Home")
        away = game.get("away_team",{}).get("full_name","Away")
        kick  = start.strftime("%Y-%m-%d %H:%M")

        # Collect moneyline odds from all books
        ml_home, ml_away = [], []
        for book_odds in game.get("odds",[]):
            if book_odds.get("ml_home") and book_odds.get("ml_away"):
                def to_decimal(ml):
                    ml = int(ml)
                    return (100/(-ml)+1) if ml < 0 else (ml/100+1)
                ml_home.append(to_decimal(book_odds["ml_home"]))
                ml_away.append(to_decimal(book_odds["ml_away"]))

        if len(ml_home) < 2:
            continue

        # Consensus fair probability
        avg_h = sum(ml_home)/len(ml_home)
        avg_a = sum(ml_away)/len(ml_away)
        fair = remove_vig({home: avg_h, away: avg_a})

        best_h = max(ml_home)
        best_a = max(ml_away)

        for team, best_p, fair_p in [(home, best_h, fair[home]), (away, best_a, fair[away])]:
            ev_val = ev(fair_p, best_p)
            if ev_val >= min_ev:
                bets.append({
                    "sport": "🏀 NCAAB", "match": f"{away} vs {home}", "kick": kick,
                    "market": "Moneyline", "pick": team,
                    "odds": round(best_p, 2), "bookmaker": "Best available",
                    "our_prob": round(fair_p*100, 1),
                    "market_prob": round(fair_p*100, 1),
                    "ev": round(ev_val*100, 1),
                    "kelly_stake": round(kelly(ev_val, fair_p, best_p), 1),
                    "model": "ActionNetwork consensus",
                    "has_sharp": True,
                    "form_h": None, "form_a": None, "ms_h": None, "ms_a": None,
                    "injury": "", "home": home, "away": away,
                    "is_special": False, "is_model_only": False,
                })
    return bets


# ── Exa value scout (fallback for uncovered sports / low credits) ─────────────

EXA_SPORTS_QUERIES = {
    "volleyball":   "volleyball match prediction winner odds value bet {date}",
    "table tennis": "table tennis WTT match prediction winner value bet odds {date}",
    "rugby union":  "rugby union Premiership URC Heineken Cup match prediction odds value {date}",
    "darts":        "PDC darts match prediction winner odds value bet player average {date}",
}

# Keywords that signal actual betting content vs navigation/boilerplate
_PICK_KW  = {"predict","pick","bet","tip","win","odds","favourite","underdog","value",
             "average","form","head-to-head","h2h","ranking","set","leg","checkout"}
_SKIP_KW  = {"subscribe","sign up","advertisement","cookie","privacy","login","register",
             "read more","follow us","newsletter","javascript","click here"}


def exa_value_scout(sport_label, date_str, n=5):
    """
    Exa scout for sports with no structured API source.
    Extracts structured pick summaries rather than raw article dumps.
    """
    query_template = EXA_SPORTS_QUERIES.get(sport_label.lower())
    if not query_template:
        return []
    query = query_template.format(date=date_str)
    if not EXA_API_KEY:
        return []

    payload = json.dumps({
        "query": query, "numResults": n, "type": "neural", "freshness": "week",
        "contents": {
            "text": {"maxCharacters": 1200},
            "highlights": {"numSentences": 3, "highlightsPerUrl": 2, "query": query}
        }
    }).encode()
    try:
        req = urllib.request.Request(
            EXA_BASE, data=payload,
            headers={"x-api-key": EXA_API_KEY, "Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=12) as r:
            data = json.loads(r.read())
    except Exception:
        return []

    picks = []
    for res in data.get("results", [])[:n]:
        title = res.get("title", "")[:80]
        url   = res.get("url", "")

        # Gather candidate text blocks: highlights first, then full text sentences
        hi = res.get("highlights", {})
        if isinstance(hi, dict):
            snippets = hi.get("highlights", [])
        elif isinstance(hi, list):
            snippets = hi
        else:
            snippets = []

        full_text = res.get("text", "")
        # Break full text into sentences as fallback candidates
        sentences = [s.strip() for s in full_text.replace("\n", " ").split(".") if len(s.strip()) > 30]
        candidates = list(snippets) + sentences[:20]

        # Score each candidate: count pick keywords, penalise skip keywords
        best_chunk = ""
        best_score = 0
        for chunk in candidates:
            cl = chunk.lower()
            if any(k in cl for k in _SKIP_KW):
                continue
            score = sum(1 for k in _PICK_KW if k in cl)
            if score > best_score:
                best_score = score
                best_chunk = chunk.strip()

        if best_score < 2 or not best_chunk:
            continue   # nothing useful in this article

        # Try to extract a match name from the title (e.g. "Smith vs Jones - PDC Darts")
        import re as _re
        match_name = title
        vs_match = _re.search(r'([A-Z][a-zA-Z\s]+)\s+v[s]?\.?\s+([A-Z][a-zA-Z\s]+)', title)
        if vs_match:
            match_name = f"{vs_match.group(1).strip()} vs {vs_match.group(2).strip()}"

        # Cap at 250 chars and clean whitespace
        pick_text = " ".join(best_chunk.split())[:250]

        picks.append({
            "sport":     f"🎯 {sport_label.title()}",
            "match":     match_name[:60],
            "kick":      date_str,
            "market":    "Scouted pick",
            "pick":      pick_text,
            "odds":      None,
            "bookmaker": _re.sub(r'https?://(www\.)?', '', url).split('/')[0][:40],
            "our_prob":  None, "market_prob": None,
            "ev":        None, "kelly_stake": None,
            "model":     f"Exa scout ({sport_label})",
            "has_sharp": False,
            "form_h": None, "form_a": None, "ms_h": None, "ms_a": None,
            "injury": "", "home": "", "away": "",
            "is_special": False, "is_model_only": True,
        })
    return picks


# ── Vig removal / value maths ─────────────────────────────────────────────────

def remove_vig(outcomes_dict):
    """Dict of {name: price} → {name: fair_prob}."""
    total = sum(1/p for p in outcomes_dict.values())
    return {k: (1/v)/total for k,v in outcomes_dict.items()}


def best_price(event, market_key):
    """Best (highest) odds per outcome across all bookmakers."""
    best, bk_name = {}, {}
    for bk in event.get("bookmakers", []):
        for mkt in bk.get("markets", []):
            if mkt["key"] != market_key:
                continue
            for o in mkt.get("outcomes", []):
                n, p = o["name"], o["price"]
                if n not in best or p > best[n]:
                    best[n] = p
                    bk_name[n] = bk["title"]
    return best, bk_name


def consensus_fair(event, market_key, prefer_sharp=True):
    """Weighted consensus fair probability for a market."""
    pool = defaultdict(list)
    for bk in event.get("bookmakers", []):
        w = 2 if (prefer_sharp and bk["key"] in SHARP_BOOKS) else 1
        for mkt in bk.get("markets", []):
            if mkt["key"] != market_key:
                continue
            for o in mkt.get("outcomes", []):
                for _ in range(w):
                    pool[o["name"]].append(o["price"])
    if not pool:
        return None
    avg = {k: sum(v)/len(v) for k,v in pool.items()}
    return remove_vig(avg)


def ev(prob, odds):
    return prob * odds - 1


def kelly(ev_val, prob, odds, bankroll=100):
    b = odds - 1
    if b <= 0:
        return 0
    fk = (b*prob - (1-prob)) / b
    return max(0, fk * KELLY_FRACTION * bankroll)

# ── Injury / suspension lookup ────────────────────────────────────────────────

def injury_summary(home, away):
    """Quick Exa search for injury/suspension news for both teams."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    q = f"{home} {away} injury suspension ban team news {today}"
    if not EXA_API_KEY:
        return ""
    payload = json.dumps({
        "query": q, "numResults": 4, "type": "neural", "freshness": "week",
        "contents": {"text": {"maxCharacters": 500}, "highlights": {"numSentences": 3}}
    }).encode()
    injury_kw = {"injur","suspend","ban","doubt","miss","absent","ruled out","fitness",
                 "unavailable","sideline","card","yellow","red card","return","recover",
                 "out for","day-to-day","questionable","listed","lineup","squad"}
    nav_kw = {"skip to","main content","matchday","soccerhub","week 29","info stats",
              "follow us","subscribe","advertisement","javascript",
              "match sheet","transfermarkt","1st leg","2nd leg","playoff",
              "age: ","market value","contract until","join date"}
    try:
        req = urllib.request.Request(
            EXA_BASE, data=payload,
            headers={"x-api-key": EXA_API_KEY, "Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=12) as r:
            data = json.loads(r.read())
        for res in data.get("results", []):
            # Prefer highlights; fall back to text
            hi = res.get("highlights", {})
            if isinstance(hi, dict):
                snippets = hi.get("highlights", [])
            elif isinstance(hi, list):
                snippets = hi
            else:
                snippets = []
            candidates = snippets or [res.get("text","")[:500]]
            for chunk in candidates:
                cl = chunk.lower()
                # Skip navigation/boilerplate
                if any(n in cl for n in nav_kw):
                    continue
                # Must contain injury-related content
                if any(k in cl for k in injury_kw):
                    return chunk.strip()[:240]
    except Exception:
        pass
    return ""


# ── Injury probability adjustment ─────────────────────────────────────────────

def injury_prob_adjustment(injury_text):
    """Parse injury/suspension text; return probability delta for the mentioned team (-ve = hurt)."""
    if not injury_text:
        return 0.0
    text = injury_text.lower()
    adj  = 0.0
    if any(k in text for k in ("ruled out", "will not play", "not available", "misses out", "out for")):
        adj -= 0.07
    elif any(k in text for k in ("doubt", "50/50", "fitness test", "questionable")):
        adj -= 0.03
    if " ban" in text or "suspended" in text or "banned" in text:
        adj -= 0.05
    return max(adj, -0.12)


# ── ESPN injury feed (all sports) ─────────────────────────────────────────────

_espn_inj_cache = {}

ESPN_INJURY_SLUGS = {
    "baseball_mlb":                  "baseball/mlb",
    "baseball_mlb_playoffs":         "baseball/mlb",
    "basketball_nba":                "basketball/nba",
    "basketball_nba_playoffs":       "basketball/nba",
    "basketball_wnba":               "basketball/wnba",
    "icehockey_nhl":                 "hockey/nhl",
    "icehockey_nhl_playoffs":        "hockey/nhl",
    "americanfootball_nfl":          "football/nfl",
    "americanfootball_nfl_playoffs": "football/nfl",
}


def espn_injuries(sport_key):
    """
    Fetch ESPN injury feed for a sport.
    Returns {team_name_lower: [{"player", "status", "pos"}]}. Cached per sport per session.
    """
    slug = ESPN_INJURY_SLUGS.get(sport_key)
    if not slug:
        return {}
    if sport_key in _espn_inj_cache:
        return _espn_inj_cache[sport_key]
    url  = f"https://site.api.espn.com/apis/site/v2/sports/{slug}/injuries"
    data = http_get(url)
    result = {}
    for entry in (data or {}).get("injuries", []):
        tname = (entry.get("team", {}).get("displayName") or "").lower()
        if not tname:
            continue
        players = []
        for inj in entry.get("injuries", []):
            ath = inj.get("athlete", {})
            players.append({
                "player": ath.get("displayName", ""),
                "status": inj.get("status", ""),
                "pos":    ath.get("position", {}).get("abbreviation", ""),
            })
        if players:
            result[tname] = players
    _espn_inj_cache[sport_key] = result
    return result


def team_injury_text(feed, team_name):
    """Return brief injury summary for a team from ESPN feed dict."""
    if not feed:
        return ""
    tl    = team_name.lower()
    words = [w for w in tl.split() if len(w) > 3]
    found = []
    for k, injuries in feed.items():
        if tl in k or k in tl or any(w in k for w in words):
            found.extend(injuries)
    if not found:
        return ""
    out   = [f"{i['player']} OUT"   for i in found if i["status"].lower() in ("out", "injured reserve", "ir")]
    doubt = [f"{i['player']} DOUBT" for i in found if i["status"].lower() in ("doubtful", "questionable")]
    return ", ".join((out + doubt)[:4])


# ── MLB independent model ─────────────────────────────────────────────────────

MLB_TEAM_IDS = {
    "arizona diamondbacks": 109, "atlanta braves": 144,     "baltimore orioles": 110,
    "boston red sox": 111,       "chicago cubs": 112,        "chicago white sox": 145,
    "cincinnati reds": 113,      "cleveland guardians": 114, "colorado rockies": 115,
    "detroit tigers": 116,       "houston astros": 117,      "kansas city royals": 118,
    "los angeles angels": 108,   "los angeles dodgers": 119, "miami marlins": 146,
    "milwaukee brewers": 158,    "minnesota twins": 142,     "new york mets": 121,
    "new york yankees": 147,     "oakland athletics": 133,   "philadelphia phillies": 143,
    "pittsburgh pirates": 134,   "san diego padres": 135,    "san francisco giants": 137,
    "seattle mariners": 136,     "st. louis cardinals": 138, "tampa bay rays": 139,
    "texas rangers": 140,        "toronto blue jays": 141,   "washington nationals": 120,
    "sacramento athletics": 133, "athletics": 133,
}

_mlb_sp_cache  = {}
_mlb_rec_cache = {}
_mlb_sch_cache = {}


def _mlb_team_id(name):
    return MLB_TEAM_IDS.get(name.lower())


def _mlb_sp_stats(person_id, season):
    if person_id in _mlb_sp_cache:
        return _mlb_sp_cache[person_id]
    url  = (f"https://statsapi.mlb.com/api/v1/people/{person_id}"
            f"?hydrate=stats(group=pitching,type=season,season={season})")
    data = http_get(url)
    result = None
    try:
        person = (data or {}).get("people", [{}])[0]
        for sg in person.get("stats", []):
            if sg.get("group", {}).get("displayName") == "pitching":
                splits = sg.get("splits", [])
                if splits:
                    s   = splits[0].get("stat", {})
                    era = float(s.get("era",  99.0) or 99.0)
                    ip  = float(s.get("inningsPitched", 0) or 0)
                    result = {"era": era, "whip": float(s.get("whip", 2.0) or 2.0),
                              "name": person.get("fullName", ""), "ip": ip}
                    break
    except Exception:
        pass
    _mlb_sp_cache[person_id] = result
    return result


def _mlb_team_record(team_id, season):
    if team_id in _mlb_rec_cache:
        return _mlb_rec_cache[team_id]
    url  = (f"https://statsapi.mlb.com/api/v1/standings"
            f"?leagueId=103,104&season={season}&standingsTypes=regularSeason")
    data = http_get(url)
    result = None
    try:
        for record in (data or {}).get("records", []):
            for tr in record.get("teamRecords", []):
                if tr.get("team", {}).get("id") == team_id:
                    wins   = int(tr.get("wins",  0) or 0)
                    losses = int(tr.get("losses", 0) or 0)
                    rs     = int(tr.get("runsScored",   0) or 0)
                    ra     = int(tr.get("runsAllowed",  0) or 0)
                    l10w   = 0
                    for sr in tr.get("records", {}).get("splitRecords", []):
                        if sr.get("type") == "lastTen":
                            l10w = int(sr.get("wins", 0) or 0)
                    result = {"wins": wins, "losses": losses, "rs": rs, "ra": ra, "last10wins": l10w}
                    break
            if result:
                break
    except Exception:
        pass
    _mlb_rec_cache[team_id] = result
    return result


def mlb_model_prob(home, away, game_date, inj_feed=None):
    """
    Independent MLB win probability from SP ERA, Pythagorean record, recent form, injuries.
    Returns (home_prob, away_prob, label_str).
    """
    season  = datetime.now(timezone.utc).year
    home_id = _mlb_team_id(home)
    away_id = _mlb_team_id(away)

    # Probable starters from MLB schedule API
    if game_date not in _mlb_sch_cache:
        url = (f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={game_date}"
               f"&hydrate=probablePitcher&gameType=R")
        _mlb_sch_cache[game_date] = http_get(url) or {}
    sched = _mlb_sch_cache[game_date]

    home_sp = away_sp = None
    try:
        for date_obj in (sched.get("dates") or []):
            for game in (date_obj.get("games") or []):
                ht = game.get("teams", {}).get("home", {})
                at = game.get("teams", {}).get("away", {})
                ht_id = ht.get("team", {}).get("id")
                at_id = at.get("team", {}).get("id")
                if home_id and away_id and ht_id == home_id and at_id == away_id:
                    home_sp = ht.get("probablePitcher")
                    away_sp = at.get("probablePitcher")
                    break
    except Exception:
        pass

    home_sp_st = _mlb_sp_stats(home_sp["id"], season) if home_sp else None
    away_sp_st = _mlb_sp_stats(away_sp["id"], season) if away_sp else None
    home_rec   = _mlb_team_record(home_id, season) if home_id else None

    league_avg_era = 4.20
    base = 0.50

    # Pitcher ERA differential — primary signal
    pitcher_adj = 0.0
    if home_sp_st and away_sp_st:
        h_era = home_sp_st["era"] if home_sp_st["era"] < 15 else league_avg_era
        a_era = away_sp_st["era"] if away_sp_st["era"] < 15 else league_avg_era
        pitcher_adj = max(-0.08, min(0.08, (a_era - h_era) * 0.025))
    elif home_sp_st and home_sp_st["ip"] > 10:
        pitcher_adj = (league_avg_era - home_sp_st["era"]) * 0.015
    elif away_sp_st and away_sp_st["ip"] > 10:
        pitcher_adj = (away_sp_st["era"] - league_avg_era) * 0.015

    # Pythagorean expectation
    pyth_adj = 0.0
    if home_rec and home_rec["rs"] > 0:
        g = home_rec["wins"] + home_rec["losses"]
        if g > 10:
            rs, ra = home_rec["rs"] / g, home_rec["ra"] / g
            pyth   = (rs ** 1.83) / (rs ** 1.83 + ra ** 1.83)
            pyth_adj = (pyth - 0.50) * 0.60

    # Recent form (last 10 games)
    form_adj = (home_rec["last10wins"] / 10 - 0.50) * 0.15 if home_rec else 0.0

    # Injury adjustment
    inj_adj = 0.0
    if inj_feed:
        hi = team_injury_text(inj_feed, home)
        ai = team_injury_text(inj_feed, away)
        if hi:
            inj_adj += injury_prob_adjustment(hi)
        if ai:
            inj_adj -= injury_prob_adjustment(ai)   # away injury benefits home

    home_prob = max(0.20, min(0.85, base + pitcher_adj + pyth_adj + form_adj + 0.04 + inj_adj))

    if home_sp_st and away_sp_st:
        sp_str = f"{home_sp_st['name']} {home_sp_st['era']:.2f} ERA vs {away_sp_st['name']} {away_sp_st['era']:.2f} ERA"
    elif home_sp_st:
        sp_str = f"{home_sp_st['name']} {home_sp_st['era']:.2f} ERA (away SP TBD)"
    elif away_sp_st:
        sp_str = f"(home SP TBD) vs {away_sp_st['name']} {away_sp_st['era']:.2f} ERA"
    else:
        sp_str = "SPs TBD — pyth/form only"

    extra = {
        "pitcher_h":      home_sp_st["name"] if home_sp_st else None,
        "pitcher_a":      away_sp_st["name"] if away_sp_st else None,
        "pitcher_h_era":  home_sp_st["era"]   if home_sp_st else None,
        "pitcher_a_era":  away_sp_st["era"]   if away_sp_st else None,
    }

    return home_prob, 1.0 - home_prob, f"MLB: {sp_str}", extra


# ── MMA / UFC model ───────────────────────────────────────────────────────────

_ufc_cache = {}


def _ufc_fighter_stats(name):
    """Scrape UFCStats.com for career striking/grappling stats. Cached per session."""
    key = name.lower().strip()
    if key in _ufc_cache:
        return _ufc_cache[key]
    try:
        q   = urllib.parse.quote_plus(key)
        req = urllib.request.Request(
            f"http://www.ufcstats.com/statistics/fighters?query={q}&action=Search",
            headers={"User-Agent": "Mozilla/5.0"}
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            html = r.read().decode("utf-8", errors="replace")
    except Exception:
        _ufc_cache[key] = None
        return None

    import re as _re
    link_m = _re.search(r'href="(http://www\.ufcstats\.com/fighter-details/[a-f0-9]+)"', html)
    if not link_m:
        _ufc_cache[key] = None
        return None
    try:
        req2 = urllib.request.Request(link_m.group(1), headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req2, timeout=10) as r:
            fhtml = r.read().decode("utf-8", errors="replace")
    except Exception:
        _ufc_cache[key] = None
        return None

    import re as _re2
    stats = {}
    for stat_key, pat in [
        ("slpm",    r'SLpM.*?<p[^>]*>([\d.]+)</p>'),
        ("str_acc", r'Str\. Acc\..*?<p[^>]*>([\d.]+)%'),
        ("sapm",    r'SApM.*?<p[^>]*>([\d.]+)<'),
        ("str_def", r'Str\. Def\..*?<p[^>]*>([\d.]+)%'),
        ("td_avg",  r'TD Avg\..*?<p[^>]*>([\d.]+)<'),
        ("td_acc",  r'TD Acc\..*?<p[^>]*>([\d.]+)%'),
        ("td_def",  r'TD Def\..*?<p[^>]*>([\d.]+)%'),
        ("sub_avg", r'Sub\. Avg\..*?<p[^>]*>([\d.]+)<'),
    ]:
        m = _re2.search(pat, fhtml, _re2.DOTALL | _re2.IGNORECASE)
        if m:
            try:
                val = float(m.group(1).strip())
                stats[stat_key] = val / 100 if stat_key in ("str_acc","str_def","td_acc","td_def") else val
            except Exception:
                pass

    result = stats if len(stats) >= 4 else None
    _ufc_cache[key] = result
    return result


def mma_model_prob(fighter_a, fighter_b):
    """
    Win probability using UFCStats striking + grappling differentials.
    Returns (prob_a, prob_b, label_str). Returns (None, None, ...) if stats unavailable.
    """
    sa = _ufc_fighter_stats(fighter_a)
    sb = _ufc_fighter_stats(fighter_b)
    if not sa or not sb:
        return None, None, "MMA: stats unavailable"

    strike_net = (sa.get("slpm", 0) * sa.get("str_acc", 0.4)) - \
                 (sb.get("slpm", 0) * (1 - sb.get("str_def", 0.5)))
    td_net     = (sa.get("td_avg", 0) * sa.get("td_acc", 0.4)) - \
                 (sb.get("td_avg", 0) * (1 - sb.get("td_def", 0.5)))
    edge  = strike_net * 0.6 + td_net * 0.4
    prob_a = max(0.15, min(0.85, 1 / (1 + math.exp(-edge * 0.8))))
    label  = (f"MMA: {fighter_a} SLpM {sa.get('slpm',0):.1f} "
              f"Acc {sa.get('str_acc',0)*100:.0f}% vs "
              f"{fighter_b} SLpM {sb.get('slpm',0):.1f} "
              f"Acc {sb.get('str_acc',0)*100:.0f}%")
    return prob_a, 1.0 - prob_a, label


# ── Understat xG form (soccer) ────────────────────────────────────────────────

_xg_cache = {}

UNDERSTAT_LEAGUE_MAP = {
    "eng.1":  "EPL",
    "esp.1":  "La_liga",
    "ger.1":  "Bundesliga",
    "ita.1":  "Serie_A",
    "fra.1":  "Ligue_1",
}


def get_xg_form(team_name, espn_league, n_games=5):
    """
    Rolling xG / xGA from Understat for last n_games.
    Covers EPL, La Liga, Bundesliga, Serie A, Ligue 1.
    Returns {"xg": float, "xga": float, "n": int} or None.
    """
    league_slug = UNDERSTAT_LEAGUE_MAP.get(espn_league)
    if not league_slug:
        return None
    team_slug = team_name.replace(" ", "_")
    cache_key = f"{league_slug}:{team_slug}"
    if cache_key in _xg_cache:
        return _xg_cache[cache_key]

    season = datetime.now(timezone.utc).year
    if datetime.now(timezone.utc).month < 7:
        season -= 1
    try:
        req = urllib.request.Request(
            f"https://understat.com/team/{team_slug}/{season}",
            headers={"User-Agent": "Mozilla/5.0"}
        )
        with urllib.request.urlopen(req, timeout=12) as r:
            html = r.read().decode("utf-8", errors="replace")
    except Exception:
        _xg_cache[cache_key] = None
        return None

    import re as _re
    m = _re.search(r"datesData\s*=\s*JSON\.parse\('(.+?)'\)", html)
    if not m:
        _xg_cache[cache_key] = None
        return None
    try:
        raw     = m.group(1).encode("utf-8").decode("unicode_escape")
        matches = json.loads(raw)
    except Exception:
        _xg_cache[cache_key] = None
        return None

    played = sorted(
        [gm for gm in matches if gm.get("isResult")],
        key=lambda x: x.get("datetime", ""), reverse=True
    )[:n_games]
    if not played:
        _xg_cache[cache_key] = None
        return None

    xg_sum  = sum(float(gm.get("xG",  0) or 0) for gm in played)
    xga_sum = sum(float(gm.get("xGA", 0) or 0) for gm in played)
    n       = len(played)
    result  = {"xg": xg_sum / n, "xga": xga_sum / n, "n": n}
    _xg_cache[cache_key] = result
    return result


# ── PDC Darts model ───────────────────────────────────────────────────────────

_pdc_avgs    = {}
_pdc_fetched = False


def _load_pdc_rankings():
    """Scrape PDC rankings page for player 3-dart averages. Loads once per session."""
    global _pdc_fetched
    if _pdc_fetched:
        return
    _pdc_fetched = True
    try:
        req = urllib.request.Request(
            "https://www.pdc.tv/players/player-rankings",
            headers={"User-Agent": "Mozilla/5.0"}
        )
        with urllib.request.urlopen(req, timeout=12) as r:
            html = r.read().decode("utf-8", errors="replace")
    except Exception:
        return
    import re as _re
    for m in _re.finditer(
        r'<td[^>]*>\s*([A-Z][a-zA-Z\s\'\-\.]+)\s*</td>.*?<td[^>]*>\s*([\d]{2,3}\.\d{2})\s*</td>',
        html, _re.DOTALL
    ):
        try:
            avg = float(m.group(2))
            if 60 <= avg <= 120:
                _pdc_avgs[m.group(1).strip().lower()] = avg
        except ValueError:
            pass


def pdc_player_avg(name):
    """Return PDC 3-dart average for a player (fuzzy last-name fallback). None if unknown."""
    _load_pdc_rankings()
    n    = name.lower().strip()
    if n in _pdc_avgs:
        return _pdc_avgs[n]
    last = n.split()[-1] if " " in n else n
    for k, v in _pdc_avgs.items():
        if last in k or k.endswith(last):
            return v
    return None


def darts_model_prob(player_a, player_b):
    """
    Win probability from PDC 3-dart average differential (each point ≈ 2% edge).
    Returns (prob_a, prob_b, label_str).
    """
    avg_a = pdc_player_avg(player_a) or 85.0
    avg_b = pdc_player_avg(player_b) or 85.0
    diff  = avg_a - avg_b
    prob_a = max(0.25, min(0.75, 0.50 + diff * 0.02))
    found  = pdc_player_avg(player_a) is not None and pdc_player_avg(player_b) is not None
    label  = (f"PDC avg: {player_a} {avg_a:.1f} vs {player_b} {avg_b:.1f}"
              + ("" if found else " (partial data — verify)"))
    return prob_a, 1.0 - prob_a, label


def scan_darts(date_str):
    """
    Darts scan: Exa for match discovery + PDC model for win probability.
    Returns model-only picks with actual statistical backing.
    """
    raw_picks = exa_value_scout("darts", date_str, n=8)
    import re as _re
    results   = []
    for p in raw_picks:
        match_name = p.get("match", "")
        m = _re.match(r'^(.+?)\s+vs\.?\s+(.+?)$', match_name.strip(), _re.IGNORECASE)
        if not m:
            results.append(p)
            continue
        pa, pb = m.group(1).strip(), m.group(2).strip()
        prob_a, prob_b, label = darts_model_prob(pa, pb)
        if prob_a is None:
            results.append(p)
            continue
        winner      = pa if prob_a >= 0.50 else pb
        winner_prob = max(prob_a, prob_b)
        results.append({
            **p,
            "pick":          f"{winner} to win",
            "our_prob":      round(winner_prob * 100, 1),
            "model":         label,
            "ev":            None,
            "is_model_only": True,
        })
    return results


# ── Value candidates ──────────────────────────────────────────────────────────

def scan_event_specials(sport_key, event_id, home, away, fdco_code, espn_league):
    """
    Fetch and analyse special markets for a single event.
    Returns list of value_bet dicts.
    """
    is_soccer = sport_key.startswith("soccer_")
    bets = []

    # ── TheRundown event-level special markets ────────────────────────────────
    # Request team_totals (market_id=94) in addition to core markets
    rd_sport_id = RUNDOWN_SPORT_IDS.get(sport_key)
    ev_data = None
    if rd_sport_id and RUNDOWN_API_KEY and event_id:
        url = (
            f"{RUNDOWN_BASE}/sports/{rd_sport_id}/events/{event_id}"
            f"?key={RUNDOWN_API_KEY}&market_ids=1,2,3,94&affiliate_ids={RUNDOWN_AFFILIATE_IDS}&main_line=true"
        )
        raw = http_get(url)
        if raw and raw.get("event_id"):
            ev_data = rundown_to_event(raw)
    if ev_data and ev_data.get("bookmakers"):
        for mkt_key in ("btts", "alternate_totals", "team_totals", "spreads"):
            fair = consensus_fair(ev_data, mkt_key)
            if not fair:
                continue
            bp, bk = best_price(ev_data, mkt_key)
            for outcome, our_prob in fair.items():
                if outcome not in bp:
                    continue
                best_p = bp[outcome]
                ev_val = ev(our_prob, best_p)
                if ev_val >= DEFAULT_MIN_EV:
                    mkt_label = {
                        "btts": "BTTS",
                        "alternate_totals": "Alt Total",
                        "team_totals": "Team Total",
                        "spreads": "Handicap",
                    }.get(mkt_key, mkt_key)
                    bets.append({
                        "market": mkt_label, "pick": outcome,
                        "odds": best_p, "bookmaker": bk.get(outcome,"?"),
                        "our_prob": round(our_prob*100,1),
                        "market_prob": round(fair.get(outcome,0)*100,1),
                        "ev": round(ev_val*100,1),
                        "kelly_stake": round(kelly(ev_val,our_prob,best_p),1),
                        "model": "Consensus", "is_special": True,
                    })

    # ── Corners model (football-data.co.uk, no API line) ─────────────────────
    if is_soccer and fdco_code:
        rows = fdco_csv(fdco_code)
        cs_h = team_corner_stats(home, rows)
        cs_a = team_corner_stats(away, rows)
        if cs_h and cs_a:
            # Expected corners: blend both teams' averages
            lam_home = (cs_h["for"] + cs_a["against"]) / 2
            lam_away = (cs_a["for"] + cs_h["against"]) / 2
            lam_total = lam_home + lam_away
            for line in (8.5, 9.5, 10.5, 11.5):
                prob_over = poisson_over(lam_total, line)
                if 0.45 <= prob_over <= 0.75:  # Only flag when model has meaningful conviction
                    bets.append({
                        "market": f"Corners O/U {line}",
                        "pick": f"Over {line}" if prob_over > 0.55 else f"Under {line}",
                        "odds": None,  # No API line — check bookmaker manually
                        "bookmaker": "Check manually",
                        "our_prob": round((prob_over if prob_over>0.55 else 1-prob_over)*100,1),
                        "market_prob": None,
                        "ev": None,
                        "kelly_stake": None,
                        "model": f"Corners model (avg total: {lam_total:.1f}/game)",
                        "is_special": True, "is_model_only": True,
                    })
                    break  # Only show best line

        # ── Cards model ───────────────────────────────────────────────────────
        cd_h = team_card_stats(home, rows)
        cd_a = team_card_stats(away, rows)
        if cd_h and cd_a:
            lam_cards = (cd_h["for"] + cd_h["against"] + cd_a["for"] + cd_a["against"]) / 2
            for line in (2.5, 3.5, 4.5):
                prob_over = poisson_over(lam_cards, line)
                if 0.45 <= prob_over <= 0.75:
                    bets.append({
                        "market": f"Cards O/U {line}",
                        "pick": f"Over {line}" if prob_over>0.55 else f"Under {line}",
                        "odds": None,
                        "bookmaker": "Check manually",
                        "our_prob": round((prob_over if prob_over>0.55 else 1-prob_over)*100,1),
                        "market_prob": None,
                        "ev": None,
                        "kelly_stake": None,
                        "model": f"Cards model (avg total: {lam_cards:.1f}/game)",
                        "is_special": True, "is_model_only": True,
                    })
                    break

    return bets


_SB_INDEX = None   # cached SportyBet upcoming index, built once per process run


def _sb_index():
    """Paginated SportyBet upcoming soccer events, cached for the whole scan."""
    global _SB_INDEX
    if _SB_INDEX is None:
        try:
            _SB_INDEX = (SBODDS.all_upcoming(max_pages=8) if SBODDS else []) or []
        except Exception:
            _SB_INDEX = []
    return _SB_INDEX


def scan_sport(sport_key, min_ev, mon, sun):
    """
    Full scan for one sport. Returns list of value bet dicts.
    Each bet includes context (form, injuries).
    """
    cfg       = SPORTS_CONFIG.get(sport_key, {})
    espn_lg   = cfg.get("espn")
    fdco_code = cfg.get("fdco")
    is_soccer = sport_key.startswith("soccer_")
    label     = cfg.get("label", sport_key)

    # ── Event discovery + odds: TheRundown → ESPN schedule (model-only) ─────────
    rd_sport_id = cfg.get("rundown_id") or RUNDOWN_SPORT_IDS.get(sport_key)
    # Tennis: map any tennis_ key to ATP(38)/WTA(39)
    if rd_sport_id is None and "tennis_" in sport_key:
        rd_sport_id = 39 if "wta" in sport_key.lower() else 38

    events = []
    if rd_sport_id:
        events = rundown_events(rd_sport_id, mon, sun)

    # Soccer fallback: ESPN schedule (free, no key)
    if not events and is_soccer and espn_lg:
        events = espn_schedule_events(espn_lg, mon, sun)

    # All-sport fallback: generic ESPN scoreboard via espn_path
    espn_any = cfg.get("espn_path")
    if not events and espn_any and not (is_soccer and espn_lg):
        events = espn_schedule_events_any(espn_any, mon, sun)

    if not events:
        return []

    # ── SportyBet odds enrichment ──────────────────────────────────────────────
    # Rundown prices only ~13 soccer leagues. For the rest, ESPN supplies fixtures
    # but no odds → model-only. Attach SportyBet h2h/totals so these in-season
    # leagues get real EV picks + double chance + props. Guarded; never fatal.
    if is_soccer and SBODDS and any(not e.get("bookmakers") for e in events):
        try:
            idx = _sb_index()
            if idx:
                for e in events:
                    if e.get("bookmakers"):
                        continue
                    sb = SBODDS.find_event(e["home_team"], e["away_team"], idx, min_sim=0.62)
                    if not sb:
                        continue
                    bk = SBODDS.event_odds_internal(sb["eventId"], e["home_team"], e["away_team"])
                    if bk:
                        e["bookmakers"] = [bk]
        except Exception:
            pass

    results = []
    _sport_inj_feed = espn_injuries(sport_key) if not is_soccer else None

    for event in events:
        home    = event["home_team"]
        away    = event["away_team"]
        kick    = event["commence_time"][:16].replace("T"," ")
        ev_id   = event["id"]
        n_books = len(event.get("bookmakers", []))

        # ── Model probability ─────────────────────────────────────────────────
        model_h2h = None
        model_src = "Consensus"
        form_home = form_away = None
        h2h_text  = None
        h2h_adj   = 1.0
        elo_diff  = None
        # Sport-specific evidence (filled below, used by plain_rationale)
        xg_h = xg_a = None
        _mlb_pitcher_h = _mlb_pitcher_a = None
        _mlb_pitcher_h_era = _mlb_pitcher_a_era = None

        if is_soccer:
            elo = elo_probs(home, away)
            h2h_text = get_h2h(home, away)
            h2h_adj  = h2h_adjustment(h2h_text, home) if h2h_text else 1.0

            if elo:
                # Elo diff for confidence scoring (home – away rating)
                raw_home = elo_probs.__wrapped__(home) if hasattr(elo_probs, "__wrapped__") else None
                # Approximate elo_diff from the probability gap
                elo_diff = (elo["home"] - elo["away"]) * 400  # inverse logistic approximation

            if elo and espn_lg:
                form_home = get_form(home, espn_lg)
                form_away = get_form(away, espn_lg)
                fa_h = form_adjustment(form_home)
                fa_a = form_adjustment(form_away)

                # API-Football fallback for form when ESPN fails (covers all leagues)
                if not form_home or not form_away:
                    fix = APIF.find_fixture(home, away, kick[:10] if kick else None)
                    if fix:
                        apif_cfg = SPORTS_CONFIG.get(sport_key, {})
                        apif_league_id = apif_cfg.get("apif_league_id")
                        apif_season    = apif_cfg.get("apif_season", datetime.now().year)
                        if fix.get("league_id"):
                            apif_league_id = apif_league_id or fix["league_id"]
                            apif_season    = fix.get("season") or apif_season
                        if not form_home and fix.get("home_id") and apif_league_id:
                            af_stats = APIF.team_stats(fix["home_id"], apif_league_id, apif_season)
                            if af_stats:
                                form_home = {
                                    "w": af_stats["w5"], "d": af_stats["d5"], "l": af_stats["l5"],
                                    "n": 5,
                                    "avg_gf": af_stats.get("goals_scored_avg"),
                                    "avg_ga": af_stats.get("goals_conceded_avg"),
                                }
                                fa_h = form_adjustment(form_home)
                        if not form_away and fix.get("away_id") and apif_league_id:
                            af_stats = APIF.team_stats(fix["away_id"], apif_league_id, apif_season)
                            if af_stats:
                                form_away = {
                                    "w": af_stats["w5"], "d": af_stats["d5"], "l": af_stats["l5"],
                                    "n": 5,
                                    "avg_gf": af_stats.get("goals_scored_avg"),
                                    "avg_ga": af_stats.get("goals_conceded_avg"),
                                }
                                fa_a = form_adjustment(form_away)

                # Blend Understat xG form where available — more reliable than win rate alone
                xg_h = get_xg_form(home, espn_lg)
                xg_a = get_xg_form(away, espn_lg)
                if xg_h:
                    xg_mult_h = max(0.85, min(1.15, 1.0 + (xg_h["xg"] - xg_h["xga"]) * 0.025))
                    fa_h = fa_h * 0.4 + xg_mult_h * 0.6
                if xg_a:
                    xg_mult_a = max(0.85, min(1.15, 1.0 + (xg_a["xg"] - xg_a["xga"]) * 0.025))
                    fa_a = fa_a * 0.4 + xg_mult_a * 0.6
                raw = {
                    "home": elo["home"] * fa_h * h2h_adj,
                    "draw": elo["draw"],
                    "away": elo["away"] * fa_a * (2 - h2h_adj),
                }
                total = sum(raw.values())
                model_h2h = {home: raw["home"]/total, "Draw": raw["draw"]/total, away: raw["away"]/total}
                model_src = "Elo+xG+Form+H2H" if (xg_h or xg_a) else "Elo+Form+H2H"
            elif elo:
                raw = {"home": elo["home"]*h2h_adj, "draw": elo["draw"], "away": elo["away"]*(2-h2h_adj)}
                total = sum(raw.values())
                model_h2h = {home: raw["home"]/total, "Draw": raw["draw"]/total, away: raw["away"]/total}
                model_src = "ClubElo+H2H"

        elif sport_key.startswith("baseball_mlb"):
            # ── MLB independent model ─────────────────────────────────────────
            game_date = event["commence_time"][:10]
            mlb_result = mlb_model_prob(home, away, game_date, _sport_inj_feed)
            if mlb_result and len(mlb_result) >= 4:
                hp, ap, mlb_label, mlb_extra = mlb_result
            else:
                hp, ap, mlb_label = mlb_result or (None, None, None)
                mlb_extra = {}
            if hp is not None:
                model_h2h = {home: hp, away: ap}
                model_src = mlb_label
                _mlb_pitcher_h     = mlb_extra.get("pitcher_h")
                _mlb_pitcher_a     = mlb_extra.get("pitcher_a")
                _mlb_pitcher_h_era = mlb_extra.get("pitcher_h_era")
                _mlb_pitcher_a_era = mlb_extra.get("pitcher_a_era")

        elif sport_key.startswith("mma_"):
            # ── MMA independent model ─────────────────────────────────────────
            prob_h, prob_a, mma_label = mma_model_prob(home, away)
            if prob_h is not None:
                model_h2h = {home: prob_h, away: prob_a}
                model_src = mma_label

        elif sport_key.startswith("americanfootball_nfl"):
            # ── NFL independent model: nfelo published Elo + QB adjustments ───
            nfl = NFLELO.nfl_probs(home, away)
            if nfl:
                model_h2h = {home: nfl["home"], away: nfl["away"]}
                model_src = nfl["label"]

        # ── Injuries / suspensions ────────────────────────────────────────────
        injury_text = injury_summary(home, away) if is_soccer else ""
        if is_soccer and not injury_text:
            # Fallback: sportsgambler.com official team-news feed (EPL/La Liga/
            # Serie A/Bundesliga/UCL/World Cup), cached 6h
            try:
                injury_text = SGAMBLER.injuries_for_match(home, away)
            except Exception:
                pass
        if not injury_text:
            # ESPN structured injury feed for MLB / NBA / NHL / NFL
            _esp_feed = _sport_inj_feed
            if _esp_feed:
                hi = team_injury_text(_esp_feed, home)
                ai = team_injury_text(_esp_feed, away)
                parts = []
                if hi:
                    parts.append(f"{home}: {hi}")
                if ai:
                    parts.append(f"{away}: {ai}")
                injury_text = " | ".join(parts)

        # Apply injury probability adjustment to soccer model (injury_text may name either team)
        if is_soccer and model_h2h and injury_text:
            inj_delta = injury_prob_adjustment(injury_text)
            if inj_delta != 0.0:
                home_mentioned = home.lower().split()[0] in injury_text.lower()
                away_mentioned = away.lower().split()[0] in injury_text.lower()
                if home_mentioned and not away_mentioned:
                    raw = dict(model_h2h)
                    raw[home] = max(0.05, raw.get(home, 0.33) + inj_delta)
                    raw[away] = max(0.05, raw.get(away, 0.33) - inj_delta * 0.5)
                    tot = sum(raw.values())
                    model_h2h = {k: v / tot for k, v in raw.items()}
                elif away_mentioned and not home_mentioned:
                    raw = dict(model_h2h)
                    raw[away] = max(0.05, raw.get(away, 0.33) + inj_delta)
                    raw[home] = max(0.05, raw.get(home, 0.33) - inj_delta * 0.5)
                    tot = sum(raw.values())
                    model_h2h = {k: v / tot for k, v in raw.items()}

        # ── Historical market stats (football) ────────────────────────────────
        ms_home = ms_away = None
        if is_soccer and fdco_code:
            rows = fdco_csv(fdco_code)
            ms_home = team_market_stats(home, rows)
            ms_away = team_market_stats(away, rows)
        elif is_soccer:
            # No fdco history (friendlies, World Cup, minor leagues) →
            # bettingstats.org per-team form stats (BTTS/over %, corners, cards)
            try:
                bs = BSTATS.match_stats(home, away, kick[:10]) if kick else None
                if bs:
                    ms_home, ms_away = bs["home"], bs["away"]
            except Exception:
                pass

        # ── Model confidence (runs whether or not we have odds) ───────────────
        confidence = model_confidence(model_h2h, elo_diff, form_home, form_away, h2h_adj)

        # ── Odds availability ────────────────────────────────────────────────
        fair_h2h = consensus_fair(event, "h2h")
        bp_h2h, bk_h2h = best_price(event, "h2h")
        has_sharp = any(bk["key"] in SHARP_BOOKS for bk in event.get("bookmakers",[]))
        has_odds  = bool(fair_h2h and bp_h2h)

        # ── Model-only pick when no odds but model is confident ────────────────
        # Use prob floor for dedicated sport models (ERA-based MLB, fight-record MMA, etc.)
        _best_prob = max(model_h2h.values()) if model_h2h else 0
        _has_dedicated_model = model_src not in ("Consensus", "Consensus+History", "ClubElo", "ClubElo+H2H")
        _model_only_ok = (
            confidence in ("HIGH", "MEDIUM")
            or (_has_dedicated_model and _best_prob >= 0.54)
        )
        if not has_odds and model_h2h and _model_only_ok:
            best_outcome = max(model_h2h, key=model_h2h.get)
            results.append({
                "sport": label, "match": f"{home} vs {away}", "kick": kick,
                "market": "1X2", "pick": best_outcome,
                "odds": None, "bookmaker": "verify price",
                "our_prob": round(model_h2h[best_outcome] * 100, 1),
                "market_prob": None,
                "ev": None, "kelly_stake": None,
                "confidence": confidence,
                "model": model_src, "has_sharp": False,
                "form_h": form_home, "form_a": form_away,
                "ms_h": ms_home, "ms_a": ms_away,
                "injury": injury_text, "h2h": h2h_text,
                "home": home, "away": away,
                "xg_h": xg_h, "xg_a": xg_a, "elo_diff": elo_diff,
                "pitcher_h": _mlb_pitcher_h, "pitcher_a": _mlb_pitcher_a,
                "pitcher_h_era": _mlb_pitcher_h_era, "pitcher_a_era": _mlb_pitcher_a_era,
                "is_special": False, "is_model_only": True,
            })
            continue  # no odds to compare — skip EV markets

        if fair_h2h and bp_h2h:
            use_probs = model_h2h if model_h2h else fair_h2h
            for outcome, our_prob in use_probs.items():
                if outcome not in bp_h2h:
                    continue
                best_p = bp_h2h[outcome]
                ev_val = ev(our_prob, best_p)
                if ev_val >= min_ev:
                    results.append(_bet(
                        sport=label, match=f"{home} vs {away}", kick=kick,
                        market="1X2", pick=outcome,
                        odds=best_p, bk=bk_h2h.get(outcome,"?"),
                        our_prob=our_prob, fair_prob=fair_h2h.get(outcome,0),
                        ev_val=ev_val, model=model_src,
                        has_sharp=has_sharp,
                        form_h=form_home, form_a=form_away,
                        ms_h=ms_home, ms_a=ms_away,
                        injury=injury_text,
                        home=home, away=away,
                        ev_id=ev_id, sport_key=sport_key,
                        fdco_code=fdco_code, espn_lg=espn_lg, h2h=h2h_text,
                        n_books=n_books,
                        xg_h=xg_h, xg_a=xg_a, elo_diff=elo_diff,
                        pitcher_h=_mlb_pitcher_h, pitcher_a=_mlb_pitcher_a,
                        pitcher_h_era=_mlb_pitcher_h_era, pitcher_a_era=_mlb_pitcher_a_era,
                    ))

        # ── Double chance (safer play when a straight win is shaky) ────────────
        # Trigger: soccer favourite whose model win prob is in the 50–65% "shaky
        # win" zone. We offer "<favourite> or Draw" so SabiAI isn't forced to
        # always back an outright win. DC odds estimated by combining the win+draw
        # prices — 1/(1/win + 1/draw) — which tracks a book's real DC line closely.
        if is_soccer and has_odds and model_h2h and "Draw" in model_h2h:
            non_draw = {k: v for k, v in model_h2h.items() if k != "Draw"}
            if non_draw:
                fav = max(non_draw, key=non_draw.get)
                fav_p = non_draw[fav]
                draw_p = model_h2h.get("Draw", 0.0)
                draw_key = next((k for k in bp_h2h if k.lower() in ("draw", "x", "tie")), None)
                dc_prob = fav_p + draw_p
                if (0.50 <= fav_p <= 0.65 and draw_key and fav in bp_h2h
                        and dc_prob >= 0.78):
                    win_price, draw_price = bp_h2h[fav], bp_h2h[draw_key]
                    if win_price > 1 and draw_price > 1:
                        dc_odds = round(1.0 / (1.0 / win_price + 1.0 / draw_price), 4)
                        if dc_odds >= 1.12:
                            results.append(_bet(
                                sport=label, match=f"{home} vs {away}", kick=kick,
                                market="Double Chance", pick=f"{fav} or Draw",
                                odds=dc_odds, bk=bk_h2h.get(fav, "?"),
                                our_prob=dc_prob, fair_prob=dc_prob,
                                ev_val=ev(dc_prob, dc_odds), model=model_src,
                                has_sharp=has_sharp,
                                form_h=form_home, form_a=form_away,
                                ms_h=ms_home, ms_a=ms_away,
                                injury=injury_text, home=home, away=away,
                                ev_id=ev_id, sport_key=sport_key,
                                fdco_code=fdco_code, espn_lg=espn_lg, h2h=h2h_text,
                                n_books=n_books,
                                xg_h=xg_h, xg_a=xg_a, elo_diff=elo_diff,
                                pitcher_h=_mlb_pitcher_h, pitcher_a=_mlb_pitcher_a,
                                pitcher_h_era=_mlb_pitcher_h_era, pitcher_a_era=_mlb_pitcher_a_era,
                            ))

        # ── Totals (Over/Under) ────────────────────────────────────────────────
        # Skip totals for combat sports — "O/U rounds" needs a dedicated model
        is_combat = sport_key.startswith(("mma_", "boxing_"))
        fair_tot = None if is_combat else consensus_fair(event, "totals")
        bp_tot, bk_tot = best_price(event, "totals")
        if fair_tot and bp_tot:
            for outcome, our_prob in fair_tot.items():
                if outcome not in bp_tot:
                    continue
                best_p = bp_tot[outcome]

                # ou25_pct is the historical Over-2.5 rate — only blend it into a
                # 2.5 line (or an unspecified Over), not into a 3.5/1.5 line.
                if (is_soccer and ms_home and ms_away and outcome.startswith("Over")
                        and ("2.5" in outcome or outcome == "Over")
                        and ms_home.get("ou25_pct") is not None
                        and ms_away.get("ou25_pct") is not None):
                    hist_prob = (ms_home["ou25_pct"] + ms_away["ou25_pct"]) / 2
                    our_prob  = 0.6*our_prob + 0.4*hist_prob
                    model_src_tot = "Consensus+History"
                else:
                    model_src_tot = "Consensus"

                ev_val = ev(our_prob, best_p)
                if ev_val >= min_ev:
                    results.append(_bet(
                        sport=label, match=f"{home} vs {away}", kick=kick,
                        market=(
                            "O/U Goals" if (is_soccer or sport_key.startswith("icehockey_"))
                            else "O/U Runs" if sport_key.startswith(("baseball_", "cricket_"))
                            else "O/U Points" if sport_key.startswith(
                                ("basketball_", "americanfootball_", "rugbyleague_", "rugbyunion_", "aussierules_"))
                            else "O/U Games" if sport_key.startswith("tennis_")
                            else "O/U"
                        ), pick=outcome,
                        odds=best_p, bk=bk_tot.get(outcome,"?"),
                        our_prob=our_prob, fair_prob=fair_tot.get(outcome,0),
                        ev_val=ev_val, model=model_src_tot,
                        has_sharp=has_sharp,
                        form_h=form_home, form_a=form_away,
                        ms_h=ms_home, ms_a=ms_away,
                        injury=injury_text,
                        home=home, away=away,
                        ev_id=ev_id, sport_key=sport_key,
                        fdco_code=fdco_code, espn_lg=espn_lg, h2h=h2h_text,
                        n_books=n_books,
                        xg_h=xg_h, xg_a=xg_a, elo_diff=elo_diff,
                        pitcher_h=_mlb_pitcher_h, pitcher_a=_mlb_pitcher_a,
                        pitcher_h_era=_mlb_pitcher_h_era, pitcher_a_era=_mlb_pitcher_a_era,
                    ))

        # ── Spreads (handicap / point spread) ─────────────────────────────────
        fair_sp = consensus_fair(event, "spreads")
        bp_sp, bk_sp = best_price(event, "spreads")
        if fair_sp and bp_sp:
            for outcome, our_prob in fair_sp.items():
                if outcome not in bp_sp:
                    continue
                best_p = bp_sp[outcome]
                ev_val = ev(our_prob, best_p)
                if ev_val >= min_ev:
                    results.append(_bet(
                        sport=label, match=f"{home} vs {away}", kick=kick,
                        market="Handicap", pick=outcome,
                        odds=best_p, bk=bk_sp.get(outcome,"?"),
                        our_prob=our_prob, fair_prob=fair_sp.get(outcome,0),
                        ev_val=ev_val, model="Consensus",
                        has_sharp=has_sharp,
                        form_h=form_home, form_a=form_away,
                        ms_h=None, ms_a=None,
                        injury="", home=home, away=away,
                        ev_id=ev_id, sport_key=sport_key,
                        fdco_code=fdco_code, espn_lg=espn_lg, h2h=h2h_text,
                        n_books=n_books,
                        xg_h=xg_h, xg_a=xg_a, elo_diff=elo_diff,
                        pitcher_h=_mlb_pitcher_h, pitcher_a=_mlb_pitcher_a,
                        pitcher_h_era=_mlb_pitcher_h_era, pitcher_a_era=_mlb_pitcher_a_era,
                    ))

        # ── Stats-based prop models (corners/cards/fouls/offsides/shots) ───────
        # No API cost — reuses the BSTATS data already fetched above. Only attach
        # props to matches that already produced a main-market pick, so they
        # enrich the games we're featuring instead of flooding every fixture.
        _match_str = f"{home} vs {away}"
        _event_featured = any(r.get("match") == _match_str for r in results)
        if is_soccer and ms_home and ms_away and _event_featured:
            for prop in soccer_stat_props(home, away, ms_home, ms_away):
                prop.update({
                    "sport": label, "match": f"{home} vs {away}", "kick": kick,
                    "form_h": form_home, "form_a": form_away,
                    "ms_h": ms_home, "ms_a": ms_away,
                    "injury": injury_text, "home": home, "away": away,
                    "h2h": h2h_text,
                })
                results.append(prop)

        # ── Special markets (football only — credit guard) ────────────────────
        if not cfg.get("specials"):
            continue
        specials = scan_event_specials(sport_key, ev_id, home, away, fdco_code, espn_lg)
        for s in specials:
            s.update({
                "sport": label, "match": f"{home} vs {away}", "kick": kick,
                "form_h": form_home, "form_a": form_away,
                "ms_h": ms_home, "ms_a": ms_away,
                "injury": injury_text, "home": home, "away": away,
                "has_sharp": has_sharp,
                "xg_h": xg_h, "xg_a": xg_a, "elo_diff": elo_diff,
                "pitcher_h": _mlb_pitcher_h, "pitcher_a": _mlb_pitcher_a,
                "pitcher_h_era": _mlb_pitcher_h_era, "pitcher_a_era": _mlb_pitcher_a_era,
            })
            if s.get("is_model_only") or (s.get("ev") or 0) >= min_ev*100:
                results.append(s)

    # ── Dedup + outlier flag ──────────────────────────────────────────────────
    seen, cleaned = set(), []
    for b in results:
        key = (b.get("match",""), b.get("market",""), b.get("pick",""), b.get("bookmaker",""))
        if key in seen:
            continue
        seen.add(key)
        if not b.get("ev_note") and (b.get("ev") or 0) > 0:
            # Outlier threshold: tight when few books built the consensus
            nb = b.get("_n_books", n_books)  # fall back to last event's n_books
            threshold = 30 if nb >= 5 else (22 if nb >= 3 else 15)
            if b["ev"] > threshold:
                b["ev_note"] = f"⚠️ verify — {nb} book{'s' if nb!=1 else ''} in consensus"
        cleaned.append(b)
    return cleaned


def _bet(sport, match, kick, market, pick, odds, bk, our_prob, fair_prob,
         ev_val, model, has_sharp, form_h, form_a, ms_h, ms_a,
         injury, home, away, ev_id, sport_key, fdco_code, espn_lg, h2h=None, n_books=0,
         xg_h=None, xg_a=None, elo_diff=None,
         pitcher_h=None, pitcher_a=None, pitcher_h_era=None, pitcher_a_era=None,
         bullpen_h_era=None, bullpen_a_era=None, park_factor=None,
         fighter_h_record=None, fighter_a_record=None, fighter_h_style=None, fighter_a_style=None,
         rank_h=None, rank_a=None, surface_record=None, rest_days=None):
    return {
        "sport": sport, "match": match, "kick": kick,
        "market": market, "pick": pick,
        "odds": odds, "bookmaker": bk,
        "our_prob": round(our_prob*100, 1),
        "market_prob": round(fair_prob*100, 1),
        "ev": round(ev_val*100, 1),
        "kelly_stake": round(kelly(ev_val, our_prob, odds), 1),
        "model": model, "has_sharp": has_sharp,
        "form_h": form_h, "form_a": form_a,
        "ms_h": ms_h, "ms_a": ms_a,
        "injury": injury, "h2h": h2h,
        "home": home, "away": away,
        "sport_key": sport_key,   # passed to plain_render for sport-specific rationale
        "xg_h": xg_h, "xg_a": xg_a, "elo_diff": elo_diff,
        "pitcher_h": pitcher_h, "pitcher_a": pitcher_a,
        "pitcher_h_era": pitcher_h_era, "pitcher_a_era": pitcher_a_era,
        "bullpen_h_era": bullpen_h_era, "bullpen_a_era": bullpen_a_era,
        "park_factor": park_factor,
        "fighter_h_record": fighter_h_record, "fighter_a_record": fighter_a_record,
        "fighter_h_style": fighter_h_style, "fighter_a_style": fighter_a_style,
        "rank_h": rank_h, "rank_a": rank_a,
        "surface_record": surface_record, "rest_days": rest_days,
        "is_special": False, "is_model_only": False,
        "_n_books": n_books,
    }

# ── Output formatters ─────────────────────────────────────────────────────────

def fmt_form(form, name):
    if not form:
        return f"{name}: no form data"
    return f"{name}: {form['w']}W {form['d']}D {form['l']}L | {form['avg_gf']:.1f} scored, {form['avg_ga']:.1f} conceded (last {form['n']})"


def fmt_market_stats(ms, name):
    if not ms:
        return ""
    parts = []
    if ms.get("btts_pct") is not None:
        parts.append(f"BTTS {ms['btts_pct']*100:.0f}%")
    if ms.get("ou25_pct") is not None:
        parts.append(f"Over2.5 {ms['ou25_pct']*100:.0f}%")
    if ms.get("clean_pct") is not None:
        parts.append(f"Clean sheets {ms['clean_pct']*100:.0f}%")
    if ms.get("avg_corners") is not None:
        parts.append(f"~{ms['avg_corners']:.1f} corners")
    return f"{name} season: " + " | ".join(parts) if parts else ""


def format_telegram(bets, mon, sun, datapoints_left):
    week_str = f"{mon.strftime('%d %b')} – {sun.strftime('%d %b %Y')}"
    main      = [b for b in bets if not b.get("is_special") and not b.get("is_model_only")]
    spec      = [b for b in bets if b.get("is_special") and not b.get("is_model_only")]
    model_all = [b for b in bets if b.get("is_model_only")]

    lines = [
        f"📊 *Value Bets — {week_str}*",
        f"_{len(main)} EV picks · {len(spec)} special · {len(model_all)} model | Data points left: {datapoints_left}_",
        "",
    ]

    def ev_icon(b):
        ev_val = b.get("ev")
        if ev_val is None:
            conf = b.get("confidence", "")
            return "🔴" if conf == "HIGH" else ("🟠" if conf == "MEDIUM" else "📐")
        return "🟢" if ev_val >= 8 else ("🟡" if ev_val >= 5 else "🔵")

    by_sport = defaultdict(list)
    for b in sorted(main+spec, key=lambda x: -(x.get("ev") or 0)):
        by_sport[b["sport"]].append(b)

    for sport_label, sbets in sorted(by_sport.items()):
        lines.append(f"*{sport_label}*")
        for b in sbets:
            icon     = ev_icon(b)
            sharp    = " ✓sharp" if b.get("has_sharp") else ""
            ev_str   = f"+{b['ev']}%" if b.get("ev") is not None else "model"
            odds_str = f"@ {b['odds']}" if b.get("odds") else "(check bk)"
            lines.append(f"{icon} *{b['match']}*")
            lines.append(f"   {b['market']}: *{b['pick']}* {odds_str} ({b.get('bookmaker','?')})")
            ev_note = f" {b['ev_note']}" if b.get("ev_note") else ""
            lines.append(f"   EV: {ev_str}{ev_note} | Prob: {b['our_prob']}% vs market {b.get('market_prob') or '?'}%{sharp}")
            lines.append(f"   Model: {b['model']} | Kick: {b['kick']} UTC")

            if b.get("form_h") or b.get("form_a"):
                lines.append(f"   📋 {fmt_form(b.get('form_h'), b.get('home','Home'))}")
                lines.append(f"   📋 {fmt_form(b.get('form_a'), b.get('away','Away'))}")
            if b.get("h2h") and "[" not in b["h2h"] and len(b["h2h"]) > 20:
                import re as _re
                rec = _re.search(r'(Record:.*)', b["h2h"])
                avg = _re.search(r'(Avg goals.*)', b["h2h"])
                h2h_compact = " | ".join(filter(None, [
                    rec.group(1) if rec else None,
                    avg.group(1) if avg else None,
                ]))
                if h2h_compact:
                    lines.append(f"   ⚔️ H2H: {h2h_compact}")
            ms_line = " | ".join(filter(None,[
                fmt_market_stats(b.get("ms_h"), b.get("home","")),
                fmt_market_stats(b.get("ms_a"), b.get("away","")),
            ]))
            if ms_line:
                lines.append(f"   📊 {ms_line}")
            if b.get("injury") and "no injury" not in b["injury"].lower():
                lines.append(f"   🚑 {b['injury'][:200]}")
            lines.append(f"   Kelly: {b.get('kelly_stake','?')}% bankroll\n")

    # ── Model-only section ────────────────────────────────────────────────────
    if model_all:
        lines.append("*📐 Model Picks — no live odds (verify price before placing)*")
        conf_label = {"HIGH": "🔴 HIGH", "MEDIUM": "🟠 MEDIUM", "LOW": "⚪ LOW"}
        by_sport_m = defaultdict(list)
        for b in sorted(model_all, key=lambda x: {"HIGH":0,"MEDIUM":1,"LOW":2}.get(x.get("confidence","LOW"),2)):
            by_sport_m[b["sport"]].append(b)
        for sport_label, sbets in sorted(by_sport_m.items()):
            lines.append(f"*{sport_label}*")
            for b in sbets:
                conf = conf_label.get(b.get("confidence",""), "📐")
                lines.append(f"{conf} *{b['match']}*")
                lines.append(f"   {b['market']}: *{b['pick']}* | Model prob: {b['our_prob']}%")
                lines.append(f"   {b['model']} | Kick: {b['kick']} UTC")
                if b.get("form_h") or b.get("form_a"):
                    lines.append(f"   📋 {fmt_form(b.get('form_h'), b.get('home','Home'))}")
                    lines.append(f"   📋 {fmt_form(b.get('form_a'), b.get('away','Away'))}")
                if b.get("injury") and "no injury" not in b["injury"].lower():
                    lines.append(f"   🚑 {b['injury'][:150]}")
                lines.append("")

    lines.append("_⚠️ Track CLV not win rate. ¼ Kelly sizing. Always verify odds before placing._")
    return "\n".join(lines)


def format_plain(bets, mon, sun, datapoints_left):
    week_str = f"{mon.strftime('%d %b')} – {sun.strftime('%d %b %Y')}"
    print(f"\n{'='*65}")
    print(f"VALUE BET SCAN  |  {week_str}  |  Data points left: {datapoints_left}")
    print(f"{'='*65}")
    if not bets:
        print("No value bets found this week.")
        return
    main = [b for b in bets if not b.get("is_model_only")]
    model_only = [b for b in bets if b.get("is_model_only")]
    for i, b in enumerate(sorted(main, key=lambda x: -(x.get("ev") or 0)), 1):
        ev_str = f"+{b['ev']}%" if b.get("ev") is not None else "model"
        odds_str = str(b['odds']) if b.get("odds") else "check bk"
        sharp = " [sharp]" if b.get("has_sharp") else ""
        print(f"\n{i}. {b['match']}  [{b['sport']}]")
        print(f"   Kickoff : {b['kick']} UTC")
        print(f"   Pick    : {b['market']} → {b['pick']} {odds_str} ({b.get('bookmaker','?')})")
        ev_note = f"  {b['ev_note']}" if b.get("ev_note") else ""
        print(f"   EV      : {ev_str}{ev_note} | Our: {b['our_prob']}% | Market: {b.get('market_prob') or '?'}%{sharp}")
        print(f"   Model   : {b['model']}")
        if b.get("form_h"):
            print(f"   Form    : {fmt_form(b['form_h'], b.get('home','Home'))}")
        if b.get("form_a"):
            print(f"           : {fmt_form(b['form_a'], b.get('away','Away'))}")
        if b.get("h2h") and "[" not in b["h2h"]:
            import re as _re
            rec = _re.search(r'(Record:.*)', b["h2h"])
            if rec:
                print(f"   H2H     : {rec.group(1)}")
        if b.get("ms_h"):
            print(f"   Stats H : {fmt_market_stats(b['ms_h'], b.get('home','Home'))}")
        if b.get("ms_a"):
            print(f"   Stats A : {fmt_market_stats(b['ms_a'], b.get('away','Away'))}")
        if b.get("injury") and "no injury" not in b.get("injury","").lower():
            print(f"   Injuries: {b['injury'][:180]}")
        print(f"   Kelly   : {b.get('kelly_stake','?')}% of bankroll")
    if model_only:
        print(f"\n{'─'*65}")
        print("MODEL PICKS — Corners / Cards (verify odds at bookmaker)")
        print(f"{'─'*65}")
        for b in model_only:
            print(f"\n  {b['match']}  [{b['sport']}]")
            print(f"  {b['market']}: {b['pick']}  |  Our prob: {b['our_prob']}%")
            print(f"  {b['model']}")

# ── Results tracker ──────────────────────────────────────────────────────────

RESULTS_FILE = "~.openclaw/workspace/data/value_bet_results.json"
DB_PATH      = "~.openclaw/workspace/data/bets.db"


def _get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS bets (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            bet_id      TEXT UNIQUE,
            scan_date   TEXT NOT NULL,
            week        TEXT NOT NULL,
            sport       TEXT,
            match       TEXT,
            kickoff     TEXT,
            market      TEXT,
            pick        TEXT,
            odds        REAL,
            bookmaker   TEXT,
            ev          REAL,
            our_prob    REAL,
            kelly       REAL,
            model       TEXT,
            outcome     TEXT,
            settled_at  TEXT,
            notes       TEXT,
            created_at  TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_week    ON bets(week)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_outcome ON bets(outcome)")
    conn.commit()
    return conn


def _make_bet_id(scan_date, match, market, pick, bookmaker):
    import hashlib
    raw = f"{scan_date}|{match}|{market}|{pick}|{bookmaker}"
    return hashlib.sha1(raw.encode()).hexdigest()[:12]


def picks_json(bets):
    """Structured pick list for downstream consumers (continuous_bet, weekly_long_shot,
    dashboards). Confidence is post-learning (honours confidence_override)."""
    out = []
    for b in bets:
        if b.get("sport", "").startswith("⚠️"):
            continue
        if b.get("is_model_only") or b.get("ev") is None:
            continue
        out.append({
            "sport": b.get("sport", ""),
            "match": b.get("match", ""),
            "kickoff": b.get("kick", ""),
            "market": b.get("market", ""),
            "pick": b.get("pick", ""),
            "plain_pick": plain_render.plain_pick(b),
            "odds": b.get("odds"),
            "bookmaker": b.get("bookmaker", ""),
            "ev": b.get("ev"),
            "confidence_pct": plain_render.confidence_pct(b),
            "plain_rationale": plain_render.plain_rationale(b),
            "learn_status": b.get("_learn_status", "active"),
        })
    out.sort(key=lambda x: -(x["confidence_pct"] or 0))
    return out


def log_picks(bets, week_str, refresh_only=False):
    """Store this scan's picks in SQLite + JSON backup.
    Includes model-only picks (no bookmaker odds) using implied odds = 1/our_prob.
    This lets international friendlies and all-sport model picks feed into the
    compound bet chain and long shot builder.

    refresh_only: don't insert anything — just refresh closing_odds/CLV on
    pending picks that match current market prices (any scan_date).
    """
    scan_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    picks = []
    for b in bets:
        if b.get("sport","").startswith("⚠️"):
            continue
        # Stats-based prop models are informational only — no post-match feed to
        # settle corner/foul/offside counts, so don't persist them as bets.
        if b.get("is_prop_model"):
            continue
        conf_pct = plain_render.confidence_pct(b)
        # Require at least 55% confidence for model-only picks
        is_model_only = b.get("is_model_only") or b.get("ev") is None
        if is_model_only and (conf_pct is None or conf_pct < 55):
            continue
        # Use implied odds for model-only picks (no bookmaker line)
        # our_prob is stored as percentage 0-100, so divide by 100 for fraction
        our_prob_pct = b.get("our_prob") or conf_pct
        if b.get("odds"):
            used_odds = b["odds"]
            bookmaker = "1xBet"
            ev = b.get("ev")
        elif our_prob_pct and our_prob_pct > 0:
            used_odds = round(1.0 / (our_prob_pct / 100.0), 3)   # implied odds from %
            bookmaker = "model"
            ev = None   # no edge vs market, but pick is logged for chain/longshot
        else:
            continue
        picks.append({
            "sport":      b.get("sport",""),
            "match":      b.get("match",""),
            "kickoff":    b.get("kick",""),
            "market":     b.get("market",""),
            "pick":       b.get("pick",""),
            "odds":       used_odds,
            "bookmaker":  bookmaker,
            "ev":         ev,
            "our_prob":   our_prob_pct,
            "kelly":      b.get("kelly_stake"),
            "model":      b.get("model",""),
            "confidence_pct":  conf_pct,
            "plain_rationale": plain_render.plain_rationale(b),
            "scorecard":       json.dumps({
                "our_prob": our_prob_pct, "market_prob": b.get("market_prob"),
                "ev": ev, "kelly": b.get("kelly_stake"),
                "has_sharp": b.get("has_sharp", False), "model": b.get("model",""),
                "is_model_only": bool(is_model_only),
                # Evidence for plain_rationale
                "form_h": b.get("form_h"), "form_a": b.get("form_a"),
                "h2h": b.get("h2h"), "injury": b.get("injury"),
                "xg_h": b.get("xg_h"), "xg_a": b.get("xg_a"),
                "elo_diff": b.get("elo_diff"),
                "pitcher_h": b.get("pitcher_h"), "pitcher_a": b.get("pitcher_a"),
                "pitcher_h_era": b.get("pitcher_h_era"), "pitcher_a_era": b.get("pitcher_a_era"),
                "bullpen_h_era": b.get("bullpen_h_era"), "bullpen_a_era": b.get("bullpen_a_era"),
                "park_factor": b.get("park_factor"),
                "fighter_h_record": b.get("fighter_h_record"),
                "fighter_a_record": b.get("fighter_a_record"),
                "rank_h": b.get("rank_h"), "rank_a": b.get("rank_a"),
                "surface_record": b.get("surface_record"),
                "rest_days": b.get("rest_days"),
            }),
        })

    if not picks:
        return []

    if refresh_only:
        # Closing-odds pass: latest seen price ≈ close. Match pending picks by
        # (match, pick) across any scan_date so yesterday's picks for today's
        # games still get a closing price.
        updated = 0
        try:
            conn = _get_db()
            for p in picks:
                if not p["odds"]:
                    continue
                cur = conn.execute("""
                    UPDATE bets
                       SET closing_odds = ?,
                           clv = ROUND((odds / ?) * 100.0 - 100.0, 2)
                     WHERE match = ? AND pick = ?
                       AND outcome IS NULL AND odds IS NOT NULL
                       AND bookmaker NOT IN ('model')
                """, (p["odds"], p["odds"], p["match"], p["pick"]))
                updated += cur.rowcount
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[warn] CLV refresh failed: {e}")
        print(f"[CLV] refreshed closing odds on {updated} pending pick rows")
        return []

    # ── SQLite (primary) ──────────────────────────────────────────────────────
    inserted_ids = []
    try:
        conn = _get_db()
        for p in picks:
            bid = _make_bet_id(scan_date, p["match"], p["market"], p["pick"], p["bookmaker"])
            conn.execute("""
                INSERT OR IGNORE INTO bets
                  (bet_id, scan_date, week, sport, match, kickoff, market, pick,
                   odds, bookmaker, ev, our_prob, kelly, model,
                   confidence_pct, plain_rationale, scorecard)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                bid, scan_date, week_str,
                p["sport"], p["match"], p["kickoff"],
                p["market"], p["pick"],
                p["odds"], p["bookmaker"],
                p["ev"], p["our_prob"], p["kelly"], p["model"],
                p["confidence_pct"], p["plain_rationale"], p["scorecard"],
            ))
            if conn.execute("SELECT changes()").fetchone()[0]:
                inserted_ids.append(bid)
            else:
                # Already-seen pending pick → refresh closing odds (last price ≈ close)
                # and compute CLV vs the original entry odds. Positive = we beat the close.
                if p["odds"]:
                    conn.execute("""
                        UPDATE bets
                           SET closing_odds = ?,
                               clv = ROUND((odds / ?) * 100.0 - 100.0, 2)
                         WHERE bet_id = ? AND outcome IS NULL AND odds IS NOT NULL
                    """, (p["odds"], p["odds"], bid))
            # Fallback re-match by (match, pick) for older rows whose bet_id used a
            # different bookmaker string — keeps CLV flowing across the routing change.
            if p["odds"]:
                conn.execute("""
                    UPDATE bets
                       SET closing_odds = ?,
                           clv = ROUND((odds / ?) * 100.0 - 100.0, 2)
                     WHERE match = ? AND pick = ? AND scan_date = ?
                       AND outcome IS NULL AND odds IS NOT NULL AND bet_id != ?
                       AND bookmaker NOT IN ('model')
                """, (p["odds"], p["odds"], p["match"], p["pick"], scan_date, bid))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[warn] SQLite write failed: {e}")

    # ── JSON backup ───────────────────────────────────────────────────────────
    try:
        with open(RESULTS_FILE) as f:
            data = json.load(f)
    except Exception:
        data = []
    existing = next((e for e in data if e.get("week") == week_str), None)
    if existing:
        existing["picks"] = picks
        existing["updated_at"] = datetime.now(timezone.utc).isoformat()
    else:
        data.append({
            "week":           week_str,
            "scan_date":      scan_date,
            "picks":          picks,
            "pick_count":     len(picks),
            "actual_outcome": None,
            "notes":          "",
        })
    with open(RESULTS_FILE, "w") as f:
        json.dump(data, f, indent=2)

    return inserted_ids


def settle_week(week_str, outcome):
    """Mark all unsettled picks for a week as won or lost."""
    outcome = "win" if outcome.upper() in ("W", "WIN") else "loss"
    # SQLite
    try:
        conn = _get_db()
        conn.execute(
            "UPDATE bets SET outcome=?, settled_at=datetime('now') WHERE week=? AND outcome IS NULL",
            (outcome, week_str)
        )
        changed = conn.execute("SELECT changes()").fetchone()[0]
        conn.commit()
        conn.close()
        print(f"Week {week_str}: {changed} bets marked as {outcome}.")
    except Exception as e:
        print(f"[warn] SQLite settle failed: {e}")
    # JSON backup
    try:
        with open(RESULTS_FILE) as f:
            data = json.load(f)
        entry = next((e for e in data if e.get("week") == week_str), None)
        if entry:
            entry["actual_outcome"] = outcome
            entry["settled_at"] = datetime.now(timezone.utc).isoformat()
            with open(RESULTS_FILE, "w") as f:
                json.dump(data, f, indent=2)
    except Exception:
        pass


SPORT_DISPLAY_TO_ESPN = {
    # Display label (with emoji) → ESPN scoreboard path for auto-settle
    # Soccer
    "⚽ EPL":                          "soccer/eng.1",
    "⚽ ENG Championship":             "soccer/eng.2",
    "⚽ ENG League One":               "soccer/eng.3",
    "⚽ ENG League Two":               "soccer/eng.4",
    "⚽ La Liga":                      "soccer/esp.1",
    "⚽ La Liga 2":                    "soccer/esp.2",
    "⚽ Serie A":                      "soccer/ita.1",
    "⚽ Serie B":                      "soccer/ita.2",
    "⚽ Bundesliga":                   "soccer/ger.1",
    "⚽ 2. Bundesliga":                "soccer/ger.2",
    "⚽ Ligue 1":                      "soccer/fra.1",
    "⚽ Ligue 2":                      "soccer/fra.2",
    "⚽ Eredivisie":                   "soccer/ned.1",
    "⚽ Primeira Liga":                "soccer/por.1",
    "⚽ Scottish Prem":                "soccer/sco.1",
    "⚽ Suer Lig":                     "soccer/tur.1",
    "⚽ Belgian Pro League":           "soccer/bel.1",
    "⚽ Greek Super League":           "soccer/gre.1",
    "⚽ Austrian Bundesliga":          "soccer/aut.1",
    "⚽ Czech Liga":                   "soccer/cze.1",
    "⚽ Russian Premier":              "soccer/rus.1",
    "⚽ Danish Superliga":             "soccer/den.1",
    "⚽ Allsvenskan":                  "soccer/swe.1",
    "⚽ Eliteserien":                  "soccer/nor.1",
    "⚽ Swiss Super League":           "soccer/sui.1",
    "⚽ Croatian HNL":                 "soccer/cro.1",
    "⚽ Serbian SuperLiga":            "soccer/srb.1",
    "⚽ Ukrainian Premier":            "soccer/ukr.1",
    "⚽ Liga 1 Romania":               "soccer/rou.1",
    "⚽ Ekstraklasa":                  "soccer/pol.1",
    "⚽ Hungarian NB1":                "soccer/hun.1",
    "⚽ Slovak Super Liga":            "soccer/svk.1",
    "⚽ UCL":                          "soccer/uefa.champions",
    "⚽ UEL":                          "soccer/uefa.europa",
    "⚽ UECL":                         "soccer/uefa.europa.conf",
    "⚽ FA Cup":                       "soccer/eng.fa",
    "⚽ EFL Cup":                      "soccer/eng.league_cup",
    "⚽ Copa del Rey":                 "soccer/esp.copa_del_rey",
    "⚽ Coppa Italia":                 "soccer/ita.coppa_italia",
    "⚽ DFB-Pokal":                    "soccer/ger.dfb_pokal",
    "⚽ Coupe de France":              "soccer/fra.coupe_de_france",
    "⚽ Brasileirao Serie A":          "soccer/bra.1",
    "⚽ Brasileirao Serie B":          "soccer/bra.2",
    "⚽ Argentine Primera":            "soccer/arg.1",
    "⚽ Liga MX":                      "soccer/mex.1",
    "⚽ Colombian Primera A":          "soccer/col.1",
    "⚽ Chilean Primera":              "soccer/chi.1",
    "⚽ Ecuadorian Liga Pro":          "soccer/ecu.1",
    "⚽ Peruvian Primera":             "soccer/per.1",
    "⚽ Uruguayan Primera":            "soccer/uru.1",
    "⚽ Venezuelan Primera":           "soccer/ven.1",
    "⚽ Paraguayan Division":          "soccer/par.1",
    "⚽ MLS":                          "soccer/usa.1",
    "⚽ USL Championship":             "soccer/usa.2",
    "⚽ Copa Libertadores":            "soccer/conmebol.libertadores",
    "⚽ Copa Sudamericana":            "soccer/conmebol.sudamericana",
    "⚽ CONCACAF Champions Cup":       "soccer/concacaf.champions",
    "⚽ J1 League (Japan)":            "soccer/jpn.1",
    "⚽ J2 League (Japan)":            "soccer/jpn.2",
    "⚽ K League 1":                   "soccer/kor.1",
    "⚽ Chinese Super League":         "soccer/chn.1",
    "⚽ A-League (Australia)":         "soccer/aus.1",
    "⚽ Indian Super League":          "soccer/ind.1",
    "⚽ Saudi Pro League":             "soccer/sau.1",
    "⚽ UAE Pro League":               "soccer/uae.1",
    "⚽ Egyptian Premier League":      "soccer/egy.1",
    "⚽ NPFL (Nigeria)":               "soccer/nig.1",
    "⚽ South African PSL":            "soccer/rsa.1",
    "⚽ Moroccan Botola":              "soccer/mar.1",
    "🌍 World Cup":                    "soccer/fifa.worldcup",
    "⚽ Intl Friendlies":              "soccer/fifa.friendly",
    "⚽ AFCON":                        "soccer/afr.nations",
    "⚽ Copa America":                 "soccer/conmebol.america",
    "⚽ UEFA Euros":                   "soccer/uefa.euro",
    "⚽ CONCACAF Gold Cup":            "soccer/concacaf.gold",
    "⚽ WCQ Europe":                   "soccer/fifa.worldq.uefa",
    "⚽ WCQ South America":            "soccer/fifa.worldq.conmebol",
    "⚽ WCQ CONCACAF":                 "soccer/fifa.worldq.concacaf",
    "⚽ WCQ Africa":                   "soccer/fifa.worldq.caf",
    "⚽ WCQ Asia":                     "soccer/fifa.worldq.afc",
    "⚽ UCL Qualifying":               "soccer/uefa.champs.qual",
    "⚽ UEL Qualifying":               "soccer/uefa.europa.qual",
    "⚽ UEFA Nations League":          "soccer/uefa.nations",
    "⚽ Women's World Cup":            "soccer/fifa.wwc",
    # Legacy aliases
    "⚽ UCL":                          "soccer/uefa.champions",
    "⚽ UEL":                          "soccer/uefa.europa",
    "⚽ Premier League":               "soccer/eng.1",
    "⚽ Champions League":             "soccer/uefa.champions",
    "⚽ Europa League":                "soccer/uefa.europa",
    "⚽ Brazil Série A":               "soccer/bra.1",
    # Basketball
    "🏀 NBA":                          "basketball/nba",
    "🏀 NBA Playoffs":                 "basketball/nba",
    "🏀 WNBA":                         "basketball/wnba",
    "🏀 NCAAB":                        "basketball/mens-college-basketball",
    "🏀 EuroLeague":                   "basketball/euroleague",
    "🏀 NBL (Australia)":              "basketball/nbl",
    "🏀 NBA G-League":                 "basketball/nba-g-league",
    # Baseball
    "⚾ MLB":                          "baseball/mlb",
    "⚾ MLB Playoffs":                 "baseball/mlb",
    "⚾ NPB (Japan)":                  "baseball/npb",
    "⚾ KBO (Korea)":                  "baseball/kbo",
    "⚾ LMB (Mexico)":                 "baseball/lmb",
    "⚾ KBO":                          "baseball/kbo",
    "⚾ NPB":                          "baseball/npb",
    # Ice Hockey
    "🏒 NHL":                          "hockey/nhl",
    "🏒 NHL Playoffs":                 "hockey/nhl",
    "🏒 AHL":                          "hockey/ahl",
    "🏒 KHL (Russia)":                 "hockey/khl",
    "🏒 SHL (Sweden)":                 "hockey/shl",
    "🏒 Liiga (Finland)":              "hockey/liiga",
    "🏒 DEL (Germany)":                "hockey/del",
    "🏒 NL (Switzerland)":             "hockey/nl",
    "🏒 Czech Extraliga":              "hockey/extraliga",
    "🏒 HockeyAllsvenskan (SWE)":      "hockey/hockeyallsvenskan",
    "🏒 IIHF World Championship":      "hockey/world-men",
    # American Football
    "🏈 NFL":                          "football/nfl",
    "🏈 NFL Playoffs":                 "football/nfl",
    "🏈 NCAAF":                        "football/college-football",
    "🏈 CFL":                          "football/cfl",
    "🏈 XFL":                          "football/xfl",
    # Rugby League
    "🏉 NRL":                          "rugby-league/nrl",
    "🏉 State of Origin":              "rugby-league/nrl",
    "🏉 Super League (Rugby)":         "rugby-league/super-league",
    # Rugby Union
    "🏉 Rugby Premiership (ENG)":      "rugby/premiership",
    "🏉 URC (Rugby)":                  "rugby/urc",
    "🏉 Top 14 (France Rugby)":        "rugby/top14",
    "🏉 Super Rugby Pacific":          "rugby/super-rugby",
    "🏉 Rugby Test Match":             "rugby/test-match",
    "🏉 Rugby Champions Cup":          "rugby/champions-cup",
    "🏉 Super League":                 "rugby-league/super-league",
    "🏉 Rugby Union":                  "rugby/test-match",
    # Cricket
    "🏏 IPL":                          "cricket/ipl",
    "🏏 T20 Blast (England)":          "cricket/t20_blast",
    "🏏 BBL (Australia)":              "cricket/bbl",
    "🏏 PSL (Pakistan)":               "cricket/psl",
    "🏏 SA20 (South Africa)":          "cricket/sa20",
    "🏏 CPL (Caribbean)":              "cricket/cpl",
    "🏏 ICC T20 World Cup":            "cricket/icc-mens-t20",
    "🏏 ICC ODI World Cup":            "cricket/icc-mens-odi",
    "🏏 International Cricket":        "cricket/international",
    "🏏 T20 Blast":                    "cricket/t20_blast",
    # Aussie Rules
    "🏑 AFL":                          "australian-football/afl",
    "🏑 AFLW":                         "australian-football/aflw",
    # Combat
    "🥊 MMA / UFC":                    "mma/ufc",
    "🥊 Bellator MMA":                 "mma/bellator",
    "🥊 ONE Championship":             "mma/one",
    "🥊 Boxing":                       "boxing",
    "🥊 MMA":                          "mma/ufc",
    # Tennis
    "🎾 ATP":                          "tennis/atp",
    "🎾 WTA":                          "tennis/wta",
    "🎾 ATP French Open":              "tennis/atp",
    "🎾 WTA French Open":              "tennis/wta",
    # Golf
    "⛳ PGA Tour":                     "golf/pga",
    "⛳ DP World Tour":                "golf/euro",
    "⛳ LPGA Tour":                    "golf/lpga",
    # Motorsports
    "🏎 Formula 1":                    "racing/f1",
    "🏎 NASCAR Cup":                   "racing/nascar",
    "🏎 IndyCar":                      "racing/indycar",
    "🏎 MotoGP":                       "racing/motogp",
    # Esports
    "🎮 LoL Esports":                  "esports/lol",
    "🎮 CS2":                          "esports/cs2",
    "🎮 Valorant":                     "esports/valorant",
    "🎮 Dota 2":                       "esports/dota2",
    "🎮 Overwatch League":             "esports/overwatch",
    # Cycling
    "🚴 Tour de France":               "cycling/tour-de-france",
    "🚴 Giro d'Italia":                "cycling/giro",
    "🚴 Vuelta a Espana":              "cycling/vuelta",
    # Handball, Volleyball, Table Tennis, Darts, Snooker — no ESPN path yet
    "🤾 Handball":                     None,
    "🤾 Handball Bundesliga":          None,
    "🤾 EHF Champions League":         None,
    "🏐 VNL (Volleyball Nations League)": None,
    "🏓 WTT Contender":                None,
    "🎯 Premier League Darts":         None,
    "🎱 Snooker Masters":              None,
}


def espn_scoreboard(sport_path, date_str):
    """Fetch final scores for a given date from the ESPN hidden scoreboard API.
    date_str: YYYY-MM-DD. Returns list of dicts with home/away team names + scores."""
    if not sport_path:
        return []
    d = date_str.replace("-", "")
    url = f"https://site.api.espn.com/apis/site/v2/sports/{sport_path}/scoreboard?dates={d}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=12) as r:
            data = json.loads(r.read().decode("utf-8", errors="replace"))
    except Exception:
        return []
    out = []
    for evt in data.get("events", []):
        comp = evt.get("competitions", [{}])[0]
        teams = comp.get("competitors", [])
        if len(teams) < 2:
            continue
        home = next((t for t in teams if t.get("homeAway") == "home"), teams[0])
        away = next((t for t in teams if t.get("homeAway") == "away"), teams[1])
        # Only settle if game is final
        status = comp.get("status", {}).get("type", {}).get("name", "")
        if status not in ("STATUS_FINAL", "STATUS_FULL_TIME", "Final"):
            continue
        out.append({
            "home":  home.get("team", {}).get("displayName", ""),
            "away":  away.get("team", {}).get("displayName", ""),
            "home_score": int(home.get("score", 0) or 0),
            "away_score": int(away.get("score", 0) or 0),
            "completed": comp.get("status", {}).get("type", {}).get("completed", False),
        })
    return out


def _normalize_name(name):
    """Lowercase, drop common suffixes, collapse whitespace. For fuzzy team match."""
    n = (name or "").lower()
    for suf in (" fc", " cf", " sc", " afc", " united", " city", " town", " basketball", " fc.", " the", " fc",
                " baseball club", " kbo", " yomiuri", " hanshin", " softbank", " seibu", " nippon-ham",
                " orix", " rakuten", " lotte", " kia", " samsung", " lg", " doosan", " kt", " hanwha", " nc", " ssg",
                " eagles", " tigers", " bears", " giants", " lions", " twins", " wyverns", " heroes", " dinos", " landers"):
        n = n.replace(suf, "")
    # Remove accented chars
    import unicodedata as _u
    n = "".join(c for c in _u.normalize("NFD", n) if _u.category(c) != "Mn")
    return " ".join(n.split())


def _pick_won(bet, score):
    """Did our pick win given the final score?"""
    if not score:
        return None
    pick = (bet.get("pick") or "").lower()
    market = (bet.get("market") or "").lower()
    home = _normalize_name(bet.get("home", ""))
    away = _normalize_name(bet.get("away", ""))
    pick_norm = _normalize_name(bet.get("pick", ""))
    hs, aws = score["home_score"], score["away_score"]

    # Double chance: "<team> or Draw" — wins if that side avoids defeat.
    if "double chance" in market or " or draw" in pick:
        team_part = _normalize_name(pick.split(" or draw")[0])
        if team_part == home or home in team_part or team_part in home:
            return hs >= aws
        if team_part == away or away in team_part or team_part in away:
            return aws >= hs
        return None

    # 1X2 markets: home/draw/away
    if market in ("1x2", "h2h", "moneyline", "ml", "match result"):
        # Pick can be team name, "Draw"/"X"/"Tie", or "Home"/"Away"
        if pick in ("draw", "x", "tie"):
            return hs == aws
        if pick_norm in (home, "home"):
            return hs > aws
        if pick_norm in (away, "away"):
            return aws > hs
        return None

    # Totals (O/U): "Over 2.5" / "Under 2.5"
    if "over" in pick or "under" in pick:
        import re as _re
        m = _re.search(r"(\d+(?:\.\d+)?)", pick)
        if not m:
            return None
        line = float(m.group(1))
        total = hs + aws
        if pick.startswith("over"):
            return total > line
        return total < line

    # Handicap / Spread
    if "handicap" in market or "spread" in market or "+" in pick or "-" in pick:
        import re as _re
        m = _re.search(r"([+-]?\d+(?:\.\d+)?)", pick)
        if not m:
            return None
        line = float(m.group(1))
        # Apply home/away to the spread
        is_home = pick_norm in (home, "home") or home in pick_norm
        margin = (hs - aws) if is_home else (aws - hs)
        # Cover: margin + line > 0 (in bookie's frame)
        return (margin + line) > 0

    return None


def _decide_outcome(bet, home_score, away_score):
    """Given a bet dict and final scores, return 'win'/'loss'/None."""
    import re as _re
    market = (bet.get("market") or "").lower()
    pick   = (bet.get("pick") or "").lower()
    home   = bet.get("home", "")
    away   = bet.get("away", "")
    hs, aws = home_score, away_score

    if "1x2" in market or "h2h" in market or "moneyline" in market or "match winner" in market or not market:
        winner = _normalize_name(home) if hs > aws else (_normalize_name(away) if aws > hs else "draw")
        pick_n = _normalize_name(pick)
        if "draw" in pick_n and winner == "draw":
            return "win"
        if winner == "draw" and "draw" not in pick_n:
            return "loss"
        if winner != "draw" and (winner in pick_n or pick_n in winner):
            return "win"
        if winner != "draw" and "draw" not in pick_n:
            return "loss"
        return None

    if "over" in pick or "under" in pick:
        m = _re.search(r"(\d+\.?\d*)", market + " " + pick)
        if m:
            line = float(m.group(1))
            total = hs + aws
            if "over" in pick: return "win" if total > line else "loss"
            else: return "win" if total < line else "loss"

    if "btts" in market or "both teams" in market:
        both = (hs > 0 and aws > 0)
        if "yes" in pick: return "win" if both else "loss"
        else: return "win" if not both else "loss"

    return None


def _write_outcome(bet_id_or_int, outcome, score_str=None):
    """Write outcome + score to the bets table."""
    conn = _get_db()
    if score_str:
        conn.execute("UPDATE bets SET outcome=?, result_score=?, settled_at=datetime('now') WHERE id=?",
                     (outcome, score_str, bet_id_or_int))
    else:
        conn.execute("UPDATE bets SET outcome=?, settled_at=datetime('now') WHERE id=?",
                     (outcome, bet_id_or_int))
    conn.commit(); conn.close()


def _espn_path_to_sofa(espn_path):
    """Map ESPN sport path prefix → SofaScore sport slug (or None if unsupported)."""
    if not espn_path:
        return None
    p = espn_path.lower()
    if p.startswith("soccer"):      return "football"
    if p.startswith("basketball"):  return "basketball"
    if p.startswith("baseball"):    return "baseball"
    if p.startswith("hockey"):      return "ice-hockey"
    if p.startswith("tennis"):      return "tennis"
    if p.startswith("rugby"):       return "rugby"
    if p.startswith("cricket"):     return "cricket"
    if p.startswith("mma"):         return "mma"
    if p.startswith("boxing"):      return "boxing"
    if p.startswith("esports"):     return "esports"
    if p.startswith("cycling"):     return "cycling"
    return None


# Sports whose display labels have no ESPN path but DO exist in SofaScore
_SOFA_NO_ESPN = {
    "handball":    "handball",
    "volleyball":  "volleyball",
    "table tennis":"table-tennis",
    "table-tennis":"table-tennis",
    "table_tennis":"table-tennis",
    "darts":       "darts",
    "snooker":     "snooker",
    "futsal":      "futsal",
    "waterpolo":   "waterpolo",
    "water polo":  "waterpolo",
}


def _display_to_sofa(sport_display):
    """Map a sport display label (may have emoji) to a SofaScore sport slug."""
    import re as _re, unicodedata as _u
    s = sport_display or ""
    s = "".join(c for c in _u.normalize("NFD", s) if _u.category(c) != "Mn")
    s = _re.sub(r"[^\w\s-]", "", s).lower().strip()
    for key, slug in _SOFA_NO_ESPN.items():
        if key in s:
            return slug
    return None


def _sofa_settle_bets(bets_list, sofa_slug, date_str):
    """
    Try to settle a list of bet dicts using SofaScore.
    Returns (settled, won, lost, no_score, no_pick, errors).
    """
    settled = won = lost = no_score = no_pick = errors = 0
    for bet in bets_list:
        if not (bet.get("home") and bet.get("away")):
            no_score += 1
            continue
        ev = SOFA.get_score(bet["home"], bet["away"], sofa_slug, date_str)
        if not ev or ev.get("status") != "finished" or ev.get("home_score") is None:
            no_score += 1
            continue
        hs = ev["home_score"]; aws = ev["away_score"]
        outcome_result = _decide_outcome(bet, hs, aws)
        if outcome_result is None:
            no_pick += 1
            continue
        sc = f"{ev.get('home','')} {hs} - {aws} {ev.get('away','')}"
        try:
            _write_outcome(bet["id"], outcome_result, sc)
            settled += 1
            if outcome_result == "win": won += 1
            else: lost += 1
        except Exception:
            errors += 1
    return settled, won, lost, no_score, no_pick, errors


def settle_pending(days_back=14):
    """Auto-settle unsettled bets whose kickoff has passed. Uses ESPN → API-Football → SofaScore.
    Returns dict with stats: {settled, won, lost, skipped, errors}."""
    conn = _get_db()
    rows = conn.execute("""
        SELECT id, bet_id, sport, match, kickoff, market, pick, odds, ev, our_prob, bookmaker
        FROM bets WHERE outcome IS NULL AND kickoff IS NOT NULL
    """).fetchall()
    # Drop model-only picks — those are system suggestions, not placed bets. Don't
    # auto-settle them: they were never staked so a W/L is meaningless. They stay
    # pending until the user marks them as placed (or not_placed manually).
    rows = [r for r in rows if (r["bookmaker"] or "").lower() != "model"]
    conn.close()

    # Eligible = games that kicked off at least 2.5h ago (typical match ~105min incl. ET/penalties)
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=2, minutes=30)).replace(tzinfo=None)
    eligible = []
    skipped_parse = 0
    for r in rows:
        k = r["kickoff"]
        if not k:
            continue
        try:
            kdt = datetime.fromisoformat(k.replace("Z", "+00:00")).replace(tzinfo=None)
        except Exception:
            skipped_parse += 1
            continue
        if kdt > cutoff:
            continue  # game hasn't happened yet
        # Parse home/away from match field ("Home vs Away" or "Home v Away")
        import re as _re
        mv = _re.match(r"(.+?)\s+(?:vs\.?|v\.?|@|at)\s+(.+)", r["match"] or "", _re.IGNORECASE)
        if not mv:
            skipped_parse += 1
            continue
        r = dict(r)
        r["home"] = mv.group(1).strip()
        r["away"] = mv.group(2).strip()
        eligible.append(r)
    print(f"[settle_pending] {len(rows)} unsettled, {len(eligible)} eligible (parse-skipped: {skipped_parse})", file=sys.stderr)
    if not eligible:
        return {"settled": 0, "won": 0, "lost": 0, "skipped": 0, "errors": 0}

    # Group by (sport_display, date) for batched ESPN queries
    by_query = defaultdict(list)
    sofa_direct = defaultdict(list)  # bets with no ESPN path → try SofaScore directly
    for r in eligible:
        sport_display = r.get("sport", "")
        # Try exact match first
        espn_path = SPORT_DISPLAY_TO_ESPN.get(sport_display)
        # Then try fuzzy match (drop emoji and try substring)
        if not espn_path and espn_path is not None:
            sport_clean = sport_display.encode("ascii", "ignore").decode().strip().lower()
            for k, v in SPORT_DISPLAY_TO_ESPN.items():
                k_clean = k.encode("ascii", "ignore").decode().strip().lower()
                if sport_clean and (sport_clean in k_clean or k_clean in sport_clean):
                    espn_path = v
                    break
        if espn_path is None:
            # No ESPN mapping — route straight to SofaScore
            sofa_slug = _display_to_sofa(sport_display)
            if sofa_slug:
                date_str = r["kickoff"][:10]
                sofa_direct[(sofa_slug, date_str)].append(r)
            continue
        date_str = r["kickoff"][:10]
        by_query[(espn_path, date_str)].append(r)

    settled = won = lost = skipped = errors = 0
    no_score = no_match = no_pick = 0
    for (espn_path, date_str), bets in by_query.items():
        scores = espn_scoreboard(espn_path, date_str)
        # Games kicking off near midnight UTC often appear on day-before in ESPN.
        # Also try day-after for very late kickoffs stored as next UTC day.
        if not scores:
            from datetime import date as _date, timedelta as _td
            try:
                d = _date.fromisoformat(date_str)
                scores = espn_scoreboard(espn_path, (d - _td(days=1)).strftime("%Y-%m-%d")) or []
                if not scores:
                    scores = espn_scoreboard(espn_path, (d + _td(days=1)).strftime("%Y-%m-%d")) or []
            except Exception:
                pass
        if not scores:
            # Tier 2: API-Football for soccer bets
            remaining_bets = list(bets)
            is_soccer_path = "soccer" in espn_path
            if is_soccer_path:
                remaining_bets = []
                for bet in bets:
                    if bet.get("home") and bet.get("away"):
                        apif_score = APIF.get_score(bet["home"], bet["away"], date_str)
                        if apif_score and apif_score.get("home_score") is not None:
                            hs = apif_score["home_score"]; aws = apif_score["away_score"]
                            outcome_result = _decide_outcome(bet, hs, aws)
                            if outcome_result is not None:
                                sc = f"{apif_score['home']} {hs} - {aws} {apif_score['away']}"
                                try:
                                    _write_outcome(bet["id"], outcome_result, sc)
                                    settled += 1
                                    if outcome_result == "win": won += 1
                                    else: lost += 1
                                except Exception:
                                    errors += 1
                            else:
                                no_pick += 1
                        else:
                            remaining_bets.append(bet)
                    else:
                        remaining_bets.append(bet)
                if not remaining_bets:
                    continue
            # Tier 3: SofaScore fallback for all sports
            sofa_slug = _espn_path_to_sofa(espn_path)
            if sofa_slug and remaining_bets:
                s, w, l, ns, np_, er = _sofa_settle_bets(remaining_bets, sofa_slug, date_str)
                settled += s; won += w; lost += l; no_score += ns; no_pick += np_; errors += er
            elif remaining_bets:
                no_score += len(remaining_bets)
            continue
        # Build lookup by normalized names
        score_by_key = {}
        for s in scores:
            key = (_normalize_name(s["home"]), _normalize_name(s["away"]))
            score_by_key[key] = s
        for bet in bets:
            h = _normalize_name(bet["home"])
            a = _normalize_name(bet["away"])
            score = score_by_key.get((h, a))
            if not score:
                score = score_by_key.get((a, h))
            if not score:
                # Last resort: substring match on any side
                for key, sc in score_by_key.items():
                    kh, ka = key
                    if (h and (h in kh or kh in h)) or (a and (a in ka or ka in a)):
                        score = sc
                        break
            if not score:
                no_match += 1
                continue
            won_pick = _pick_won(bet, score)
            if won_pick is None:
                no_pick += 1
                continue
            outcome = "win" if won_pick else "loss"
            try:
                score_str = f"{score.get('home','')} {score.get('home_score','')} - {score.get('away_score','')} {score.get('away','')}"
                _write_outcome(bet["id"], outcome, score_str)
                settled += 1
                if won_pick: won += 1
                else: lost += 1
            except Exception:
                errors += 1
    # Tier 3: SofaScore for sports with no ESPN mapping (handball, table tennis, volleyball, darts, snooker…)
    for (sofa_slug, date_str), bets in sofa_direct.items():
        s, w, l, ns, np_, er = _sofa_settle_bets(bets, sofa_slug, date_str)
        settled += s; won += w; lost += l; no_score += ns; no_pick += np_; errors += er

    if no_pick or no_match or no_score:
        print(f"[settle_pending] {settled} settled; {no_score} no-score, {no_match} no-match, {no_pick} no-pick-decision", file=sys.stderr)
    return {"settled": settled, "won": won, "lost": lost, "skipped": no_score + no_match + no_pick, "errors": errors}


def show_accuracy():
    """Print pick accuracy stats from SQLite."""
    try:
        conn = _get_db()
        total_all = conn.execute("SELECT COUNT(*) FROM bets").fetchone()[0]
        total_settled = conn.execute("SELECT COUNT(*) FROM bets WHERE outcome IS NOT NULL").fetchone()[0]
        wins = conn.execute("SELECT COUNT(*) FROM bets WHERE outcome='win'").fetchone()[0]
        pending = conn.execute("SELECT COUNT(*) FROM bets WHERE outcome IS NULL").fetchone()[0]
        avg_ev = conn.execute("SELECT AVG(ev) FROM bets WHERE outcome IS NOT NULL").fetchone()[0]
        conn.close()
    except Exception:
        print("No bet history yet.")
        return
    losses = total_settled - wins
    print(f"\nValue Bet Record")
    print(f"  Total logged  : {total_all}")
    print(f"  Settled       : {total_settled}")
    print(f"  Pending       : {pending}")
    if total_settled:
        pct = wins / total_settled * 100
        print(f"  Wins / Losses : {wins} / {losses}  ({pct:.0f}%)")
    if avg_ev:
        print(f"  Avg EV/pick   : +{avg_ev*100:.1f}%")
    print(f"\n  Full breakdown: python3 bet_history.py --stats")


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sport",    default="all")
    parser.add_argument("--min-ev",   type=float, default=DEFAULT_MIN_EV)
    parser.add_argument("--format",   default="plain", choices=["plain","telegram","simple","json"])
    parser.add_argument("--no-learn", action="store_true", help="Skip learned adjustments (raw model output)")
    parser.add_argument("--band",     default="", help="Odds band filter, e.g. 1.50-2.19 (high-probability events)")
    parser.add_argument("--accuracy", action="store_true", help="Show pick accuracy stats")
    parser.add_argument("--settle",   default="", help="Mark current week W or L (e.g. --settle W)")
    parser.add_argument("--auto-settle", action="store_true", help="Auto-settle pending bets via ESPN scoreboard")
    parser.add_argument("--refresh-clv", action="store_true",
                        help="Scan prices but log nothing new — only refresh closing odds/CLV on pending picks")
    args = parser.parse_args()

    if args.refresh_clv:
        # See everything the market offers: no EV floor, no band, no benching.
        args.min_ev = -100.0
        args.band = ""
        args.no_learn = True

    load_env()

    # Shortcut commands that don't need a full scan
    if args.accuracy:
        show_accuracy()
        return

    if args.auto_settle:
        res = settle_pending()
        print(f"Auto-settle: {res['settled']} settled ({res['won']}W / {res['lost']}L), {res['skipped']} skipped, {res['errors']} errors")
        if res['settled'] > 0:
            show_accuracy()
        return

    mon, sun = week_window()

    if args.settle:
        outcome = "win" if args.settle.upper() == "W" else "loss"
        week_str = mon.strftime("%Y-W%V")
        settle_week(week_str, outcome)
        return

    # Sport group aliases → prefix or substring match
    SPORT_GROUPS = {
        "soccer":           "soccer_",
        "football":         "soccer_",
        "basketball":       "basketball_",
        "tennis":           "tennis_",
        "mma":              "mma_",
        "boxing":           "boxing_",
        "combat":           ("mma_", "boxing_"),
        "baseball":         "baseball_",
        "mlb":              "baseball_mlb",
        "rugby":            "rugbyleague_",
        "nrl":              "rugbyleague_nrl",
        "hockey":           "icehockey_",
        "nhl":              "icehockey_nhl",
        "cricket":          "cricket_",
        "afl":              "aussierules_",
        "aussie":           "aussierules_",
        "handball":         "handball_",
        "nfl":              "americanfootball_nfl",
        "americanfootball": "americanfootball_",
        "wnba":             "basketball_wnba",
        "nba":              "basketball_nba",
        "ncaaf":            "americanfootball_ncaaf",
        "ncaab":            "basketball_ncaab",
        "college":          ("americanfootball_ncaaf", "basketball_ncaab"),
        "worldcup":         "soccer_fifa_world_cup",
        "world cup":        "soccer_fifa_world_cup",
        "wc":               "soccer_fifa_world_cup",
        "fifa":             "soccer_fifa_world_cup",
    }

    # ── In-season filter: with --sport all, only scan sports actually playing ──
    # this month. Scanning all 150 keys serially trips TheRundown rate limits and
    # times the pipeline out; off-season keys return nothing anyway.
    SEASON_MONTHS = {
        # Family prefix → months when in season (1-12)
        "soccer_epl": {8,9,10,11,12,1,2,3,4,5},
        "soccer_england": {8,9,10,11,12,1,2,3,4,5},
        "soccer_spain": {8,9,10,11,12,1,2,3,4,5},
        "soccer_italy": {8,9,10,11,12,1,2,3,4,5},
        "soccer_germany": {8,9,10,11,12,1,2,3,4,5},
        "soccer_france": {8,9,10,11,12,1,2,3,4,5},
        "soccer_netherlands": {8,9,10,11,12,1,2,3,4,5},
        "soccer_portugal": {8,9,10,11,12,1,2,3,4,5},
        "soccer_scotland": {8,9,10,11,12,1,2,3,4,5},
        "soccer_turkey": {8,9,10,11,12,1,2,3,4,5},
        "soccer_belgium": {8,9,10,11,12,1,2,3,4,5},
        "soccer_greece": {8,9,10,11,12,1,2,3,4,5},
        "soccer_austria": {8,9,10,11,12,1,2,3,4,5},
        "soccer_czech": {8,9,10,11,12,1,2,3,4,5},
        "soccer_russia": {8,9,10,11,12,1,2,3,4,5},
        "soccer_croatia": {8,9,10,11,12,1,2,3,4,5},
        "soccer_serbia": {8,9,10,11,12,1,2,3,4,5},
        "soccer_ukraine": {8,9,10,11,12,1,2,3,4,5},
        "soccer_romania": {8,9,10,11,12,1,2,3,4,5},
        "soccer_poland": {8,9,10,11,12,1,2,3,4,5},
        "soccer_hungary": {8,9,10,11,12,1,2,3,4,5},
        "soccer_slovakia": {8,9,10,11,12,1,2,3,4,5},
        "soccer_uefa": {9,10,11,12,1,2,3,4,5},
        "soccer_denmark": {7,8,9,10,11,12,2,3,4,5},
        "soccer_sweden": {4,5,6,7,8,9,10,11},        # Allsvenskan: summer league
        "soccer_norway": {4,5,6,7,8,9,10,11},
        "soccer_usa_mls": {3,4,5,6,7,8,9,10,11},
        "soccer_brazil": {4,5,6,7,8,9,10,11,12},
        "soccer_argentina": {2,3,4,5,6,7,8,9,10,11},
        "soccer_japan": {2,3,4,5,6,7,8,9,10,11,12},
        "basketball_nba": {10,11,12,1,2,3,4,5,6},
        "basketball_wnba": {5,6,7,8,9,10},
        "basketball_ncaab": {11,12,1,2,3,4},
        "basketball_euroleague": {10,11,12,1,2,3,4,5},
        "basketball_nbl": {10,11,12,1,2,3},
        "baseball_mlb_playoffs": {10},   # duplicate espn_path of baseball_mlb — only scan in October
        "baseball_mlb": {3,4,5,6,7,8,9,10},
        "basketball_nba_playoffs": {4,5,6},
        "icehockey_nhl_playoffs": {4,5,6},
        "icehockey_nhl": {10,11,12,1,2,3,4,5,6},
        "americanfootball_nfl": {9,10,11,12,1,2},
        "americanfootball_ncaaf": {8,9,10,11,12,1},
        "rugbyleague_nrl": {3,4,5,6,7,8,9,10},
        "aussierules": {3,4,5,6,7,8,9},
        # Year-round families (tennis, mma, boxing, cricket, darts, friendlies,
        # World Cup, Copa, esports, motorsports) are simply not listed → always scanned.
    }
    _now_month = datetime.now(timezone.utc).month

    def _in_season(sport_key: str) -> bool:
        for prefix, months in SEASON_MONTHS.items():
            if sport_key.startswith(prefix):
                return _now_month in months
        return True  # unknown/year-round families: always scan

    sport_filter = args.sport.lower()
    if sport_filter == "all":
        keys = [k for k in SPORTS_CONFIG if _in_season(k)]
        skipped = len(SPORTS_CONFIG) - len(keys)
        if skipped:
            print(f"[season] scanning {len(keys)} in-season sports ({skipped} off-season skipped)", file=sys.stderr)
    elif sport_filter in SPORT_GROUPS:
        prefix = SPORT_GROUPS[sport_filter]
        if isinstance(prefix, tuple):
            keys = [k for k in SPORTS_CONFIG if any(k.startswith(p) for p in prefix)]
        else:
            keys = [k for k in SPORTS_CONFIG if k.startswith(prefix) or k == prefix]
    else:
        keys = [k for k in SPORTS_CONFIG if sport_filter in k]

    all_bets = []

    # ── Main scan (TheRundown + model) ────────────────────────────────────────
    for sk in keys:
        bets = scan_sport(sk, args.min_ev, mon, sun)
        all_bets.extend(bets)

    # ── NCAAB via ActionNetwork (free, in-season Nov–Apr) ─────────────────────
    if sport_filter in ("all", "basketball", "ncaab", "college", "ncaa"):
        ncaab_bets = scan_ncaab(args.min_ev, mon, sun)
        all_bets.extend(ncaab_bets)

    # ── Exa scout for sports with no structured source ────────────────────────
    week_label = mon.strftime("%Y-%m-%d")
    exa_targets = []
    if sport_filter == "all":
        exa_targets = ["volleyball", "table tennis", "rugby union"]
    elif sport_filter in ("volleyball", "volley"):
        exa_targets = ["volleyball"]
    elif sport_filter in ("table tennis", "tabletennis", "tt"):
        exa_targets = ["table tennis"]
    elif sport_filter in ("rugby", "rugbyunion", "union"):
        exa_targets = ["rugby union"]

    # Exa scout disabled in picks output: web scrapes produce Polymarket leaks,
    # "partial data" rationales, and unrated confidence. Function kept for research.
    # for sl in exa_targets: all_bets.extend(exa_value_scout(sl, week_label))

    # Darts: PDC model-based picks (replaces Exa-only opinion scraping)
    if sport_filter in ("all", "darts"):
        all_bets.extend(scan_darts(week_label))

    # ── Sanity filter: drop picks with absurd EV or model/market divergence ────
    # Model probabilities are sometimes wildly overconfident (e.g. 85% on a 50/50
    # game), which produces nonsensical 70%+ EV picks. The market is almost always
    # right; when our model disagrees by >25%, we're wrong, not the bookies.
    # Anything with EV > 30% is dropped — real value bets are 5-15% edge.
    # Hard quality gate: drop garbage before sanity filter
    def _quality_gate(b):
        pick_text  = b.get("pick") or ""
        model_text = (b.get("model") or "").lower()
        # No odds + Exa-scouted = garbage
        if b.get("odds") is None and ("exa" in model_text or "scouted" in model_text):
            return False
        # Pick text that's a web snippet (>120 chars or contains URL leaks)
        if len(pick_text) > 120:
            return False
        BAD_KW = ("polymarket", "1xbet.com", "betway.com", "williamhill.com",
                  "skip to content", "skip navigation", "bet365.com")
        if any(k in pick_text.lower() for k in BAD_KW):
            return False
        # "partial data" in model notes — not enough data to be reliable
        if "partial data" in model_text:
            return False
        # "confidence unrated" model-only picks (no real confidence estimate)
        if b.get("odds") is None and b.get("our_prob") is None and b.get("confidence") is None:
            return False
        return True

    all_bets = [b for b in all_bets if _quality_gate(b)]
    all_bets = _sanity_filter(all_bets)

    # Deduplicate: for same (match, market, pick), prefer pick with odds over model-only
    _seen = {}
    for b in sorted(all_bets, key=lambda x: 0 if x.get("odds") is not None else 1):
        key = (b.get("match",""), b.get("market",""), b.get("pick",""))
        if key not in _seen:
            _seen[key] = b
    all_bets = list(_seen.values())


    # ── Odds-band filter (high-probability "events likely to happen") ─────────
    if args.band:
        try:
            lo, hi = [float(x) for x in args.band.split("-")]
            # Double Chance is a deliberately low-odds safety play (~1.10–1.25) —
            # exempt it from the band so the safer alternative still surfaces.
            all_bets = [b for b in all_bets
                        if b.get("odds") is None
                        or b.get("market") == "Double Chance"
                        or lo <= b["odds"] <= hi]
        except Exception:
            print(f"[warn] bad --band '{args.band}', ignoring")

    # ── Learning loop: recalibrate confidence + bench losing categories ───────
    # Picks evolve from settled outcomes (written by sabiai_analyze → learn.py).
    if not args.no_learn:
        _adj = learn.get_adjustments()
        if _adj:
            all_bets = [b for b in all_bets if learn.apply(b, _adj)]

    if args.refresh_clv:
        week_str = mon.strftime("%Y-W%V")
        log_picks(all_bets, week_str, refresh_only=True)
        return

    if args.format == "json":
        print(json.dumps(picks_json(all_bets), indent=2, default=str))
    elif args.format == "telegram":
        print(format_telegram(all_bets, mon, sun, _datapoints_left))
    elif args.format == "simple":
        print(plain_render.render(all_bets, mon, sun, title="Today's Picks"))
    else:
        format_plain(all_bets, mon, sun, _datapoints_left)

    # ── Log picks to results tracker ─────────────────────────────────────────
    week_str = mon.strftime("%Y-W%V")
    new_ids = log_picks(all_bets, week_str)
    logged = [b for b in all_bets if b.get("ev") is not None and not b.get("is_model_only")]
    if logged and args.format not in ("telegram", "json"):
        print(f"\n[Results] {len(logged)} picks saved to bets.db (week {week_str}, {len(new_ids)} new)")


if __name__ == "__main__":
    main()
