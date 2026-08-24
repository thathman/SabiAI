# Value Bet Scanner Skill

Use this skill when Hendrix asks for value bets, betting picks, or sports research.

**Trigger phrases:** "scan for value bets", "what are this week's picks", "find me value bets", "check the bets", "any good bets this week", "value bets for [sport]"

---

## What it does

Scans 34+ sports for value bets using:
- Live bookmaker odds (The Odds API — 40+ bookmakers)
- Team Elo strength (ClubElo)
- Recent form (ESPN API)
- Historical BTTS/Over/corners/cards stats (football-data.co.uk)
- Injury/suspension news (Exa)
- NCAAB college basketball (ActionNetwork)
- Volleyball, table tennis, rugby union (Exa value scout)

Value = our model probability > bookmaker's no-vig probability. Kelly ¼ sizing.

---

## How to run

### Full weekly scan (all sports, 5%+ edge):
```bash
python3 ~.openclaw/workspace/scripts/value_bet_finder.py \
  --format telegram --min-ev 0.05
```

### Football only:
```bash
python3 ~.openclaw/workspace/scripts/value_bet_finder.py \
  --sport soccer --format telegram --min-ev 0.05
```

### Specific sport:
```bash
# Options: soccer, basketball, tennis, boxing, mma, combat, baseball, mlb,
#          rugby, nrl, hockey, nhl, cricket, afl, handball, nfl, ncaaf,
#          ncaab, college, wnba, nba, volleyball, "table tennis", "rugby union"
python3 ~.openclaw/workspace/scripts/value_bet_finder.py \
  --sport tennis --format telegram --min-ev 0.03
```

### Lower the threshold for more picks:
```bash
python3 ~.openclaw/workspace/scripts/value_bet_finder.py \
  --format telegram --min-ev 0.03
```

---

## After running

1. **Send the full output to Telegram** channel `YOUR_TELEGRAM_CHANNEL_ID_HERE` (The Clawsons). Do not truncate.

2. **Log the picks** — append to the results file:
```bash
python3 - <<'EOF'
import json, datetime
path = "~.openclaw/workspace/data/value_bet_results.json"
# Read existing
try:
    with open(path) as f: data = json.load(f)
except: data = []
# Build entry from scan output (summary only)
entry = {
    "week": datetime.date.today().strftime("%Y-W%V"),
    "date": str(datetime.date.today()),
    "picks": [],   # populate from scan output
    "actual_outcome": None
}
data.append(entry)
with open(path, "w") as f: json.dump(data, f, indent=2)
print("Logged")
EOF
```

3. **Send a Telegram summary card** after logging:
```
📋 Week [W] value picks logged — [N] picks.
Reply W (all won) or L (any lost) when the week settles.
```

---

## Bet history & results tracking

Every pick is stored in **SQLite** (`data/bets.db`) — one row per bet, permanent record.

### View pending bets (unsettled):
```bash
python3 ~.openclaw/workspace/scripts/bet_history.py --pending
```

### Settle a whole week (most common — after Hendrix reports W or L):
```bash
python3 ~.openclaw/workspace/scripts/bet_history.py --settle-week 2026-W22 W
python3 ~.openclaw/workspace/scripts/bet_history.py --settle-week 2026-W22 L
```

### Settle a single bet by ID:
```bash
python3 ~.openclaw/workspace/scripts/bet_history.py --settle abc123 W
```
(bet IDs shown in --pending output)

### Full stats (win rate by sport, market, bookmaker):
```bash
python3 ~.openclaw/workspace/scripts/bet_history.py --stats
python3 ~.openclaw/workspace/scripts/bet_history.py --stats --sport soccer
```

### When Hendrix asks "how are my picks doing?":
```bash
python3 ~.openclaw/workspace/scripts/value_bet_finder.py --accuracy
```

---

## Odds source

- **TheRundown API** — primary odds source (15+ sportsbooks, real-time)
  - Sign up: https://therundown.io/api
  - Key env var: `RUNDOWN_API_KEY`
  - Set in `~/.config/systemd/user/openclaw-gateway.service.d/20-secrets.conf`
- **Model-first**: football picks surface even without a key using Elo+Form+H2H
- **Confidence tiers** (model-only picks): 🔴 HIGH · 🟠 MEDIUM · ⚪ LOW

## Output guide

| Icon | Meaning |
|------|---------|
| 🟢 | EV ≥ 8% — strong value |
| 🟡 | EV 5–8% — moderate value |
| 🔵 | EV 3–5% — marginal value |
| 📐 | Model pick — no API odds, verify manually |
| ✓sharp | At least one sharp book (Pinnacle/Betfair) in the consensus |
| ⚠️ verify | EV >150% — likely stale/error line, act fast or skip |
