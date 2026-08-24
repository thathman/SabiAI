#!/usr/bin/env python3
"""live_bets.py — SabiAI live bet scanner (for fun, tracks records).

Two modes:
  flag     Runs during the daily scan. Looks at today's upcoming games and
           flags which ones will be worth watching live (high-variance,
           evenly matched, or strong "goals coming" signal). Saves to live_bets
           table with status='watch'. Run once per day.

  scan     Called every ~30 min during game windows. Checks ESPN live scoreboards,
           evaluates juiciness of in-progress games, sends a WhatsApp alert for
           anything that crosses the threshold, and marks it 'alerted'. Cron-safe:
           silent unless something is genuinely juicy.

  summary  JSON summary of today's watches + alerts.

Juiciness signals (plain-English logic, no jargon):
  - Game is tight (within 1 goal) past 60 min → still open
  - 0-0 at half-time but both sides are normally high-scoring → goals due
  - One team dominating but score flat → value in the dominant side next goal
  - A red card or penalty awarded → match dynamics shifted, live markets reprice
"""
import json, os, sqlite3, sys, urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, date, timedelta
from zoneinfo import ZoneInfo

# Read-only SportyBet odds for live corner/card/foul prop lines (optional —
# never let its absence or failure break the live scanner).
try:
    import sportybet_odds as SB
except Exception:
    SB = None

DB = "~.openclaw/workspace/data/bets.db"
LAGOS = ZoneInfo("Africa/Lagos")
WA_TARGET = "+234XXXXXXXXXX"

# ESPN sport scoreboards — free, no key. All sports with accessible live data.
SCOREBOARDS = [
    # ── Soccer / Football ──────────────────────────────────────────────────
    ("soccer/eng.1",               "EPL"),
    ("soccer/eng.2",               "ENG Championship"),
    ("soccer/esp.1",               "La Liga"),
    ("soccer/esp.2",               "La Liga 2"),
    ("soccer/ita.1",               "Serie A"),
    ("soccer/ger.1",               "Bundesliga"),
    ("soccer/ger.2",               "2. Bundesliga"),
    ("soccer/fra.1",               "Ligue 1"),
    ("soccer/ned.1",               "Eredivisie"),
    ("soccer/por.1",               "Primeira Liga"),
    ("soccer/sco.1",               "Scottish Prem"),
    ("soccer/tur.1",               "Super Lig"),
    ("soccer/bel.1",               "Belgian Pro League"),
    ("soccer/rus.1",               "Russian Premier"),
    ("soccer/den.1",               "Danish Superliga"),
    ("soccer/swe.1",               "Allsvenskan"),
    ("soccer/nor.1",               "Eliteserien"),
    ("soccer/sui.1",               "Swiss Super League"),
    ("soccer/cro.1",               "Croatian HNL"),
    ("soccer/pol.1",               "Ekstraklasa"),
    ("soccer/rou.1",               "Liga 1 Romania"),
    ("soccer/ukr.1",               "Ukrainian Premier"),
    ("soccer/bra.1",               "Brasileirao A"),
    ("soccer/bra.2",               "Brasileirao B"),
    ("soccer/arg.1",               "Argentine Primera"),
    ("soccer/mex.1",               "Liga MX"),
    ("soccer/col.1",               "Colombian Primera"),
    ("soccer/chi.1",               "Chilean Primera"),
    ("soccer/usa.1",               "MLS"),
    ("soccer/usa.2",               "USL Championship"),
    ("soccer/jpn.1",               "J1 League"),
    ("soccer/kor.1",               "K League 1"),
    ("soccer/chn.1",               "Chinese Super League"),
    ("soccer/aus.1",               "A-League"),
    ("soccer/sau.1",               "Saudi Pro League"),
    ("soccer/egy.1",               "Egyptian Premier"),
    ("soccer/rsa.1",               "South African PSL"),
    ("soccer/nig.1",               "NPFL Nigeria"),
    ("soccer/uae.1",               "UAE Pro League"),
    ("soccer/ind.1",               "Indian Super League"),
    ("soccer/uefa.champions",      "UCL"),
    ("soccer/uefa.europa",         "UEL"),
    ("soccer/uefa.europa.conf",    "UECL"),
    ("soccer/conmebol.libertadores","Copa Libertadores"),
    ("soccer/conmebol.sudamericana","Copa Sudamericana"),
    ("soccer/concacaf.champions",  "CONCACAF Champions"),
    ("soccer/fifa.worldcup",       "FIFA World Cup"),
    ("soccer/fifa.friendly",       "Intl Friendlies"),
    ("soccer/afr.nations",         "AFCON"),
    ("soccer/conmebol.america",    "Copa America"),
    ("soccer/uefa.euro",           "UEFA Euros"),
    ("soccer/fifa.worldq.uefa",    "WCQ Europe"),
    ("soccer/fifa.worldq.conmebol","WCQ S.America"),
    ("soccer/fifa.worldq.concacaf","WCQ CONCACAF"),
    ("soccer/fifa.worldq.caf",     "WCQ Africa"),
    ("soccer/fifa.worldq.afc",     "WCQ Asia"),
    ("soccer/uefa.nations",        "UEFA Nations League"),
    # ── Basketball ─────────────────────────────────────────────────────────
    ("basketball/nba",                     "NBA"),
    ("basketball/wnba",                    "WNBA"),
    ("basketball/mens-college-basketball", "NCAAB"),
    ("basketball/euroleague",              "EuroLeague"),
    ("basketball/nbl",                     "NBL Australia"),
    # ── Baseball ───────────────────────────────────────────────────────────
    ("baseball/mlb",   "MLB"),
    ("baseball/npb",   "NPB Japan"),
    ("baseball/kbo",   "KBO Korea"),
    # ── Ice Hockey ─────────────────────────────────────────────────────────
    ("hockey/nhl",               "NHL"),
    ("hockey/ahl",               "AHL"),
    ("hockey/khl",               "KHL"),
    ("hockey/shl",               "SHL Sweden"),
    ("hockey/liiga",             "Liiga Finland"),
    ("hockey/del",               "DEL Germany"),
    ("hockey/extraliga",         "Czech Extraliga"),
    ("hockey/world-men",         "IIHF Worlds"),
    # ── American Football ──────────────────────────────────────────────────
    ("football/nfl",             "NFL"),
    ("football/college-football","NCAAF"),
    ("football/cfl",             "CFL"),
    # ── Rugby ──────────────────────────────────────────────────────────────
    ("rugby-league/nrl",         "NRL"),
    ("rugby-league/super-league","Super League"),
    ("rugby/premiership",        "Rugby Premiership"),
    ("rugby/urc",                "URC"),
    ("rugby/top14",              "Top 14"),
    ("rugby/super-rugby",        "Super Rugby"),
    # ── Cricket ────────────────────────────────────────────────────────────
    ("cricket/ipl",              "IPL"),
    ("cricket/bbl",              "BBL Australia"),
    ("cricket/psl",              "PSL Pakistan"),
    # ── Aussie Rules ───────────────────────────────────────────────────────
    ("australian-football/afl",  "AFL"),
    ("australian-football/aflw", "AFLW"),
    # ── Tennis ─────────────────────────────────────────────────────────────
    ("tennis/atp",               "ATP"),
    ("tennis/wta",               "WTA"),
    # ── Golf ───────────────────────────────────────────────────────────────
    ("golf/pga",                 "PGA Tour"),
    ("golf/euro",                "DP World Tour"),
    # ── Motorsports ────────────────────────────────────────────────────────
    ("racing/f1",                "Formula 1"),
    ("racing/nascar",            "NASCAR"),
    ("racing/indycar",           "IndyCar"),
    ("racing/motogp",            "MotoGP"),
    # ── Esports ────────────────────────────────────────────────────────────
    ("esports/lol",              "LoL Esports"),
    ("esports/cs2",              "CS2"),
    ("esports/valorant",         "Valorant"),
    ("esports/dota2",            "Dota 2"),
]

ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports"

# Juiciness thresholds
MIN_JUICY_SCORE = 3     # need 3+ signals to alert
ALERT_COOLDOWN_MIN = 45  # don't re-alert same game within 45 min


def _conn():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    c.execute("""CREATE TABLE IF NOT EXISTS live_bets(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT, sport TEXT, league TEXT, match TEXT,
        kickoff TEXT, status TEXT DEFAULT 'watch',
        juicy_score INTEGER DEFAULT 0, signals TEXT,
        alerted_at TEXT, outcome TEXT, notes TEXT,
        created_at TEXT DEFAULT (datetime('now')))""")
    # Track record columns
    for col, defn in [("result", "TEXT"), ("was_juicy", "INTEGER DEFAULT 0")]:
        try:
            c.execute(f"ALTER TABLE live_bets ADD COLUMN {col} {defn}")
        except Exception:
            pass
    return c


def _get(path):
    req = urllib.request.Request(
        f"{ESPN_BASE}/{path}",
        headers={"User-Agent": "Mozilla/5.0 (openclaw live-scanner)"})
    try:
        with urllib.request.urlopen(req, timeout=6) as r:
            return json.loads(r.read())
    except Exception:
        return {}


def _notify(msg):
    try:
        import subprocess
        subprocess.run(
            [os.path.expanduser("~/.npm-global/bin/openclaw"), "message", "send", "--channel", "whatsapp",
             "--target", WA_TARGET, "--message", msg],
            capture_output=True, text=True, timeout=15)
    except Exception as e:
        print(f"notify err: {e}", file=sys.stderr)


def _score_int(val):
    try:
        return int(float(val))
    except Exception:
        return None


def _competitor_label(comp):
    """Best-effort label for a scoreboard competitor."""
    team = comp.get("team") or {}
    for key in ("abbreviation", "shortDisplayName", "displayName", "name"):
        val = team.get(key)
        if val:
            return str(val)
    for key in ("displayName", "name", "abbreviation"):
        val = comp.get(key)
        if val:
            return str(val)
    return "?"


def _home_away_names(comp):
    """Full home/away display names from an ESPN competition."""
    h = a = None
    for x in comp.get("competitors", []):
        nm = (x.get("team") or {}).get("displayName") or x.get("displayName") or ""
        if x.get("homeAway") == "home":
            h = nm
        elif x.get("homeAway") == "away":
            a = nm
    return h, a


def _live_prop_text(home, away, sb_events):
    """Available SportyBet live prop lines (corners/cards/fouls) for this match,
    as a short alert block. Returns '' if no event/props or anything fails.
    Read-only and fully guarded — must never break the scan."""
    if not SB or not sb_events or not home or not away:
        return ""
    try:
        ev = SB.find_event(home, away, sb_events, min_sim=0.62)
        if not ev:
            return ""
        props = SB.prop_odds(ev["eventId"], timeout=8)
        if not props:
            return ""
        label = {"corners": "Corners", "cards": "Cards", "fouls": "Fouls"}
        rows = []
        for key in ("corners", "cards", "fouls"):
            lines = props.get(key)
            if not lines:
                continue
            # show the middle line (most balanced) per market
            mid = lines[len(lines) // 2]
            rows.append(f"  {label[key]} O/U {mid['line']:g}: Over {mid['over']:.2f} / Under {mid['under']:.2f}")
        if not rows:
            return ""
        return "📐 *Live props on SportyBet*\n" + "\n".join(rows)
    except Exception:
        return ""


def _juiciness(event, league):
    """Return (score, signals_list) for a live event."""
    c = event["competitions"][0]
    status = c["status"]["type"]["name"]
    if status not in ("STATUS_IN_PROGRESS", "STATUS_HALFTIME", "STATUS_SECOND_HALF",
                      "STATUS_END_OF_PERIOD"):
        return 0, []

    comps = c["competitors"]
    scores = []
    names = []
    for x in comps:
        s = _score_int(x.get("score", {}).get("value") if isinstance(x.get("score"), dict) else x.get("score"))
        scores.append(s if s is not None else 0)
        names.append(_competitor_label(x))

    clock = c["status"].get("displayClock", "")
    elapsed = c["status"].get("clock", 0)
    try:
        elapsed_min = int(elapsed / 60) if elapsed > 100 else int(elapsed)
    except Exception:
        elapsed_min = 0

    signals = []
    score_diff = abs(scores[0] - scores[1]) if len(scores) == 2 else 0
    total_goals = sum(scores) if scores else 0

    # Signal 1: tight game, late
    if score_diff <= 1 and elapsed_min >= 55:
        signals.append(f"tight ({scores[0]}-{scores[1]}) at {elapsed_min} min — still live")

    # Signal 2: goal-less but deep into game (goals expected)
    if total_goals == 0 and elapsed_min >= 40 and "soccer" in league.lower():
        signals.append("0-0 deep in game — both teams to score still live")

    # Signal 3: exactly 0-0 at half-time for soccer
    if total_goals == 0 and status == "STATUS_HALFTIME" and "soccer" in league.lower():
        signals.append("0-0 at HT — Over 0.5 second half is live value")

    # Signal 4: one team down but in reach
    if score_diff == 1 and elapsed_min < 75 and "soccer" in league.lower():
        behind = names[1] if scores[0] > scores[1] else names[0]
        signals.append(f"{behind} one down with time to fight back")

    # Signal 5: comeback scenario in basketball (within 5 pts after 3 qtrs)
    if "basketball" in league.lower() or "nba" in league.lower():
        if score_diff <= 5 and elapsed_min >= 35:
            signals.append(f"within {score_diff} pts, anyone's game")
        elif score_diff <= 10 and elapsed_min >= 45:
            signals.append(f"10pt game with time — live spread worth watching")

    # Signal 6: high-scoring game still open (BTTS / total goals market)
    if total_goals >= 3 and score_diff <= 1 and "soccer" in league.lower():
        signals.append(f"goal fest ({total_goals} goals), still tight — more coming")

    return len(signals), signals


def cmd_flag():
    """Pre-game: flag today's upcoming matches worth watching live."""
    today = date.today().isoformat()
    c = _conn()
    existing = {r["match"] for r in c.execute(
        "SELECT match FROM live_bets WHERE date=?", (today,))}

    flagged = []
    now_utc = datetime.now(timezone.utc)

    # Fetch all scoreboards concurrently
    def _fetch_board(item):
        sp_path, league = item
        return sp_path, league, _get(f"{sp_path}/scoreboard")

    boards = {}
    with ThreadPoolExecutor(max_workers=20) as pool:
        futs = {pool.submit(_fetch_board, item): item for item in SCOREBOARDS}
        for fut in as_completed(futs, timeout=30):
            try:
                sp_path, league, d = fut.result()
                boards[(sp_path, league)] = d
            except Exception:
                pass

    for (sp_path, league), d in boards.items():
        for ev in d.get("events", []):
            if not ev.get("competitions"):
                continue
            comp = ev["competitions"][0]
            status = comp.get("status", {}).get("type", {}).get("name", "")
            # Only upcoming (within next 8 hours)
            if status not in ("STATUS_SCHEDULED",):
                continue
            ev_dt_str = ev.get("date", "")
            try:
                ev_dt = datetime.fromisoformat(ev_dt_str.replace("Z", "+00:00"))
                hours_away = (ev_dt - now_utc).total_seconds() / 3600
                if hours_away < 0 or hours_away > 8:
                    continue
            except Exception:
                continue
            name = ev.get("name", "")
            if name in existing:
                continue

            # Compute "worth watching" score
            comps = comp["competitors"]
            # Check if evenly matched (similar seeds/ranks)
            rank_diff = None
            for x in comps:
                rank = x.get("curatedRank", {}).get("current")
                if rank:
                    rank_diff = rank

            watch_score = 0
            signals = []

            # Both teams in top 10? Likely tight
            ranks = [x.get("curatedRank", {}).get("current", 999) for x in comps]
            if all(r <= 10 for r in ranks):
                watch_score += 2; signals.append("both top-10 — competitive")
            elif all(r <= 20 for r in ranks):
                watch_score += 1; signals.append("evenly ranked — could go either way")

            # League-level interest
            if league in ("EPL", "La Liga", "Bundesliga", "Serie A", "NBA"):
                watch_score += 1; signals.append(f"top league ({league})")

            # Kickoff in prime time (Lagos evening)
            ev_lag = ev_dt.astimezone(LAGOS)
            if 18 <= ev_lag.hour <= 22:
                watch_score += 1; signals.append("prime time — you'll be up")

            if watch_score >= 2:
                c.execute("""INSERT OR IGNORE INTO live_bets
                  (date, sport, league, match, kickoff, status, juicy_score, signals)
                  VALUES (?,?,?,?,?,?,?,?)""",
                  (today, sp_path.split("/")[0], league, name,
                   ev_dt.isoformat(), "watch", watch_score, json.dumps(signals)))
                flagged.append({"match": name, "league": league,
                                "kickoff_lagos": ev_lag.strftime("%H:%M"),
                                "signals": signals})

    c.commit(); c.close()
    if not flagged:
        print("No watch-worthy games flagged today.", file=sys.stderr)
        return
    print(f"Flagged {len(flagged)} games to watch live:")
    for f in flagged:
        print(f"  [{f['league']}] {f['match']} @ {f['kickoff_lagos']} Lagos — {', '.join(f['signals'])}")


def cmd_scan(dry_run=False):
    """Scan live scoreboards, alert on juicy situations."""
    now_utc = datetime.now(timezone.utc)
    now_iso = now_utc.isoformat()
    c = _conn()
    alerted = []

    # Fetch all scoreboards concurrently (up to 20 workers, 6s timeout each)
    def _fetch_board(item):
        sp_path, league = item
        return sp_path, league, _get(f"{sp_path}/scoreboard")

    boards = {}
    with ThreadPoolExecutor(max_workers=20) as pool:
        futs = {pool.submit(_fetch_board, item): item for item in SCOREBOARDS}
        for fut in as_completed(futs, timeout=30):
            try:
                sp_path, league, d = fut.result()
                boards[(sp_path, league)] = d
            except Exception:
                pass

    # One SportyBet live-events pull per scan (shared across all alerts; guarded).
    sb_events = []
    if SB:
        try:
            sb_events = SB.live_events(timeout=8)
        except Exception:
            sb_events = []

    for (sp_path, league), d in boards.items():
        for ev in d.get("events", []):
            if not ev.get("competitions"):
                continue
            comp = ev["competitions"][0]
            status = comp.get("status", {}).get("type", {}).get("name", "")
            if status not in ("STATUS_IN_PROGRESS", "STATUS_HALFTIME",
                              "STATUS_SECOND_HALF", "STATUS_END_OF_PERIOD"):
                continue
            name = ev.get("name", "")
            score_text = " vs ".join(
                f"{_competitor_label(x)} {x.get('score',{}).get('value','?') if isinstance(x.get('score'),dict) else x.get('score','?')}"
                for x in comp["competitors"])
            clock = comp["status"].get("displayClock", "?")

            juicy, signals = _juiciness(ev, sp_path)
            if juicy < MIN_JUICY_SCORE:
                continue

            # Cooldown: don't re-alert same game within ALERT_COOLDOWN_MIN
            last = c.execute(
                "SELECT alerted_at FROM live_bets WHERE match=? AND alerted_at IS NOT NULL ORDER BY alerted_at DESC LIMIT 1",
                (name,)).fetchone()
            if last and last["alerted_at"]:
                try:
                    last_dt = datetime.fromisoformat(last["alerted_at"])
                    mins_since = (now_utc - last_dt).total_seconds() / 60
                    if mins_since < ALERT_COOLDOWN_MIN:
                        continue
                except Exception:
                    pass

            # Upsert record
            c.execute("""INSERT INTO live_bets
              (date, sport, league, match, status, juicy_score, signals, alerted_at)
              VALUES (?,?,?,?,?,?,?,?)
              ON CONFLICT DO NOTHING""",
              (date.today().isoformat(), sp_path.split("/")[0], league, name,
               "alerted", juicy, json.dumps(signals), now_iso))
            c.execute("UPDATE live_bets SET status='alerted', juicy_score=?, signals=?, alerted_at=? WHERE match=?",
                      (juicy, json.dumps(signals), now_iso, name))

            # Format message
            sig_text = " · ".join(signals[:3])
            msg = (f"⚡ *Live Bet Watch — {league}*\n"
                   f"*{name}* | {score_text} | {clock}\n"
                   f"{sig_text}\n"
                   f"_Check the live markets — this looks juicy. No money on it, just watching the action._")
            # Attach SportyBet live prop lines for soccer (guarded — never blocks).
            if sp_path.startswith("soccer/"):
                ph, pa = _home_away_names(comp)
                prop_text = _live_prop_text(ph, pa, sb_events)
                if prop_text:
                    msg += "\n\n" + prop_text
            if not dry_run:
                _notify(msg)
            alerted.append({"match": name, "score": score_text, "signals": signals})

    c.commit(); c.close()
    if alerted:
        print(f"Alerted on {len(alerted)} live games:")
        for a in alerted:
            print(f"  {a['match']} | {a['score']} | {', '.join(a['signals'][:2])}")
    # else: silent pass


def cmd_summary():
    c = _conn()
    today = date.today().isoformat()
    watches = [dict(r) for r in c.execute(
        "SELECT * FROM live_bets WHERE date=? ORDER BY created_at DESC", (today,))]
    total = c.execute("SELECT COUNT(*) n FROM live_bets").fetchone()["n"]
    alerted_total = c.execute("SELECT COUNT(*) n FROM live_bets WHERE status='alerted'").fetchone()["n"]
    c.close()
    print(json.dumps({
        "today": {"watch": len([w for w in watches if w["status"]=="watch"]),
                  "alerted": len([w for w in watches if w["status"]=="alerted"])},
        "all_time": {"total": total, "alerted": alerted_total},
        "today_games": watches,
    }, indent=2, default=str))


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "scan"
    dry = "--dry-run" in sys.argv
    if cmd == "flag": cmd_flag()
    elif cmd == "scan": cmd_scan(dry)
    elif cmd == "summary": cmd_summary()
    else: print("usage: live_bets.py flag|scan|summary [--dry-run]")


if __name__ == "__main__":
    main()
