# SabiAI — Personal Betting Analyst

SabiAI is a personal betting intelligence engine. It scans sportsbook odds,
builds probabilistic models of match outcomes, finds **+EV (positive expected
value)** bets using the **Kelly criterion**, places them across three
bookmakers with three distinct bankroll strategies, logs every pick, and
learns from outcomes to get sharper over time.

> **Note:** this repo is the engine. Secrets (API keys, tokens, phone numbers,
> channel IDs) have been stripped — see [Environment Variables](#environment-variables).

---

## What it does

- **Scanner tier** — pulls odds from multiple sources (1xBet, SportyBet,
  Bet9ja, ESPN, API-Football, Sofascore, TheRundown, Exa) and normalizes them
- **Model tier** — Dixon-Coles / Poisson / ELO / feature-based models estimate
  true match probabilities
- **Value tier** — compares model probability vs implied bookmaker probability
  to find +EV edges, sized with Kelly fraction
- **Execution tier** — three bookmaker-specific bet types (below)
- **Logging tier** — every pick, stake, odds, and settlement in SQLite
- **Learning loop** — periodic retraining (feature refit + model calibration)
  against settled outcomes

## Three bet types

| Bet type | Bookmaker | Concept |
|---|---|---|
| **Kelly** | 1xBet | Single, mathematically-sized stake on a value edge (`value_bet_finder.py`) |
| **Chain Compound** | SportyBet | Multi-leg chains where winnings roll forward (accumulator with stake growth) |
| **Weekly Long Shot** | Bet9ja | One low-probability/high-odds ticket per week, tiny stake, big upside |

---

## Architecture

```
                    ┌──────────────────────────────┐
                    │         SCANNERS             │
                    │  1xBet · SportyBet · Bet9ja  │
                    │  ESPN · API-Football · etc.  │
                    └──────────────┬───────────────┘
                                   ▼
                    ┌──────────────────────────────┐
                    │         MODEL TIER           │
                    │  Dixon-Coles · Poisson ·    │
                    │  ELO · feature model         │
                    └──────────────┬───────────────┘
                                   ▼
                    ┌──────────────────────────────┐
                    │       VALUE ENGINE           │
                    │  model prob vs implied odds  │
                    │  → EV filter → Kelly sizing  │
                    └──────────────┬───────────────┘
                                   ▼
        ┌──────────────┬───────────────┬──────────────┐
        ▼              ▼               ▼              ▼
   ┌─────────┐   ┌────────────┐  ┌────────────┐  ┌─────────┐
   │  KELLY  │   │   CHAIN    │  │  LONG SHOT │  │  LOGGING│
   │ 1xBet   │   │  SportyBet │  │   Bet9ja   │  │ SQLite  │
   └─────────┘   └────────────┘  └────────────┘  └────┬────┘
                                                      ▼
                                              ┌─────────────┐
                                              │  LEARNING   │
                                              │ loop: refit │
                                              │ + calibrate │
                                              └─────────────┘
```

## File structure

```
sabiai-engine/
├── README.md
├── SABIAI.md                  # engine overview & dashboard docs
├── SOUL.md / IDENTITY.md      # agent identity
├── AGENTS.md                  # workspace rules (team coordination)
├── HEARTBEAT.md               # proactive-check checklist
├── OPERATING_MANUAL.md        # day-to-day operating procedures
├── TOOLS.md                   # local tool notes (sanitized)
├── lessons.md                 # accumulated lessons learned
├── scripts/
│   ├── value_bet_finder.py    # KELLY: scan → model → value picks
│   ├── continuous_bet.py      # chain compound runner
│   ├── weekly_long_shot.py    # weekly long-shot ticket builder
│   ├── record_pick.py         # log / settle / query picks
│   ├── record_chain.py        # record chain accumulators
│   ├── record_accumulator.py  # record accumulator bets
│   ├── backtest*.py           # backtesting harnesses
│   ├── fast_backtest.py
│   ├── sabiai_scraper.py      # screenshot/OCR odds scraping
│   ├── sabiai_analyze.py      # analysis dashboard data
│   ├── sabiai_data.py / sabiai_init.py / sabiai_v2.py
│   ├── value_engine.py        # EV + Kelly core math
│   ├── dixon_coles.py         # Dixon-Coles model
│   ├── nfl_elo.py / features.py / learn.py
│   ├── sportsbook.py          # odds API clients (sanitized keys)
│   ├── sofascore.py / espn_odds.py / apifootball.py
│   ├── sportybet_odds.py / sportybet_book.py
│   ├── bet9ja_book.py
│   ├── filter_high_conf.py / plain_render.py
│   ├── bet_history.py / live_bets.py / bet9ja_book.py
│   ├── money.py / expense_heartbeat.sh / monthly_pl_report.sh
│   ├── backup_bets_db.sh      # DB backup
│   ├── value_bet_daily.sh     # daily cron entrypoint
│   └── ... (support scripts)
├── skills/                    # SKILL.md playbooks (flattened)
│   ├── sabiai_SKILL.md
│   ├── value-bet-scanner_SKILL.md
│   ├── sportybet-researcher_SKILL.md
│   ├── betting-record_SKILL.md
│   ├── money_SKILL.md
│   └── sabiai-onboarding_SKILL.md
└── data/
    ├── schema.sql             # full SQLite schema of bets.db + sabiai_v2.db
    ├── picks.json             # current picks state
    ├── longshot_weekly.json   # weekly long-shot state
    ├── scraper_state.json     # scraper dedup state
    └── risk-review-*.md       # periodic risk reviews
```

---

## Setup

### 1. Dependencies

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install requests beautifulsoup4 scrapy scrapy-playwright lxml pandas numpy scikit-learn openpyxl
# optional: playwright install chromium
```

Main runtime deps: `requests`, `beautifulsoup4`, `lxml`, `pandas`, `numpy`,
`scikit-learn`. Scraping additions: `scrapy`, `scrapy-playwright` (or
scrapling) for JS-heavy bookmaker pages.

### 2. Environment variables

Create `~/.env` (or your secrets file) with **names only** — values are yours
to supply:

| Variable | Used by |
|---|---|
| `RUNDOWN_API_KEY` | TheRundown odds (MLB/WNBA/NHL/NBA/NCAAB) |
| `EXA_API_KEY` | Exa neural search for injury/news context |
| `RAPIDAPI_KEY` / `RAPID_API_KEY` | RapidAPI sports endpoints (Sofascore, OddsAPI) |
| `ODDSAPI_KEY` | The Odds API |
| `PERFEX_TOKEN` | Perfex CRM API (money script) |
| `OPENAI_API_KEY` | image/OCR odds extraction in scraper |
| `ELEVENLABS_API_KEY` | TTS (bedtime story, minor) |
| `GEMINI_API_KEY` | Gemini synthesis pass in researcher |
| `SABIAI_PIN` | dashboard write-auth PIN override (default 1234) |
| `TELEGRAM_BOT_TOKEN` | Telegram delivery |
| `WA_TARGET` | WhatsApp delivery target (E.164) |

No `~/.env` file is committed or needed for the repo to run — scripts
already fall back to env vars at runtime.

### 3. Database init

```bash
python3 scripts/sabiai_init.py      # creates picks DB tables
python3 scripts/sabiai_v2.py        # v2 schema/migration entrypoint
```

Reference schema: see `data/schema.sql` (19 tables across `bets.db` and
`sabiai_v2.db`).

---

## Usage

### Kelly value betting (1xBet)

```bash
# scan + model + print value bets (plain text)
python3 scripts/value_bet_finder.py --format plain --min-ev 0.03

# high-confidence filter
python3 scripts/filter_high_conf.py

# log a pick (or use record_pick.py)
python3 scripts/record_pick.py log --match "ARS vs CHE" --market 1X2 \
  --pick home --odds 2.30 --stake 50 --ev 0.07 --bookmaker 1xBet
```

### Chain compound (SportyBet)

```bash
python3 scripts/continuous_bet.py --stake 500 --target-profit 50000
# each leg's winnings roll into the next; stops at target or on a loss
python3 scripts/record_chain.py --slip-code CHAIN-2026-06-07-002
```

### Weekly long shot (Bet9ja)

```bash
python3 scripts/weekly_long_shot.py --stake 200
# builds one multi-leg acca with high odds, tiny stake, weekly cadence
```

### Backtesting

```bash
python3 scripts/backtest.py          # full backtest
python3 scripts/fast_backtest.py     # quick iteration backtest
python3 scripts/value_engine.py      # EV/Kelly core (importable)
```

### Daily / weekly automation

```bash
# morning scan for value bets
scripts/value_bet_daily.sh

# end-of-month P&L report
scripts/monthly_pl_report.sh

# DB backup
scripts/backup_bets_db.sh
```

---

## Workflows explained

### Kelly workflow

1. `scraper` fetches current odds from 1xBet/ESPN/Rundown/etc.
2. `dixon_coles.py` / `features.py` estimate each team's true win/draw/loss probs.
3. `value_engine.py` computes `EV = p_true * odds - 1`; filters `EV >= min_ev`.
4. Stake sized by Kelly: `f* = (b*p - q) / b`, scaled to a fraction of bankroll.
5. Pick logged with `record_pick.py` → appears in dashboard/history.
6. On settlement, `record_pick.py settle` marks win/loss → backtest + learning data.

### Chain compound workflow

- Pick a target profit and starter stake.
- Each leg: single bet on a high-confidence outcome, winnings roll forward.
- The chain stops automatically at target, or on a loss.
- Slip recorded with `record_chain.py` for P&L tracking.

### Weekly long shot workflow

- Model identifies low-probability, high-odds combinations.
- One ticket/week, stake is pocket change relative to bankroll (loss is
  absorbed; win is a season highlight).
- State persisted in `data/longshot_weekly.json` (dedup / weekly reset).

---

## Database schema

From `data/schema.sql` (tables across both DBs). Key tables:

- `bets` — one row per settled/tracked pick: bet_id, scan_date, week, sport,
  match, market, pick, odds, bookmaker, ev, our_prob, kelly, model, outcome,
  settled_at, notes.
- `picks` — current open picks (dashboard-facing state).
- `bankroll` / `bankroll_history` — bankroll tracking (Kelly sizing input).
- `chains` / `chain_legs` — SportyBet chain compound records.
- `longshots` — weekly long-shot tickets.
- `learned_*` / `model_*` — learning-loop artifacts (feature weights,
  calibration bins).

Full DDL: `data/schema.sql`.

## Learning loop

1. Picks settle → outcomes written to `bets` (`outcome` column).
2. `learn.py` refits feature model weights on the expanded dataset.
3. Calibration pass re-bins `our_prob` vs realised frequency.
4. Next scan uses the updated model → probabilities get sharper.
5. `backtest*.py` verifies the loop improved EV capture before new settings
   go live.

---

## Recommended cron setup

```cron
# daily value-bet scan (Kelly)
0 6 * * * cd ~/sabiai-engine && ./scripts/value_bet_daily.sh

# weekly long shot (Monday morning)
0 7 * * 1 cd ~/sabiai-engine && python3 scripts/weekly_long_shot.py

# daily DB backup
30 5 * * * cd ~/sabiai-engine && ./scripts/backup_bets_db.sh

# monthly P&L report
0 8 1 * * cd ~/sabiai-engine && ./scripts/monthly_pl_report.sh
```

---

## Safety & bankroll

- Kelly stakes are computed against **available bankroll** (see
  `data/finance_context.md` in the workspace and the finance team
  coordination in `AGENTS.md`).
- Losses are logged and reflected in the shared bankroll so the food and
  money agents can adjust budgets.
- Risk reviews are run periodically — see `data/risk-review-*.md`.

## License

Private / personal — not intended for redistribution.
## Dashboard

The SabiAI dashboard is a FastAPI app served at `localhost:8090` (or `picks.hendrix.com.ng` in production).

**Location:** `dashboard/app.py`

**Systemd service:** `systemd/sabiai-dashboard.service`

**To install the service:**
```bash
cp systemd/sabiai-dashboard.service ~/.config/systemd/user/
# Edit WorkingDirectory to point to your sabiai-engine/dashboard/ path
systemctl --user daemon-reload
systemctl --user enable --now sabiai-dashboard
```

**Environment variables:**
- `DASHBOARD_FINANCE_PW` — PIN for the finance view (default: set in service file)

**Endpoints:**
- `/` — Overview
- `/picks` — All picks
- `/betchain` — Chain compound tracker
- `/longshot` — Weekly long shot monitor
- `/history` — Bet history
- `/finance` — Financial view (PIN protected)
- `/diary` — Betting diary
- `/strategies` — Strategy analysis
- `/live` — Live bets

**Write auth:** POST endpoints require `X-SabiAI-Key` header. Token is generated at `data/.dashboard_token`. Frontend exchanges PIN via `GET /api/write-key?pin=`.

## Dashboard

The SabiAI dashboard is a FastAPI app served at `localhost:8090` (or `picks.hendrix.com.ng` in production).

**Location:** `dashboard/app.py`

**Systemd service:** `systemd/sabiai-dashboard.service`

**To install the service:**
```bash
cp systemd/sabiai-dashboard.service ~/.config/systemd/user/
# Edit WorkingDirectory to point to your sabiai-engine/dashboard/ path
systemctl --user daemon-reload
systemctl --user enable --now sabiai-dashboard
```

**Environment variables:**
- `DASHBOARD_FINANCE_PW` — PIN for the finance view (default: set in service file)

**Endpoints:**
- `/` — Overview
- `/picks` — All picks
- `/betchain` — Chain compound tracker
- `/longshot` — Weekly long shot monitor
- `/history` — Bet history
- `/finance` — Financial view (PIN protected)
- `/diary` — Betting diary
- `/strategies` — Strategy analysis
- `/live` — Live bets

**Write auth:** POST endpoints require `X-SabiAI-Key` header. Token is generated at `data/.dashboard_token`. Frontend exchanges PIN via `GET /api/write-key?pin=`.
