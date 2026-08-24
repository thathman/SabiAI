# SportyBet Researcher Skill

Use this skill when the user asks to research, analyze, or extract SportyBet booking codes, match data, or betting research.

---

## Data Sources (Free, No API Key)

| Source | What it gives | Script command |
|--------|---------------|----------------|
| **ESPN hidden API** | Form (last 5), H2H across all competitions, live scores | `fetch_stats.py form` / `fetch_stats.py h2h` |
| **football-data.co.uk** | BTTS%, Over 1.5/2.5%, avg goals, clean sheets — full season CSV | `fetch_stats.py market` |

**Always use these before Exa for domestic league stats and H2H.** They return actual match data, not article summaries.

```bash
SCRIPT="~/.openclaw/workspace/skills/sportybet-researcher/scripts/fetch_stats.py"

# Last 5 results
python3 $SCRIPT form "Arsenal" eng.1
python3 $SCRIPT form "PSG" fra.1

# Head-to-head (searches across EPL, UCL, UEL automatically)
python3 $SCRIPT h2h "Arsenal" "Paris Saint-Germain"

# BTTS%, Over 2.5%, avg goals for the season
python3 $SCRIPT market "Arsenal" E0
python3 $SCRIPT market "PSG" F1

# football-data.co.uk league codes:
# E0=EPL  E1=Championship  SP1=La Liga  D1=Bundesliga
# I1=Serie A  F1=Ligue 1  N1=Eredivisie  P1=Primeira Liga
```

Note: football-data.co.uk does NOT cover UCL/UEL. For cross-competition H2H use `fetch_stats.py h2h`.

---

## Pre-Flight Check

Before starting any research session, run:
```bash
~/.openclaw/workspace/skills/sportybet-researcher/scripts/check_tools.sh
```
If output is `DEGRADED`, note which tools are missing and activate the appropriate fallbacks documented below.

---

## Tool Fallback Chain

### SportyBet extraction
```
1. browser → mobile URL (https://www.sportybet.com/ng/m/code-hub/load-code)
2. browser → desktop URL if mobile fails (https://www.sportybet.com/ng/booking?code=[CODE])
3. browser screenshot → Claude vision if DOM extraction fails
```

### Match research (per match)
```
1. exa_search        — primary (neural, football-aware, API key configured)
2. firecrawl_scrape  — for JS-heavy stats pages or thin Exa results
3. scrapling         — for bot-protected sites (SofaScore, FlashScore)
4. gemini_search     — AI-grounded synthesis pass (GEMINI_API_KEY configured)
5. web_fetch         — lightweight fallback for mostly-static pages (FBref, etc.)
6. DuckDuckGo        — last resort, always available, no key needed
```

Use the research.sh script to automate steps 1–4 for a single match.

---

## Booking Code Lookup

### Step 1 — Load the ticket

Navigate to:
```
https://www.sportybet.com/ng/m/code-hub/load-code
```
Use browser profile `openclaw`. Wait 4 seconds after clicking Load.

**If mobile page is empty or shows CAPTCHA:**
→ Switch immediately to desktop URL:
```
https://www.sportybet.com/ng/booking?code=[CODE]
```
Maximum 2 retries total. After 2 failures → take screenshot → use Claude vision to read match list.

### Step 2 — Extract match data

From the browser snapshot (`compact: false`) or screenshot, extract per match:
- Home team and away team
- Market type (Over/Under, BTTS, 1X2, DNB, etc.)
- Selection (e.g. "Over 2.5", "Both Teams to Score - Yes", "Home Win")
- Odds value
- Competition / league name

If DOM snapshot is unparseable → take screenshot → Claude vision reads it directly. Do NOT attempt tesseract or PIL — neither is installed.

---

## Step 3 — Session Cache

Before researching any match, check: **has this team appeared earlier in the same slip?**

If yes: reuse the form/injury findings already gathered for that team. Do not re-search it.

Maintain a simple in-memory dict as you work through the slip:
```
team_cache = {
  "Arsenal": { "form": "W W D W W", "avg_goals": 2.4, "injuries": "none known" },
  ...
}
```

---

## Step 4 — Research Each Match

Use the research script for consistent output:
```bash
~/.openclaw/workspace/skills/sportybet-researcher/scripts/research.sh \
  "Team A" "Team B" "Over 2.5" "EPL"
```

The script handles the full fallback chain. Read its output and use it to populate the analysis section.

For manual research when the script is unavailable, follow these steps:

### 4a — Exa search (primary)

Query templates per market:

**Over 2.5 / Over 1.5:**
```
exa: "[Team A] vs [Team B] preview stats [year]"
exa: "[Team A] average goals per game [year]"
exa: "[Team B] average goals per game [year]"
exa: "[Team A] [Team B] over under goals stats"
```

**BTTS:**
```
exa: "[Team A] [Team B] both teams to score statistics"
exa: "[Team A] clean sheets [year]"
exa: "[Team B] goals scored every game [year]"
```

**1X2 / DNB:**
```
exa: "[Team A] home record [year] wins draws losses"
exa: "[Team B] away form [year]"
```

**Always (every match):**
```
exa: "[Team A] injury news suspension [current date]"
exa: "[Team B] injury news suspension [current date]"
exa: "[Team A] vs [Team B] head to head last 3 seasons results [year]"
```

⚠️ **H2H freshness rule:** H2H queries MUST include the current year or "last 3 seasons". Exa will surface old articles (e.g. "Team A has never lost to Team B") that are factually outdated. Always check the article date. If the H2H result predates the last 12 months, search again with `freshness: year` filter or add the current year explicitly to the query.

### 4b — Stats site playbook

| Site | Method | Why |
|------|--------|-----|
| `sofascore.com` | scrapling stealthy-fetch | Cloudflare protected |
| `flashscore.com` | scrapling or firecrawl | Anti-bot |
| `footystats.org` | firecrawl_scrape | JS-heavy |
| `fbref.com` | web_fetch | Mostly static |
| `soccerstats.com` | web_fetch | Mostly static |
| `transfermarkt.com` | firecrawl_scrape | For injuries/squad |

```bash
# Scrapling for bot-protected:
~/.scrapling-venv/bin/scrapling extract stealthy-fetch --ai-targeted "https://www.sofascore.com/..."

# Firecrawl for JS-heavy:
# Use firecrawl_scrape tool with the URL
```

### 4c — League data tiers

| Tier | Leagues | Approach |
|------|---------|----------|
| **Rich** | EPL, La Liga, Serie A, Bundesliga, Ligue 1, UCL, UEL | Full pipeline — form + H2H + injuries + stats site |
| **Medium** | Championship, Eredivisie, Primeira Liga, Copa Libertadores | Exa + Firecrawl, skip H2H if thin |
| **Thin** | NPFL, CAF competitions, lower Asian leagues | Exa form only, skip H2H, default to MEDIUM confidence |

---

## Step 5 — Quality Gate (before writing output)

For each match, check before assigning confidence:

| Check | Pass condition | Fail effect |
|-------|----------------|-------------|
| Form data for both teams | ≥3 results each | Force LOW confidence |
| H2H found | ≥2 meetings | OK to skip for thin leagues |
| Injury check done | Searched for both teams | Required for HIGH |
| Stats support the pick | e.g. Over 2.5 pick → avg goals > 2.0 combined | Downgrade confidence if contradicted |

**Confidence rules:**
- **HIGH** — Form, H2H, injury check all done. Stats confirm the selection.
- **MEDIUM** — Some data gaps, or stats are mixed (not clearly for or against).
- **LOW** — Thin data, stats contradict the pick, or key players injured.

---

## Step 6 — Output (PLAIN LANGUAGE — Hendrix does not speak betting jargon)

**Hard rules for every report:**
- **Decimal odds only** (e.g. `1.85`), never fractional/American.
- **Confidence as a percentage** plus a simple word (e.g. `68% — Strong`). Never just HIGH/MEDIUM/LOW.
- **"Why" in plain English** anyone can read. No "EV", "value", "no-vig", "Kelly" in the text.
- Prefer **events likely to happen** (over/under goals, both teams to score, corners, cards) alongside win/draw/loss.

Confidence words: ≥75% Very strong · ≥67% Strong · ≥58% Solid · ≥52% Slight lean · else Coin-flip.

### Booking code report:
```
🔮 Booking code: [CODE]  ·  [N] games  ·  Combined odds: [X.XX] (decimal)

1. [Team A] vs [Team B]  ([Competition])
   Pick: [plain selection, e.g. "Over 2.5 goals" / "Both teams to score" / "Team A to win"]
   Odds: [X.XX] (decimal)  ·  Confidence: [NN]% ([word])
   Why: [one or two plain sentences — form, scoring, H2H, injuries in everyday words]

2. ...

────────────────────────
The verdict (plain):
✅ Most likely to land: [match numbers + why in a few words]
⚠️ Riskiest leg: [match number + why]
Overall slip confidence: [NN]% ([word])
```

---

## Step 7 — Log the Slip + Telegram Notification

After delivering the analysis, do two things:

### 7a — Log the picks to the shared database (bets.db → `predictions`)

Do NOT use results.json (deprecated). Log every analysed match into the shared
`bets.db` so it feeds the dashboard and the accuracy backtest. Pipe one JSON object
into `log_prediction.py`:

```bash
echo '{
  "code": "TS4R2D",
  "source": "researcher",
  "matches": [
    {"sport":"⚽ EPL","match":"Team A vs Team B","kickoff":"2026-06-05 15:00",
     "market":"Total Goals","pick":"Over 2.5","odds":1.85,
     "confidence_pct":68,"plain_rationale":"Both teams score freely and defend poorly.",
     "data_completeness":0.9}
  ]
}' | python3 ~/.openclaw/workspace/skills/sportybet-researcher/scripts/log_prediction.py
```

`odds` are decimal, `confidence_pct` is a number 0–100, `plain_rationale` is the
same everyday-language sentence you showed the user. Returns `{"ok":true,"logged":N}`.

### 7b — Send Telegram summary card

Send to Telegram channel `YOUR_TELEGRAM_CHANNEL_ID_HERE`:
```
📋 Slip: [CODE] | [N] games | Odds: [X.XX]
[Slip confidence signal]

[For each match, one line:]
N. [Team A] vs [Team B] — [Selection] [confidence emoji]

Reply W (won) or L (lost) when it settles.
```

Confidence emojis (by %): 🟢 ≥67% · 🟡 ≥58% · 🟠 below 58%

### 7c — Handling W/L replies

Outcomes are settled automatically from results APIs (`settle.py` / `value_bet_finder.py --auto-settle`).
If the user replies `W` or `L` before auto-settle runs, settle the matching `predictions`/`bets`
rows in `bets.db` by `code` (or most recent): set `outcome` = `win`/`loss` and `settled_at` = now.

---

## Research by Prompt (no booking code)

When user asks e.g. "find today's best Over 2.5 games":

1. Search for today's fixtures:
```
exa: "football matches today [date] schedule"
exa: "best over 2.5 picks today [date]"
```
2. Identify 5-8 candidate matches
3. Run research.sh for each (or use Step 4 manually)
4. Rank by confidence, return top 3-5 with full analysis

---

## Accuracy Tracking (on request)

When the user asks "how are my picks doing?" run the shared backtest (reads bets.db,
plain-language summary + calibration + CLV):

```bash
python3 ~/.openclaw/workspace/scripts/backtest.py
```

It reports the real win rate, whether stated confidence matches reality (calibration),
and whether picks beat the closing line (CLV = genuine edge). All decimal odds / % based.

---

## Notes

- Browser profile: `openclaw`
- CDP endpoint: `http://YOUR_HOST_IP_HERE:3000`
- Scrapling binary: `~.scrapling-venv/bin/scrapling`
- Results store: shared `~/.openclaw/workspace/data/bets.db` (`predictions` table) — log via `scripts/log_prediction.py`
- Booking codes: alphanumeric, 6-8 chars (e.g. `TS4R2D`)
- Do NOT attempt tesseract, PIL, or any OCR Python libs — none are installed
- Gemini search (`GEMINI_API_KEY` is set) is good for a synthesis/second-opinion pass on uncertain matches
