#!/usr/bin/env python3
"""
weekly_long_shot.py — SabiAI weekly long-shot accumulator builder.

Runs once a week. Builds a 3–8 leg accumulator targeting 1000+ combined odds from
the daily scan's picks. Stake: ₦100 (training-mode "monopoly naira").

Reads the daily scan's unsettled picks straight from the `bets` table (the daily cron
already populated it with learned-adjusted confidence) — no redundant multi-minute scan.
Greedy build: take the longest-odds, most independent legs (one per match) until combined
odds clear the target.

Logs to weekly_long_shot + accumulator_legs. Notifies Hendrix with the slip request,
or stays silent if no qualifying combo exists.
"""
import argparse, json, sqlite3, subprocess, sys, os
from datetime import datetime, timezone, timedelta

DB = "/home/hendrix/.openclaw/workspace/data/bets.db"
SCRIPTS = "/home/hendrix/.openclaw/workspace/scripts"
WEEKLY_TARGET_ODDS = 1000.0
LONGSHOT_BOOKMAKER = "bet9ja"


def _config_stakes():
    """Stake range comes from config.weekly_long_shot (single source of truth).
    Hendrix's rule: ₦100 minimum, ₦1,000 maximum per long-shot slip."""
    try:
        c = sqlite3.connect(DB)
        row = c.execute("SELECT value FROM config WHERE key='weekly_long_shot'").fetchone()
        c.close()
        if row:
            cfg = json.loads(row[0])
            return float(cfg.get("stake", 100)), float(cfg.get("stake_max", 1000))
    except Exception:
        pass
    return 100.0, 1000.0


WEEKLY_STAKE, WEEKLY_STAKE_MAX = _config_stakes()
# Near-sure legs: each individual leg has 78%+ confidence (implied odds 1.10–1.30).
# Stacking 25–30 near-certain legs makes the combined slip itself a long shot (~0.1% chance).
# That's the point: each leg is almost guaranteed, but hitting ALL of them is the long shot.
# Math: 1.25^30 ≈ 807× / 1.28^28 ≈ 1080× — need ~28 legs at 1.28 avg to clear 1000×.
MIN_LEGS, MAX_LEGS = 20, 35
MIN_LEG_ODDS = 1.01   # floor: include extreme favourites (Germany 1.02, Spain 1.08, etc.)
MAX_LEG_ODDS = 1.35   # cap for "near-certain" legs; higher-odds legs added as supplement
MIN_CONFIDENCE = 50   # 50%+ for supplement legs; near-certain legs require higher via build logic
# Window: Monday 08:00 Lagos → following Monday 07:59 Lagos
# When run manually, use the current calendar week's Monday→Monday span.


def _week_window():
    """Return (start_date_str, end_date_str) covering Mon 07:00 → next Mon 06:59 Lagos.
    Cutoff is 7am Monday. Games starting after that cutoff are the NEXT week's slip."""
    from zoneinfo import ZoneInfo
    LAGOS = ZoneInfo("Africa/Lagos")
    now = datetime.now(LAGOS)
    # If it's Monday before 7am, we're still in last week's window
    days_since_monday = now.weekday()
    if days_since_monday == 0 and now.hour < 7:
        days_since_monday = 7  # treat as last Monday → this Sunday
    monday = (now - timedelta(days=days_since_monday)).replace(hour=7, minute=0, second=0, microsecond=0)
    next_monday = monday + timedelta(days=7)
    return monday.strftime("%Y-%m-%d"), next_monday.strftime("%Y-%m-%d")


def _is_longshot_bookmaker(value: str) -> bool:
    # Accept Bet9ja picks AND model-only picks — user places on Bet9ja manually
    raw = (value or "").strip().lower()
    return raw.startswith(LONGSHOT_BOOKMAKER) or raw in ("model", "", "bet9ja", "sportybet")


def _sofa_week_sweep():
    """
    Sweep SofaScore for ALL sports across the full week (Mon→Sun).
    Uses market odds from SofaScore (primary) and Elo model for football fallback.
    Any event where the favourite's odds sit in [MIN_LEG_ODDS, MAX_LEG_ODDS] qualifies.
    Returns count of new picks inserted.
    """
    sys.path.insert(0, SCRIPTS)
    try:
        import sofascore as SOFA
        SOFA._load_key()
        SOFA._init_cache()
    except ImportError:
        return 0

    # Elo disabled in week sweep — too slow (276 ClubElo HTTP calls for 138 games).
    # ESPN sweep covers World Cup + friendly odds. Elo used only in live scan cron.
    _elo_probs = None

    start_str, end_str = _week_window()
    from datetime import datetime as _dt, timezone as _tz, timedelta as _td
    start = _dt.strptime(start_str, "%Y-%m-%d").replace(tzinfo=_tz.utc)
    end   = _dt.strptime(end_str,   "%Y-%m-%d").replace(tzinfo=_tz.utc)

    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    inserted = 0

    # Every sport SofaScore covers — market odds handle all of them
    ALL_SPORTS = [
        ("football",     "⚽"),
        ("basketball",   "🏀"),
        ("baseball",     "⚾"),
        ("tennis",       "🎾"),
        ("volleyball",   "🏐"),
        ("rugby",        "🏉"),
        ("handball",     "🤾"),
        ("ice-hockey",   "🏒"),
        ("table-tennis", "🏓"),
        ("cricket",      "🏏"),
        ("futsal",       "⚽"),
        ("mma",          "🥊"),
        ("boxing",       "🥊"),
        ("darts",        "🎯"),
        ("snooker",      "🎱"),
    ]

    day = start
    while day < end:
        date_str = day.strftime("%Y-%m-%d")
        for sport_slug, sport_emoji in ALL_SPORTS:
            try:
                events = SOFA.events_today(sport_slug, date_str)
            except Exception:
                continue

            for ev in events:
                home = ev.get("home", "")
                away = ev.get("away", "")
                if not home or not away:
                    continue
                kickoff_ts = ev.get("kickoff_ts")
                if kickoff_ts:
                    kickoff = _dt.fromtimestamp(kickoff_ts, tz=_tz.utc).strftime("%Y-%m-%d %H:%M")
                else:
                    kickoff = ev.get("start_time") or date_str
                # Skip finished/cancelled
                if ev.get("status") in ("finished", "canceled", "postponed"):
                    continue
                # Skip if kickoff already past
                try:
                    kt = _dt.fromisoformat(kickoff).replace(tzinfo=_tz.utc)
                    if kt < _dt.now(_tz.utc):
                        continue
                except Exception:
                    pass
                # Skip if already in DB
                already = c.execute(
                    "SELECT id FROM bets WHERE match LIKE ? AND kickoff LIKE ?",
                    (f"%{home[:10]}%", f"{kickoff[:10]}%")
                ).fetchone()
                if already:
                    continue

                # --- Confidence model ---
                # SofaScore odds only available for football (other sports return empty)
                home_odds = away_odds = draw_odds = None
                ev_id = ev.get("id")
                if ev_id and sport_slug in ("football", "futsal"):
                    try:
                        mkt = SOFA.event_odds(ev_id)
                        if mkt:
                            home_odds = mkt.get("home")
                            away_odds = mkt.get("away")
                            draw_odds = mkt.get("draw")
                    except Exception:
                        pass

                # For non-football: no odds source — skip (ESPN sweep handles those)
                if sport_slug not in ("football", "futsal") and not home_odds:
                    continue

                # Fallback for football only: Elo model when no odds available
                if home_odds is None and sport_slug in ("football", "futsal") and _elo_probs:
                    try:
                        elo = _elo_probs(home, away)
                    except Exception:
                        elo = None
                    if elo:
                        home_prob = elo.get("home", 0)
                        away_prob = elo.get("away", 0)
                        if home_prob > 0:
                            home_odds = round(1.0 / home_prob, 2)
                        if away_prob > 0:
                            away_odds = round(1.0 / away_prob, 2)
                        draw_prob = elo.get("draw", 0)
                        if draw_prob > 0:
                            draw_odds = round(1.0 / draw_prob, 2)

                if not home_odds or not away_odds:
                    continue  # no odds available, skip

                # Pick the favourite (lowest odds = highest implied probability)
                candidates = [("home", home, home_odds), ("away", away, away_odds)]
                candidates.sort(key=lambda x: x[2])  # lowest odds first
                _, pick_team, fav_odds = candidates[0]

                if not (MIN_LEG_ODDS <= fav_odds <= MAX_LEG_ODDS):
                    continue

                implied_prob = round(1.0 / fav_odds * 100, 1)
                if implied_prob < MIN_CONFIDENCE:
                    continue

                market = "1X2" if draw_odds else "H2H"
                league = ev.get("tournament") or ev.get("league") or f"{sport_emoji} {sport_slug.title()}"
                match_str = f"{home} vs {away}"
                week_str = _dt.strptime(date_str, "%Y-%m-%d").strftime("%Y-W%V")
                source = "SofaScore odds" if ev_id else "Elo"

                c.execute("""INSERT OR IGNORE INTO bets
                    (bet_id, scan_date, week, sport, match, kickoff, market, pick,
                     odds, bookmaker, ev, our_prob, kelly, model, outcome, confidence_pct,
                     plain_rationale, bet_type, selected)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,NULL,?,?,?,0)""", (
                    f"ls_{hash(match_str+date_str) & 0xFFFFFF:06x}",
                    date_str, week_str, f"{sport_emoji} {league}",
                    match_str, kickoff[:16], market, pick_team,
                    fav_odds, "model",
                    round((1.0 / fav_odds * fav_odds - 1) * 100, 1),  # EV = 0 at fair odds
                    implied_prob,
                    0.0, source, implied_prob,
                    f"{source}: {pick_team} is favourite at {fav_odds:.2f} ({implied_prob}% implied).",
                    "kelly"
                ))
                if c.execute("SELECT changes()").fetchone()[0]:
                    inserted += 1

        day += _td(days=1)

    c.commit()
    c.close()
    return inserted


def _espn_week_sweep():
    """
    Sweep ESPN public scoreboard API for all sports this week.
    Inserts picks into bets.db where the favourite's odds are in [MIN_LEG_ODDS, MAX_LEG_ODDS]
    OR where this is a FIFA World Cup / major tournament game (include any favourite).
    Returns count of new picks inserted.
    """
    sys.path.insert(0, SCRIPTS)
    try:
        import espn_odds as ESPN
    except ImportError:
        return 0

    from datetime import datetime as _dt, timezone as _tz
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    inserted = 0

    start_str, end_str = _week_window()
    qualifying = ESPN.week_qualifying(start_str, 1.02, 2.50, days=7)

    for ev in qualifying:
        home, away = ev["home"], ev["away"]
        match_str = f"{home} vs {away}"
        kickoff = ev.get("kickoff", start_str)
        date_str = kickoff[:10]
        week_str = _dt.strptime(date_str[:10], "%Y-%m-%d").strftime("%Y-W%V") if len(date_str) >= 10 else ""
        odds = ev["odds"]
        impl_prob = ev["implied_prob"]
        pick = ev["pick"]
        sport = ev["sport"]
        tournament = ev.get("tournament", sport)

        # Any game with 50%+ implied probability qualifies (near-certain OR supplement)
        if impl_prob < 50:
            continue

        # Skip if already in DB
        already = c.execute(
            "SELECT id FROM bets WHERE match LIKE ? AND kickoff LIKE ?",
            (f"%{home[:10]}%", f"{kickoff[:10]}%")
        ).fetchone()
        if already:
            continue

        c.execute("""INSERT OR IGNORE INTO bets
            (bet_id, scan_date, week, sport, match, kickoff, market, pick,
             odds, bookmaker, ev, our_prob, kelly, model, outcome, confidence_pct,
             plain_rationale, bet_type, selected)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,NULL,?,?,?,0)""", (
            f"ls_{hash(match_str+date_str) & 0xFFFFFF:06x}",
            date_str, week_str, sport,
            match_str, kickoff[:16], "1X2", pick,
            odds, "model",
            round((impl_prob / 100.0 * odds - 1) * 100, 1),
            impl_prob, 0.0, "ESPN/DraftKings", impl_prob,
            f"DraftKings: {pick} is favourite at {odds:.2f} ({impl_prob}% implied).",
            "kelly"
        ))
        if c.execute("SELECT changes()").fetchone()[0]:
            inserted += 1

    c.commit()
    c.close()
    return inserted


def fetch_picks():
    """Pull unsettled picks from the current Mon→Mon window."""
    start, end = _week_window()
    try:
        c = sqlite3.connect(DB)
        c.row_factory = sqlite3.Row
        rows = c.execute("""SELECT sport, match, kickoff, market, pick, odds, confidence_pct, plain_rationale, bookmaker
            FROM bets WHERE outcome IS NULL
            AND scan_date >= ? AND scan_date < ?
            AND odds IS NOT NULL
            ORDER BY odds DESC""", (start, end)).fetchall()
        c.close()
    except Exception as e:
        return None, f"db error: {e}"
    # Also include picks whose kickoff falls inside the window even if scan was earlier
    if not rows:
        # Fall back to last 7 days
        since = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
        try:
            c = sqlite3.connect(DB)
            c.row_factory = sqlite3.Row
            rows = c.execute("""SELECT sport, match, kickoff, market, pick, odds, confidence_pct, plain_rationale, bookmaker
                FROM bets WHERE outcome IS NULL AND scan_date >= ? AND odds IS NOT NULL
                ORDER BY odds DESC""", (since,)).fetchall()
            c.close()
        except Exception as e:
            return None, f"db error (fallback): {e}"
    data = [{"sport": r["sport"], "match": r["match"], "kickoff": r["kickoff"] or "",
             "market": r["market"], "pick": r["pick"], "plain_pick": r["pick"],
             "odds": float(r["odds"]),
             "confidence_pct": r["confidence_pct"], "learn_status": "active",
             "bookmaker": r["bookmaker"] or ""}
            for r in rows]
    return data, None


def build_long_shot(picks):
    """
    Greedy: one leg per match, sorted by odds (shorter first = more certain legs anchor the slip).
    When near-certain picks (1.10-1.35) alone can't reach 20 legs or 1000×, automatically
    includes World Cup / major-tournament picks at higher odds to fill out the slip.
    """
    near_certain = [p for p in picks
                    if isinstance(p.get("odds"), (int, float))
                    and MIN_LEG_ODDS <= p["odds"] <= MAX_LEG_ODDS
                    and (p.get("confidence_pct") or 0) >= 50
                    and p.get("learn_status") != "avoid"
                    and _is_longshot_bookmaker(p.get("bookmaker"))]

    # Supplement: higher-odds picks (tournament games, 1.35-2.50)
    supplement = [p for p in picks
                  if isinstance(p.get("odds"), (int, float))
                  and MAX_LEG_ODDS < p["odds"] <= 2.50
                  and (p.get("confidence_pct") or 0) >= 50
                  and p.get("learn_status") != "avoid"
                  and _is_longshot_bookmaker(p.get("bookmaker"))]

    # Sort: shorter odds first (more certain legs anchor the slip)
    near_certain.sort(key=lambda p: p["odds"])
    supplement.sort(key=lambda p: p["odds"])

    pool = near_certain + supplement
    legs, seen_matches, combined = [], set(), 1.0
    for p in pool:
        if p["match"] in seen_matches:
            continue
        legs.append(p)
        seen_matches.add(p["match"])
        combined *= p["odds"]
        if len(legs) >= MIN_LEGS and combined >= WEEKLY_TARGET_ODDS:
            break
        if len(legs) >= MAX_LEGS:
            break
    return legs, combined


def log_long_shot(legs, combined_odds):
    c = sqlite3.connect(DB)
    now = datetime.now(timezone.utc).isoformat()
    week_of = datetime.now(timezone.utc).strftime("%Y-W%V")  # ISO week, matches bets.week
    cur = c.execute("""INSERT INTO weekly_long_shot
      (week_of, slip_code, created_at, bookmaker, legs, combined_odds, stake, status)
      VALUES (?,?,?,?,?,?,?,?)""",
      (week_of, None, now, "Bet9ja", len(legs), combined_odds, WEEKLY_STAKE, "pending"))
    ls_id = cur.lastrowid
    # also drop the legs into accumulator_legs for the dashboard, tagged by note
    acc = c.execute("""INSERT INTO accumulators
      (slip_code, created_at, bookmaker, legs, combined_odds, stake, status, notes)
      VALUES (?,?,?,?,?,?,?,?)""",
      (None, now, "Bet9ja", len(legs), combined_odds, WEEKLY_STAKE, "pending",
       f"weekly long shot #{ls_id}")).lastrowid
    for L in legs:
        c.execute("""INSERT INTO accumulator_legs
          (acc_id, sport, match, market, pick, odds, confidence_pct, outcome)
          VALUES (?,?,?,?,?,?,?,?)""",
          (acc, L.get("sport"), L.get("match"), L.get("market"), L.get("pick"),
           L.get("odds"), L.get("confidence_pct"), None))
    c.commit()
    c.close()
    return ls_id


def monitor_current():
    """
    Check progress of the active weekly long-shot slip.
    Returns a dict with:
      - slip_id, combined_odds, stake, status
      - legs: list of {match, pick, odds, status, score, won/lost/pending}
      - legs_won, legs_lost, legs_pending
      - eliminated: True if any leg lost (slip is dead)
      - running_odds: current multiplier of surviving legs
      - potential_payout: stake * running_odds
    """
    sys.path.insert(0, SCRIPTS)
    try:
        import sofascore as SOFA
        SOFA.init()
        sofa_ok = True
    except Exception:
        sofa_ok = False

    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    # Get latest active/pending long-shot
    ls = c.execute(
        "SELECT * FROM weekly_long_shot WHERE status IN ('pending','active') ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if not ls:
        c.close()
        return None

    ls = dict(ls)
    acc = c.execute(
        "SELECT * FROM accumulator_legs WHERE acc_id = (SELECT id FROM accumulators WHERE notes LIKE ? ORDER BY id DESC LIMIT 1)",
        (f"weekly long shot #{ls['id']}%",)
    ).fetchall()
    c.close()

    legs_out = []
    legs_won = legs_lost = legs_pending = 0
    running_odds = 1.0
    eliminated = False

    from datetime import datetime as _dt, timezone as _tz
    now_utc = _dt.now(_tz.utc)

    for leg in acc:
        match = leg["match"] or ""
        pick = leg["pick"] or ""
        odds = float(leg["odds"] or 1.0)
        kickoff = ""

        # Guess kickoff from bets table
        bet_row = None
        try:
            tmp = sqlite3.connect(DB)
            tmp.row_factory = sqlite3.Row
            bet_row = tmp.execute(
                "SELECT kickoff FROM bets WHERE match=? AND pick=? ORDER BY id DESC LIMIT 1",
                (match, pick)
            ).fetchone()
            tmp.close()
        except Exception:
            pass
        if bet_row and bet_row["kickoff"]:
            kickoff = bet_row["kickoff"]

        # Parse home/away
        import re as _re
        mv = _re.match(r"(.+?)\s+(?:vs\.?|v\.?)\s+(.+)", match, _re.IGNORECASE)
        home = mv.group(1).strip() if mv else match
        away = mv.group(2).strip() if mv else ""

        # Get live/final score from SofaScore
        score_str = ""
        leg_status = "pending"
        won = None

        if sofa_ok and home and away:
            date_str = kickoff[:10] if kickoff else now_utc.strftime("%Y-%m-%d")
            ev = SOFA.get_score(home, away, "football", date_str)
            if ev and ev.get("status") == "finished":
                hs = ev.get("home_score", 0) or 0
                aws = ev.get("away_score", 0) or 0
                score_str = f"{hs}-{aws}"
                leg_status = "finished"
                # Determine outcome for this leg
                pick_n = pick.strip().lower()
                home_n = home.strip().lower()
                away_n = away.strip().lower()
                if "draw" in pick_n or pick_n == "x":
                    won = (hs == aws)
                elif pick_n in (home_n, "home") or home_n in pick_n:
                    won = (hs > aws)
                elif pick_n in (away_n, "away") or away_n in pick_n:
                    won = (aws > hs)
                else:
                    won = None
            elif ev and ev.get("status") == "inprogress":
                hs = ev.get("home_score", 0) or 0
                aws = ev.get("away_score", 0) or 0
                score_str = f"{hs}-{aws} (LIVE)"
                leg_status = "inprogress"

        if leg_status == "finished" and won is True:
            legs_won += 1
            running_odds *= odds
        elif leg_status == "finished" and won is False:
            legs_lost += 1
            eliminated = True
        else:
            legs_pending += 1
            if leg_status != "inprogress":
                running_odds *= odds  # assume pending legs will win for potential calc

        legs_out.append({
            "match": match, "pick": pick, "odds": odds,
            "status": leg_status, "score": score_str, "won": won,
        })

    potential_payout = ls["stake"] * running_odds if not eliminated else 0
    return {
        "slip_id": ls["id"],
        "combined_odds": ls["combined_odds"],
        "stake": ls["stake"],
        "status": "eliminated" if eliminated else ("won" if legs_pending == 0 and legs_lost == 0 else "active"),
        "legs": legs_out,
        "legs_total": len(legs_out),
        "legs_won": legs_won,
        "legs_lost": legs_lost,
        "legs_pending": legs_pending,
        "eliminated": eliminated,
        "running_odds": round(running_odds, 2),
        "potential_payout": round(potential_payout, 2),
    }


def notify_telegram(text):
    try:
        subprocess.run([os.path.expanduser("~/.npm-global/bin/openclaw"), "message", "send", "--channel", "telegram",
                        "--target", "-1003892428943", "--thread-id", "188", "--message", text],
                       capture_output=True, text=True, timeout=15)
    except Exception as e:
        print(f"notify error: {e}", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    # Sweep SofaScore for ALL soccer fixtures this week before reading picks
    new_from_sofa = _sofa_week_sweep()
    if new_from_sofa:
        print(f"[sofa sweep] Added {new_from_sofa} new model picks from SofaScore fixtures")

    # Sweep ESPN public scoreboard (World Cup, MLB, NBA, NHL, tennis, etc.)
    new_from_espn = _espn_week_sweep()
    if new_from_espn:
        print(f"[espn sweep] Added {new_from_espn} new picks from ESPN/DraftKings")

    picks, err = fetch_picks()
    if picks is None:
        print(err or "no picks", file=sys.stderr)
        return  # silent pass
    legs, combined = build_long_shot(picks)
    # If we have at least 3 legs but haven't cleared 1000, send a "partial" slip —
    # more picks will accumulate through the week and the full run fires Monday.
    if len(legs) < MIN_LEGS:
        print(f"Not enough legs ({len(legs)}) — need at least {MIN_LEGS}. "
              f"More games needed; will rebuild Monday.", file=sys.stderr)
        return  # truly silent
    is_partial = combined < WEEKLY_TARGET_ODDS

    start, end = _week_window()
    # Compact slip: game | pick @ odds | kickoff (Lagos)
    from zoneinfo import ZoneInfo as _ZI
    from datetime import datetime as _dt
    LAGOS_TZ = _ZI("Africa/Lagos")
    leg_lines = []
    earliest_kick = None
    for i, L in enumerate(legs, 1):
        kick = L.get("kickoff", "")
        kick_str = "TBD"
        if kick:
            try:
                kt = _dt.fromisoformat(kick.replace("Z", "+00:00")).astimezone(LAGOS_TZ)
                kick_str = kt.strftime("%a %d %b %H:%M")
                if earliest_kick is None or kt < earliest_kick:
                    earliest_kick = kt
            except Exception:
                kick_str = kick[:10]
        sport_short = L.get("sport", "").replace("⚽ ", "").replace("⚾ ", "").replace("🏀 ", "").replace("🏒 ", "").replace("🏈 ", "").replace("🏉 ", "").replace("🏏 ", "").replace("🏑 ", "").split("(")[0].strip()
        leg_lines.append(f"  {i}. {L['match']} | {L.get('plain_pick') or L['pick']} @ {L['odds']:.2f} | {kick_str}")

    legs_text = "\n".join(leg_lines)
    first_kick_str = earliest_kick.strftime("%a %d %b %H:%M Lagos") if earliest_kick else "varies"

    if is_partial:
        header = f"🎲 *Long Shot (partial)* — {start}"
        footer = f"⚠️ Only {combined:,.0f}× so far (need 1,000+). More picks build through the week. Full shot fires Monday 8am."
    else:
        header = f"🎲 *Weekly Long Shot* — {start}"
        footer = (f"Place on Bet9ja. Stake ₦{WEEKLY_STAKE:,.0f}–₦{WEEKLY_STAKE_MAX:,.0f} — your call within that range. "
                  "Send me the booking code once placed.")

    msg = (f"{header}\n"
           f"{len(legs)} games · *{combined:,.0f}×* combined odds · stake ₦{WEEKLY_STAKE:,.0f}–₦{WEEKLY_STAKE_MAX:,.0f}\n"
           f"First kickoff: {first_kick_str}\n"
           f"{'—'*30}\n"
           f"{legs_text}\n"
           f"{'—'*30}\n"
           f"{footer}")
    if args.dry_run:
        print(msg)
        return
    ls_id = log_long_shot(legs, combined)

    # Auto-book on SportyBet NG (full slip only)
    booking_code = None
    if not is_partial:
        try:
            import subprocess as _sp, json as _json, os as _os
            _booker = _os.path.join(_os.path.dirname(__file__), "bet9ja_book.py")
            _leg_data = _json.dumps([
                {
                    "match": L["match"],
                    "pick": L.get("plain_pick") or L["pick"],
                    "sport": L.get("sport", ""),
                }
                for L in legs
            ])
            _result = _sp.run(
                ["python3", "-u", _booker, "--legs", _leg_data],
                capture_output=True, text=True, timeout=180,
            )
            raw_code = _result.stdout.strip().splitlines()[-1] if _result.stdout.strip() else ""
            if raw_code and raw_code not in ("DRY_RUN_CODE_PLACEHOLDER", "MANUAL_CODE_NEEDED"):
                booking_code = raw_code
                print(f"SportyBet booking code: {booking_code}")
            else:
                print(f"SportyBet auto-book failed: {_result.stderr[:300]}")
        except Exception as _e:
            print(f"SportyBet auto-book error: {_e}")

    if booking_code:
        final_msg = f"*Booking code: {booking_code}*\n\n{msg}"
    else:
        final_msg = msg

    notify_telegram(final_msg)
    status_note = "partial" if is_partial else "full"
    print(f"Logged {status_note} long shot #{ls_id}: {len(legs)} legs, combined {combined:,.0f}")


if __name__ == "__main__":
    main()
