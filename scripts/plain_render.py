#!/usr/bin/env python3
"""plain_render.py — jargon-free rendering of betting picks for Hendrix.

Plain English, decimal odds, confidence as %, no betting jargon.
Rationale structure: EVIDENCE FIRST, model note last.
  1. Key absences / suspensions (if critical)
  2. Recent form comparison
  3. Head-to-head record
  4. xG / scoring stats
  5. Home advantage context
  6. Elo / rankings (when no form data)
  7. Value closing note: "odds suggest X%, we see Y%"

Language rules:
  - decimal odds always (e.g. 1.85)
  - no "ATS", "EV", "edge", "units", "sharps", "fade", "vig", "juice"
  - no "Our model says" as an opener
  - plain English — if a 10-year-old can't understand it, rewrite it
"""
from collections import defaultdict
import json, re

# ── Confidence ───────────────────────────────────────────────────────────────
def confidence_pct(b):
    ov = b.get("confidence_override")
    if isinstance(ov, (int, float)):
        return round(ov)
    p = b.get("our_prob")
    if isinstance(p, (int, float)):
        return round(p)
    conf = (b.get("confidence") or "").upper()
    return {"HIGH": 72, "MEDIUM": 60, "LOW": 52}.get(conf)

def confidence_word(pct):
    if pct is None:    return "Unrated"
    if pct >= 75:      return "Very strong"
    if pct >= 67:      return "Strong"
    if pct >= 58:      return "Solid"
    if pct >= 52:      return "Slight lean"
    return "Coin-flip"

def confidence_emoji(pct):
    if pct is None:    return "⚪"
    if pct >= 67:      return "🟢"
    if pct >= 58:      return "🟡"
    return "🟠"

# ── Plain pick label ─────────────────────────────────────────────────────────
def plain_pick(b):
    market = (b.get("market") or "").strip()
    pick   = (b.get("pick") or "").strip()
    m = market.lower()
    if "moneyline" in m or m in ("1x2", "h2h", "match winner"):
        return f"{pick} to win"
    if "btts" in m or "both teams" in m:
        return "Both teams to score" + ("" if "yes" in pick.lower() else f" — {pick}")
    if "o/u rounds" in m:
        return f"{pick} rounds (MMA)"
    if "o/u games" in m:
        return f"{pick} games (tennis)"
    if "o/u runs" in m:
        return f"{pick} runs"
    if "o/u points" in m:
        return f"{pick} points"
    # Prop totals — match the unit to the market (check before the goals catch,
    # since these market labels also contain "O/U").
    if "over" in pick.lower() or "under" in pick.lower():
        for kw, unit in (("shots on target", "shots on target"),
                         ("shot", "shots"), ("corner", "corners"),
                         ("card", "cards"), ("foul", "fouls"),
                         ("offside", "offsides")):
            if kw in m:
                return f"{pick} {unit}"
    if "o/u goals" in m or ("o/u" in m and "goal" in m):
        if "over" in pick.lower() or "under" in pick.lower():
            return f"{pick} goals"
    if "over" in pick.lower() or "under" in pick.lower():
        thing = market.replace("Total", "").replace("O/U", "").strip() or "total"
        # drop a trailing number already in the pick to avoid "Over 9.5 Corners 9.5"
        thing = re.sub(r'\s*\d+(?:\.\d+)?$', '', thing).strip() or "total"
        return f"{pick} {thing}".replace("  ", " ")
    if "corner" in m:
        return f"{pick} corners"
    if "card" in m:
        return f"{pick} cards"
    if "handicap" in m or "spread" in m:
        # Parse the line from the pick string if present, e.g. "Chicago White Sox +1.5"
        # or "Over 8.5" → show clearly as "[Team] [+/-line] handicap"
        line_m = re.search(r'([+-]?\d+\.?\d*)', pick)
        if line_m:
            line = float(line_m.group(1))
            # Strip the line from the team/pick name for clarity
            team_part = re.sub(r'\s*[+-]?\d+\.?\d*$', '', pick).strip()
            # Determine sport unit (runs for baseball, goals for soccer, points for basketball)
            sport_s = (b.get("sport") or "").lower()
            if any(x in sport_s for x in ("baseball","mlb","npb","kbo","⚾")):
                unit = "run"
            elif any(x in sport_s for x in ("basketball","nba","nbl","🏀")):
                unit = "point"
            elif any(x in sport_s for x in ("hockey","nhl","🏒")):
                unit = "goal"
            elif any(x in sport_s for x in ("tennis","🎾")):
                unit = "game"
            else:
                unit = "goal"
            units = f"{unit}s" if abs(line) != 1.0 else unit
            sign = "+" if line > 0 else ""
            if team_part:
                if line < 0:
                    return f"{team_part} must win by more than {abs(line):.1f} {units} ({sign}{line:.1f} handicap)"
                else:
                    return f"{team_part} gets a {line:.1f}-{unit} head start ({sign}{line:.1f} handicap)"
            return f"{sign}{line:.1f} handicap"
        return f"Handicap: {pick}"
    if "double chance" in m:
        return f"{pick} (double chance — wins or draws)"
    if "draw no bet" in m or m == "dnb":
        return f"{pick} (draw = stake back)"
    if "scouted" in m:
        return f"Scouted: {pick[:80]}"
    return f"{market}: {pick}" if market else pick

# ── Sport category detection ─────────────────────────────────────────────────
def _sport_cat(b):
    sk = (b.get("sport_key") or "").lower()
    if sk:
        for prefix, cat in [
            ("soccer_", "soccer"), ("football_", "soccer"),
            ("baseball_", "baseball"), ("basketball_", "basketball"),
            ("icehockey_", "hockey"), ("tennis_", "tennis"),
            ("mma_", "mma"), ("boxing_", "mma"),
            ("rugby", "rugby"), ("cricket_", "cricket"),
        ]:
            if sk.startswith(prefix):
                return cat
        return sk.split("_")[0]
    sp = (b.get("sport") or "").lower()
    if any(x in sp for x in ("soccer","football","⚽")):    return "soccer"
    if any(x in sp for x in ("baseball","mlb","npb","kbo","⚾")): return "baseball"
    if any(x in sp for x in ("basketball","nba","euroleague","🏀")): return "basketball"
    if any(x in sp for x in ("hockey","nhl","khl","🏒")):   return "hockey"
    if any(x in sp for x in ("tennis","atp","wta","🎾")):   return "tennis"
    if any(x in sp for x in ("mma","ufc","boxing","🥊")):   return "mma"
    if any(x in sp for x in ("rugby","nrl","🏉")):          return "rugby"
    if any(x in sp for x in ("cricket","ipl","🏏")):        return "cricket"
    if any(x in sp for x in ("table","ping","🏓")):         return "tabletennis"
    if any(x in sp for x in ("volleyball","🏐")):           return "volleyball"
    if any(x in sp for x in ("handball","🤾")):             return "handball"
    return "other"

# ── Scorecard enrichment ─────────────────────────────────────────────────────
def _enrich_from_scorecard(b):
    """If direct evidence fields are missing but scorecard JSON is present, populate them."""
    sc_raw = b.get("scorecard")
    if not sc_raw or isinstance(sc_raw, dict):
        if isinstance(sc_raw, dict):
            for k, v in sc_raw.items():
                if b.get(k) is None and v is not None:
                    b[k] = v
        return
    try:
        sc = json.loads(sc_raw)
        for k, v in sc.items():
            if b.get(k) is None and v is not None:
                b[k] = v
    except Exception:
        pass

# ── Form helpers ─────────────────────────────────────────────────────────────
def _form_dict(b, side):
    """Get form dict, handling both direct field and nested scorecard."""
    key = f"form_{side}"
    f = b.get(key)
    if isinstance(f, dict):
        return f
    if isinstance(f, str):
        try:
            return json.loads(f)
        except Exception:
            return None
    return None

def _form_wins_losses(f):
    """Return (wins, draws, losses, n) from a form dict."""
    if not f:
        return None, None, None, None
    w = f.get("w"); d = f.get("d"); l = f.get("l"); n = f.get("n", 5)
    return w, d, l, n

def _form_label(w, d, l, n):
    """Turn wins/draws/losses into a short string like '4W 0D 1L'."""
    parts = []
    if w is not None: parts.append(f"{w}W")
    if d is not None: parts.append(f"{d}D")
    if l is not None: parts.append(f"{l}L")
    return " ".join(parts) if parts else None

def _form_narrative(b, home, away):
    """
    Build a natural form comparison sentence.
    Returns None if no data.
    Examples:
      "Brazil are in red-hot form — 5W 0D 0L in their last 5. Argentina have been patchy: 2W 1D 2L."
      "Brazil are flying (5W, 1.8 scored/0.4 conceded per game). Argentina are struggling: 1W 3L."
    """
    fh = _form_dict(b, "h")
    fa = _form_dict(b, "a")
    if not fh and not fa:
        return None

    def _team_str(f, name):
        w, d, l, n = _form_wins_losses(f)
        if w is None:
            return None
        lbl = _form_label(w, d, l, n)
        avg_gf = f.get("avg_gf"); avg_ga = f.get("avg_ga")
        base = f"{name}: {lbl} in last {n}"
        if avg_gf is not None and avg_ga is not None:
            base += f" ({avg_gf:.1f} scored, {avg_ga:.1f} conceded per game)"
        return base, w, d, l, n

    h_data = _team_str(fh, home) if fh else None
    a_data = _team_str(fa, away) if fa else None

    if h_data and a_data:
        h_str, hw, hd, hl, hn = h_data
        a_str, aw, ad, al, an = a_data

        # Describe the gap
        h_pts = (hw or 0) * 3 + (hd or 0) if hw is not None else None
        a_pts = (aw or 0) * 3 + (ad or 0) if aw is not None else None

        if h_pts is not None and a_pts is not None:
            gap = h_pts - a_pts
            if gap >= 6:
                opener = f"{home} are in much better form right now — "
            elif gap >= 3:
                opener = f"{home} have the edge on form — "
            elif gap <= -6:
                opener = f"{away} are in much better form right now — "
            elif gap <= -3:
                opener = f"{away} have the edge on form — "
            else:
                opener = "Both sides in similar form — "
            return f"{opener}{h_str}; {a_str}."
        return f"Recent form — {h_str}; {a_str}."

    if h_data:
        return f"{h_data[0]}."
    if a_data:
        return f"{a_data[0]}."
    return None

# ── H2H narrative ─────────────────────────────────────────────────────────────
def _h2h_narrative(h2h, home, away):
    """
    Parse raw H2H text into a readable sentence.
    Input formats vary:
      "Record: Brazil 3W, 1D, 2W Argentina | Last: Brazil 2-1 Argentina (Apr 2024)"
      or free text from Exa
    Returns None if nothing usable.
    """
    if not h2h:
        return None
    if isinstance(h2h, dict):
        for k in ("summary", "text", "recent"):
            if isinstance(h2h.get(k), str) and len(h2h[k]) > 10:
                h2h = h2h[k]
                break
        else:
            return None
    if not isinstance(h2h, str) or h2h.strip().lower() in ("none", "", "null") or len(h2h.strip()) < 10:
        return None
    if "[" in h2h and "http" in h2h:
        return None  # raw URL junk

    # Try structured Record: format
    m = re.search(r'Record:\s*(.+?)(?:\||$)', h2h)
    if m:
        record_part = m.group(1).strip()
        # Extract wins for each team
        wins = re.findall(r'(\d+)W', record_part)
        draws = re.findall(r'(\d+)D', record_part)
        n = sum(int(x) for x in wins) + sum(int(x) for x in draws if draws)
        last_m = re.search(r'Last(?:.*?):\s*(.+?)(?:\(|$)', h2h)
        last_str = last_m.group(1).strip() if last_m else ""

        home_low = home.lower()
        if home_low in record_part.lower():
            # Figure out which wins belong to home
            teams_wins = re.findall(r'(\w[\w\s]*?)\s+(\d+)W', record_part)
            hw = aw = None
            for team, w in teams_wins:
                if home_low in team.lower():
                    hw = int(w)
                else:
                    aw = int(w)
            d = int(draws[0]) if draws else 0
            if hw is not None and aw is not None:
                total = hw + aw + d
                if hw > aw:
                    s = f"{home} have dominated head-to-head — {hw}W {d}D {aw}L in last {total} meetings."
                elif aw > hw:
                    s = f"{away} have the better H2H record — {aw}W {d}D {hw}L in last {total} meetings."
                else:
                    s = f"Even H2H — {hw} wins each in last {total} meetings, {d} draws."
                if last_str:
                    s += f" Last result: {last_str}."
                return s

    # Avg goals from H2H
    avg_m = re.search(r'Avg goals[^:]*:\s*([\d.]+)', h2h)
    if avg_m:
        avg = float(avg_m.group(1))
        extra = f" ({avg:.1f} goals per game in their meetings)" if avg else ""
        return f"H2H data available{extra}."

    # Just return a cleaned version of the raw text if it looks useful
    clean = h2h.strip()
    if len(clean) > 30 and len(clean) < 300:
        # Remove anything that looks like a URL or bracket noise
        clean = re.sub(r'https?://\S+', '', clean)
        clean = re.sub(r'\[.*?\]', '', clean)
        clean = re.sub(r'\s+', ' ', clean).strip()
        if len(clean) > 20:
            return f"H2H: {clean[:260]}."
    return None

# ── Injury / absence highlighting ────────────────────────────────────────────
def _injury_note(b):
    """Return injury/suspension text, or None.

    Rejects raw Exa web-scraper content (match preview / prediction pages).
    Only passes text that actually contains injury/absence keywords.
    """
    inj = b.get("injury") or b.get("injuries") or b.get("team_news") or ""
    if not isinstance(inj, str) or len(inj) < 10:
        return None

    inj_l = inj.lower()

    # Reject obvious prediction-site / match-preview junk from Exa
    junk_phrases = (
        "prediction, betting tips", "betting tips & odds", "match preview",
        "no live streams", "broadcast", "odds comparison",
        "football prediction", "tips and prediction", "check our prediction",
        "world cup qualifier", "squad for fifa", "squad announced",
    )
    if any(p in inj_l for p in junk_phrases):
        return None

    # Only accept text that contains real injury/absence keywords
    real_kw = (
        "injur", "suspend", "ban", "ruled out", "doubtful", "miss",
        "absent", "unavailable", "red card", "hamstring", "knee", "ankle",
        "muscle", "fitness", "illness", "late fitness", "out for", "out of",
        "not play", "will miss", "could miss", "may miss",
    )
    if not any(kw in inj_l for kw in real_kw):
        return None

    if "no injury" in inj_l or "no significant" in inj_l:
        return None

    # Trim to only sentences containing injury language
    inj = re.sub(r'\s+', ' ', inj).strip()
    sentences = re.split(r'(?<=[.!?])\s+', inj)
    useful = [s for s in sentences if any(kw in s.lower() for kw in real_kw)]
    if useful:
        inj = " ".join(useful[:3])
    if len(inj) > 350:
        inj = inj[:350] + "…"
    return inj

# ── Home/away context ─────────────────────────────────────────────────────────
def _venue_note(b, home, away, pick):
    """Add home/away context where relevant."""
    pick_n = (pick or "").strip().lower()
    home_n = (home or "").strip().lower()
    away_n = (away or "").strip().lower()

    if not pick_n or not home_n:
        return None

    # Is the pick the home team?
    if pick_n in home_n or home_n in pick_n:
        return f"{home} are playing at home."
    if pick_n in away_n or away_n in pick_n:
        return f"{away} are the away side here."
    return None

# ── Value closing note ────────────────────────────────────────────────────────
def _value_note(b, pct):
    """
    Closing sentence: what bookmakers imply vs what we see.
    Avoids leading with it. Only added when there's something to say.
    """
    odds        = b.get("odds")
    market_prob = b.get("market_prob")
    ev_val      = b.get("ev")
    n_books     = b.get("_n_books") or b.get("n_books") or 0
    has_sharp   = b.get("has_sharp") or False
    is_model_only = b.get("is_model_only") or False

    if pct is None:
        return None

    odds_s = f"{odds:.2f}" if isinstance(odds, (int, float)) else None

    # Model-only (no market line)
    if is_model_only or (odds is None and market_prob is None):
        if odds_s:
            return f"Implied chance at {odds_s} odds: {round(100/odds):.0f}%. Our estimate: {pct}%."
        return f"Our estimate: {pct}%. No bookmaker line to compare."

    if market_prob is not None:
        gap = pct - market_prob
        books_note = f" (across {n_books} bookmakers)" if n_books and n_books > 1 else ""
        if odds_s:
            implied = round(100 / odds, 1) if isinstance(odds, (int, float)) else None
            implied_s = f" — implying {implied:.0f}%" if implied else ""
        else:
            implied_s = ""

        if abs(gap) < 2:
            if ev_val and ev_val >= 3:
                return (f"Odds {odds_s}{implied_s}. Bookmakers broadly agree on the probability{books_note}. "
                        f"The best available odds are {ev_val:.1f}% better than the market average.")
            elif odds_s:
                return f"Odds {odds_s}{implied_s}. Bookmakers agree on the probability{books_note}."
            return None
        elif gap >= 5:
            return (f"Odds {odds_s}{implied_s}. Bookmakers are at {round(market_prob)}%{books_note} — "
                    f"we see {pct}%, so these odds look better than they should be."
                    + (" Sharp bookmakers also price it here — good sign." if has_sharp else ""))
        elif gap >= 2:
            return (f"Odds {odds_s}{implied_s}. Bookmakers average {round(market_prob)}%{books_note}, "
                    f"we're at {pct}% — slight discrepancy in our favour."
                    + (" Sharp bookmakers agree." if has_sharp else ""))
        elif gap <= -5:
            return (f"Odds {odds_s}{implied_s}. Bookmakers are at {round(market_prob)}%{books_note} — "
                    f"slightly above our estimate of {pct}%, but within acceptable range.")
        else:
            if odds_s:
                return f"Odds {odds_s}{implied_s}. We're at {pct}%, bookmakers at {round(market_prob)}%{books_note}."
            return None
    else:
        if odds_s:
            implied = round(100 / odds, 1) if isinstance(odds, (int, float)) else None
            return (f"Odds {odds_s}"
                    + (f" (implying {implied:.0f}% chance)" if implied else "")
                    + f". Our estimate: {pct}%.")
        return f"Our estimate: {pct}%."

# ── Sport-specific evidence builders ─────────────────────────────────────────

def _soccer_xg(b, home, away):
    """Build xG sentence if data available."""
    xg_h = b.get("xg_h"); xg_a = b.get("xg_a")
    if not isinstance(xg_h, dict) or not isinstance(xg_a, dict):
        return None
    hxg = xg_h.get("xg"); hxga = xg_h.get("xga")
    axg = xg_a.get("xg"); axga = xg_a.get("xga")
    if hxg is None or axg is None:
        return None
    better = home if hxg > axg else away
    diff = abs(hxg - axg)
    xg_note = (f"Expected goals per game — {home} {hxg:.2f} scored / {hxga:.2f} conceded; "
               f"{away} {axg:.2f} scored / {axga:.2f} conceded.")
    if diff >= 0.5:
        xg_note += f" {better} creating significantly more quality chances."
    return xg_note

def _soccer_elo(b, home, away, pct):
    """Elo-based fallback when no form data."""
    elo_diff = b.get("elo_diff")
    if elo_diff is None:
        return None
    gap = abs(int(elo_diff))
    stronger = home if elo_diff > 0 else away
    weaker   = away if elo_diff > 0 else home
    if gap > 200:
        return f"{stronger} are considerably stronger than {weaker} on international rankings (rating gap: {gap} points) — this is a significant mismatch on paper."
    elif gap > 100:
        return f"{stronger} hold a clear ranking advantage over {weaker} (rating gap: {gap} points)."
    elif gap > 50:
        return f"{stronger} are rated slightly above {weaker} based on international rankings (gap: {gap} points)."
    elif gap > 20:
        return f"These sides are evenly matched on paper — small ratings edge to {stronger} ({gap} points)."
    return None

def _soccer_handicap_note(b):
    pick = b.get("pick") or ""
    m = re.search(r"([+-]?\d+\.?\d*)", pick)
    if not m:
        return None
    line = float(m.group(1))
    if line < 0:
        return f"The favourite needs to win by more than {abs(line):.0f} goal{'s' if abs(line)!=1 else ''} for this to pay out."
    return f"The underdog gets a {line:.0f} goal head start — they don't even need to win outright."

def _soccer_ou_stats(b, home, away, pick):
    """For over/under, give goal scoring context."""
    fh = _form_dict(b, "h")
    fa = _form_dict(b, "a")
    parts = []
    if isinstance(fh, dict) and isinstance(fa, dict):
        gf_h = fh.get("avg_gf"); ga_h = fh.get("avg_ga")
        gf_a = fa.get("avg_gf"); ga_a = fa.get("avg_ga")
        if all(x is not None for x in [gf_h, ga_h, gf_a, ga_a]):
            total_exp = gf_h + gf_a
            parts.append(
                f"Goals per game (last 5): {home} score {gf_h:.1f}, concede {ga_h:.1f}; "
                f"{away} score {gf_a:.1f}, concede {ga_a:.1f}. "
                f"Combined average: {total_exp:.1f} goals per game."
            )
            line_m = re.search(r"(\d+\.?\d*)", pick)
            if line_m:
                line = float(line_m.group(1))
                if "over" in pick.lower():
                    if total_exp > line + 0.5:
                        parts.append(f"The expected total of {total_exp:.1f} comfortably clears the {line} line.")
                    elif total_exp > line:
                        parts.append(f"Expected total sits just above the {line} line — margins thin.")
                    else:
                        parts.append(f"Expected total of {total_exp:.1f} is below the line, but bookmakers may be undervaluing these attacking sides.")
                else:
                    if total_exp < line - 0.5:
                        parts.append(f"The expected total of {total_exp:.1f} comfortably stays under the {line} line.")
                    elif total_exp < line:
                        parts.append(f"Expected total sits just below the {line} line — narrow margin.")
    return parts

def _soccer_btts_stats(b, home, away):
    fh = _form_dict(b, "h")
    fa = _form_dict(b, "a")
    if not isinstance(fh, dict) or not isinstance(fa, dict):
        return None
    gf_h = fh.get("avg_gf"); ga_h = fh.get("avg_ga")
    gf_a = fa.get("avg_gf"); ga_a = fa.get("avg_ga")
    if all(x is not None for x in [gf_h, ga_h, gf_a, ga_a]):
        both_score_likely = (gf_h > 0.8 and gf_a > 0.8)
        note = (f"Scoring form (last 5): {home} average {gf_h:.1f} scored / {ga_h:.1f} conceded; "
                f"{away} average {gf_a:.1f} scored / {ga_a:.1f} conceded.")
        if both_score_likely:
            note += " Both sides have been finding the net regularly."
        else:
            note += " One or both sides have been struggling to score."
        return note
    return None

def _mlb_pitching(b, home, away):
    sp_h = b.get("pitcher_h"); sp_a = b.get("pitcher_a")
    era_h = b.get("pitcher_h_era"); era_a = b.get("pitcher_a_era")
    parts = []
    if sp_h or sp_a:
        line = "Pitching matchup — "
        if sp_h:
            line += f"{home} send {sp_h}"
            if era_h is not None:
                quality = "dominant" if era_h < 2.5 else ("solid" if era_h < 3.5 else ("shaky" if era_h > 4.5 else "average"))
                line += f" (ERA {era_h:.2f} — {quality} this season)"
        if sp_a:
            sep = "; " if sp_h else ""
            line += f"{sep}{away} counter with {sp_a}"
            if era_a is not None:
                quality = "dominant" if era_a < 2.5 else ("solid" if era_a < 3.5 else ("shaky" if era_a > 4.5 else "average"))
                line += f" (ERA {era_a:.2f} — {quality})"
        parts.append(line + ".")
        if era_h is not None and era_a is not None:
            if era_h < era_a - 0.5:
                parts.append(f"{home}'s starter has the clear edge on the mound.")
            elif era_a < era_h - 0.5:
                parts.append(f"{away}'s starter has the pitching advantage.")
    bp_h = b.get("bullpen_h_era"); bp_a = b.get("bullpen_a_era")
    if bp_h is not None and bp_a is not None:
        better = home if bp_h < bp_a else away
        parts.append(f"Bullpen ERA — {home} {bp_h:.2f}, {away} {bp_a:.2f}. {better} have the stronger relief corps if it goes late.")
    park = b.get("park_factor")
    if park:
        parts.append(f"Park note: {park}.")
    return parts

def _basketball_stats(b, home, away, market):
    parts = []
    rest = b.get("rest_days")
    if rest is not None and rest != 0:
        rested = home if rest > 0 else away
        days = abs(rest)
        parts.append(f"{rested} have a {days}-day rest advantage over their opponent — fresher legs matter in the NBA.")
    if "handicap" in (market or "").lower() or "spread" in (market or "").lower():
        pick = b.get("pick") or ""
        m = re.search(r"([+-]?\d+\.?\d*)", pick)
        if m:
            line = float(m.group(1))
            if line < 0:
                parts.append(f"The favourite needs to win by more than {abs(line):.0f} points.")
            else:
                parts.append(f"The underdog gets a {line:.0f}-point head start.")
    return parts

def _tennis_stats(b, home, away):
    parts = []
    rank_h = b.get("rank_h"); rank_a = b.get("rank_a")
    if rank_h is not None and rank_a is not None:
        better = home if rank_h < rank_a else away
        worse  = away if rank_h < rank_a else home
        br = min(rank_h, rank_a); wr = max(rank_h, rank_a)
        gap = wr - br
        if gap > 50:
            parts.append(f"{better} (world #{br}) is significantly higher ranked than {worse} (world #{wr}) — a big gap on paper.")
        elif gap > 20:
            parts.append(f"{better} (world #{br}) has a clear ranking edge over {worse} (world #{wr}).")
        else:
            parts.append(f"{better} ranked #{br}, {worse} ranked #{wr} — a close matchup on paper.")
    surf = b.get("surface_record")
    if surf:
        parts.append(f"Surface form: {surf}.")
    return parts

def _mma_stats(b, home, away):
    parts = []
    rec_h = b.get("fighter_h_record"); rec_a = b.get("fighter_a_record")
    style_h = b.get("fighter_h_style"); style_a = b.get("fighter_a_style")
    if rec_h or rec_a:
        line = "Fighter records — "
        if rec_h:
            line += f"{home}: {rec_h}"
            if style_h: line += f" ({style_h})"
        if rec_a:
            line += f"; {away}: {rec_a}"
            if style_a: line += f" ({style_a})"
        parts.append(line + ".")
    return parts

# ── Main rationale builder ────────────────────────────────────────────────────
def plain_rationale(b):
    # Enrich from scorecard JSON if direct fields missing
    b = dict(b)  # don't mutate caller's dict
    _enrich_from_scorecard(b)

    pct    = confidence_pct(b)
    market = (b.get("market") or "").lower()
    pick   = b.get("pick") or ""
    home   = b.get("home") or (b.get("match","").split(" vs ")[0].strip() if " vs " in (b.get("match","")) else "")
    away   = b.get("away") or (b.get("match","").split(" vs ")[1].strip() if " vs " in (b.get("match","")) else "")
    sport  = _sport_cat(b)
    pick_n = pick.lower()

    evidence = []  # each piece of evidence as a sentence/fragment

    # ── 1. Injury / suspensions (most impactful — goes first if significant) ──
    inj = _injury_note(b)
    if inj:
        # If it mentions a key word like "suspended", "banned", "out", "ruled out" — lead with it
        high_impact_kw = ("suspended", "banned", "ruled out", "red card", "missing", "absent", "doubtful", "key player")
        if any(kw in inj.lower() for kw in high_impact_kw):
            evidence.append(f"Team news: {inj}")
        else:
            evidence.append(f"Team news: {inj}")  # still add, just not necessarily "key injury"

    # ── 2. Sport-specific evidence ───────────────────────────────────────────
    if sport == "soccer":
        if "btts" in market or "both teams" in market:
            btts = _soccer_btts_stats(b, home, away)
            if btts: evidence.append(btts)
            form = _form_narrative(b, home, away)
            if form: evidence.append(form)

        elif "handicap" in market or "spread" in market:
            form = _form_narrative(b, home, away)
            if form: evidence.append(form)
            h2h = _h2h_narrative(b.get("h2h"), home, away)
            if h2h: evidence.append(h2h)
            hcap = _soccer_handicap_note(b)
            if hcap: evidence.append(hcap)

        elif "o/u" in market or "over" in pick_n or "under" in pick_n or "total" in market:
            ou_parts = _soccer_ou_stats(b, home, away, pick)
            evidence.extend(ou_parts)
            h2h = _h2h_narrative(b.get("h2h"), home, away)
            if h2h: evidence.append(h2h)

        else:
            # 1X2 — the main match result
            form = _form_narrative(b, home, away)
            if form: evidence.append(form)
            h2h = _h2h_narrative(b.get("h2h"), home, away)
            if h2h: evidence.append(h2h)
            xg = _soccer_xg(b, home, away)
            if xg: evidence.append(xg)
            # Venue only if no form (otherwise form covers it)
            if not form:
                venue = _venue_note(b, home, away, pick)
                if venue: evidence.append(venue)
            # Elo only if no form and no H2H
            if not form and not h2h:
                elo = _soccer_elo(b, home, away, pct)
                if elo: evidence.append(elo)

    elif sport == "baseball":
        evidence.extend(_mlb_pitching(b, home, away))
        form = _form_narrative(b, home, away)
        if form: evidence.append(form)
        h2h = _h2h_narrative(b.get("h2h"), home, away)
        if h2h: evidence.append(h2h)

    elif sport == "basketball":
        form = _form_narrative(b, home, away)
        if form: evidence.append(form)
        evidence.extend(_basketball_stats(b, home, away, market))
        h2h = _h2h_narrative(b.get("h2h"), home, away)
        if h2h: evidence.append(h2h)

    elif sport == "hockey":
        form = _form_narrative(b, home, away)
        if form: evidence.append(form)
        h2h = _h2h_narrative(b.get("h2h"), home, away)
        if h2h: evidence.append(h2h)

    elif sport == "tennis":
        evidence.extend(_tennis_stats(b, home, away))
        form = _form_narrative(b, home, away)
        if form: evidence.append(form)
        h2h = _h2h_narrative(b.get("h2h"), home, away)
        if h2h: evidence.append(h2h)

    elif sport in ("mma", "boxing"):
        evidence.extend(_mma_stats(b, home, away))
        h2h = _h2h_narrative(b.get("h2h"), home, away)
        if h2h: evidence.append(h2h)

    elif sport == "rugby":
        form = _form_narrative(b, home, away)
        if form: evidence.append(form)
        h2h = _h2h_narrative(b.get("h2h"), home, away)
        if h2h: evidence.append(h2h)
        venue = _venue_note(b, home, away, pick)
        if venue and not form: evidence.append(venue)

    elif sport == "cricket":
        form = _form_narrative(b, home, away)
        if form: evidence.append(form)
        h2h = _h2h_narrative(b.get("h2h"), home, away)
        if h2h: evidence.append(h2h)

    else:
        # Generic — try everything
        form = _form_narrative(b, home, away)
        if form: evidence.append(form)
        h2h = _h2h_narrative(b.get("h2h"), home, away)
        if h2h: evidence.append(h2h)
        venue = _venue_note(b, home, away, pick)
        if venue and not form: evidence.append(venue)

    # ── 3. Risk note ─────────────────────────────────────────────────────────
    risk = b.get("risk_note")
    if isinstance(risk, str) and 5 < len(risk) < 220:
        evidence.append(f"Watch out: {risk}")

    # ── 4. Closing value note ─────────────────────────────────────────────────
    val = _value_note(b, pct)
    if val:
        evidence.append(val)

    # ── 5. Absolute fallback ──────────────────────────────────────────────────
    if not evidence:
        odds = b.get("odds")
        if odds and isinstance(odds, (int, float)):
            implied = round(100 / odds, 1)
            evidence.append(
                f"Odds {odds:.2f} imply a {implied:.0f}% chance."
                + (f" Our estimate: {pct}%." if pct else "")
            )
        elif pct:
            evidence.append(f"Model estimate: {pct}%. Limited data available for this pick.")
        else:
            evidence.append("No data available — based on model only.")

    return " ".join(evidence).strip()


# ── Full render ───────────────────────────────────────────────────────────────
def render(bets, mon=None, sun=None, title="Today's Picks"):
    pickable = [b for b in bets if not (b.get("sport") or "").startswith("⚠️")]
    pickable.sort(key=lambda b: -(confidence_pct(b) or 0))
    lines = [f"🔮 *{title}*",
             "_Decimal odds · confidence shown as % · plain English reasons_", ""]
    if not pickable:
        lines.append("No qualified picks right now — nothing met the confidence bar.")
        return "\n".join(lines)

    by_sport = defaultdict(list)
    for b in pickable:
        by_sport[b.get("sport", "Other")].append(b)

    for sport, sb in by_sport.items():
        lines.append(f"*{sport}*")
        for b in sb:
            pct   = confidence_pct(b)
            emoji = confidence_emoji(pct)
            odds  = b.get("odds")
            if isinstance(odds, (int, float)):
                odds_s = f"{odds:.2f}"
            elif b.get("fair_odds"):
                odds_s = f"— (target ≥ {b['fair_odds']:.2f})"
            else:
                odds_s = "—"
            conf_s = f"{pct}% ({confidence_word(pct)})" if pct is not None else "unrated"
            lines.append(f"{emoji} *{b.get('match','')}*")
            lines.append(f"   Pick: *{plain_pick(b)}*")
            lines.append(f"   Odds: {odds_s} · Confidence: {conf_s}")
            lines.append(f"   Why: {plain_rationale(b)}")
            if b.get("kick"):
                lines.append(f"   Starts: {b['kick']} UTC")
            lines.append("")
    lines.append("_Bet responsibly. Model estimates only._")
    return "\n".join(lines)
