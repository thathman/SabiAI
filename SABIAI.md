# SABIAI.md — Clawson's Complete Betting System Reference

Read this whenever Hendrix mentions bets, picks, odds, chain, longshot, Kelly, SportyBet, 1xBet, Bet9ja, or SabiAI.

**Last updated: 2026-06-09** (post-audit overhaul: bookmaker routing, bankroll ledger, learning loop, national-team Elo, auth, backups).

---

## 1. What SabiAI Is

SabiAI is Hendrix's personal betting analyst. It's a FastAPI dashboard at `picks.hendrix.com.ng` (also `localhost:8090`), backed by a Python engine and SQLite database at `~.openclaw/workspace/data/bets.db`.

Scans are normally triggered by Hendrix asking for them. `value_bet_daily.sh` is the full daily pipeline (settle → learn → backup → scan → WhatsApp) — runnable manually or by cron if Hendrix decides to schedule it.

---

## 2. The Three Bet Types

### A — Kelly Picks (Daily Analysis)
- **What:** Value bets where our model probability beats the bookmaker's implied odds.
- **Run:** `cd ~.openclaw/workspace/scripts && python3 value_bet_finder.py --format simple --band 1.30-2.50 --min-ev 0.03`
- **Bookmaker:** 1xBet
- **Who picks:** Scanner surfaces; Hendrix decides which to place.

### B — Compound Chain Bet (30-day challenge)
- **What:** One compounding bet per day. Starts ₦1,000. Wins compound. Goal: 30 straight days.
- **Bookmaker:** SportyBet ONLY
- **Odds:** ≥1.30 combined per day.
- **On win:** stake × odds → next day. Day count advances at SETTLE, not log.
- **On loss:** reset to ₦1,000, `streak_status='restrategy'`, **7-day break** — `restrategy_until` is set automatically by `record_pick.py settle`.
- **State:** `continuous_bet_state` (id=1).

### C — Weekly Long Shot
- **What:** One big accumulator per week (Mon–Sun, cutoff 7am Monday Lagos). 20+ near-certain legs stacked to ≥1,000× combined. Stake ₦100–1,000.
- **Bookmaker:** **Bet9ja** ONLY (changed from SportyBet June 2026)
- **Run:** `python3 weekly_long_shot.py` (`--dry-run` to preview)
- **Booking code:** the script calls `bet9ja_book.py` (real Chrome + Playwright) to auto-generate a Bet9ja booking code. **From the week of June 15, 2026 this happens automatically whenever the long shot is generated.** If booking fails, give Hendrix the legs to place manually.
- **Monitoring:** dashboard `/longshot`; API `GET /api/long-shot/monitor`.

---

## 3. Bookmaker Assignment — Non-Negotiable

| Bet type          | Bookmaker   | Booking script        |
|-------------------|-------------|-----------------------|
| Kelly picks       | 1xBet       | manual                |
| Live bets         | 1xBet       | manual                |
| Chain (compound)  | SportyBet   | manual (screenshot)   |
| Long shot         | **Bet9ja**  | `bet9ja_book.py`      |

Scanner odds (TheRundown/ESPN/DraftKings) are US reference lines. The real Nigerian-book odds differ — **always log the odds from the actual slip/screenshot**.

---

## 4. Screenshot Workflow

1. Read screenshot → extract match, pick, odds, bookmaker.
2. Bookmaker → bet type (SportyBet→compound, 1xBet→kelly/live, Bet9ja→longshot).
3. Log:
```bash
cd ~.openclaw/workspace/scripts
python3 record_pick.py log --match "Nigeria vs Ghana" --pick "Nigeria" --odds 1.45 \
  --type compound --market "1X2" --sport "Football" --bookmaker "SportyBet"
```
4. Confirm: "Logged — Day X/30, stake ₦Y, odds Z. Next stake if win: ₦W."
5. Settle after the game:
```bash
python3 record_pick.py settle --match "Nigeria vs Ghana" --result win   # or --id N
```
Settling a compound bet auto-updates chain state AND writes the bankroll ledger row.
Multi-leg chains: `record_chain.py` (writes accumulators + legs + bets + state + ledger in one transaction).

---

## 5. The Bankroll Ledger (source of money truth)

`bankroll` table: **one row per settled money event.** Columns: `delta` (net cash change, + or -), `balance` (running), `kind` (`chain_win|chain_loss|acc_win|acc_loss|longshot_win|longshot_loss|chain_pending`).

- Dashboard `overview()` computes `bankroll_current = bankroll_start + SUM(delta)`. Never hand-edit balances; insert correct delta rows.
- Settle paths (`record_pick.py`, `record_accumulator.py`) write ledger rows automatically.
- Pending chain stakes have `delta=NULL` (excluded from P/L until settled).

---

## 6. The Learning Loop (runs after every settle)

```bash
python3 sabiai_analyze.py --days 30        # analyze + write learned_adjustments
```
- Writes `sabiai_insights` (period summary, calibration, recommendations) and `learned_adjustments` (confidence multipliers per sport/market; `avoid` benches a category).
- `value_bet_finder.py` applies adjustments automatically on every scan (skip with `--no-learn`).
- Wired into `value_bet_daily.sh` after auto-settle.
- **Never bulk-mark long-shot legs as loss when the slip dies** — legs settle individually by real scores via `--auto-settle`, otherwise the learner trains on false data.

---

## 7. Scanner Architecture

- **Odds:** TheRundown API (`RUNDOWN_API_KEY` in `/PATH/TO/.env`) → MLB/WNBA/NHL/NBA/NCAAB covered. Soccer/NFL 403 on current plan. Fallback: ESPN scoreboard (DraftKings lines, free).
- **Models:** MLB = starting-pitcher ERA model; soccer = ClubElo (clubs) + **eloratings.net (all ~318 national teams** — fetched dynamically, covers every friendly/World Cup match); **NFL = nfelo** (`nfl_elo.py`, published Elo + QB adjustments from github.com/greerreNFL/nfelo, refreshed daily in season). Other sports = consensus only (≈0 EV — accumulator filler, not Kelly material).
- **Extra soccer evidence:** `sportsgambler.py` — injury/suspension feed (EPL, La Liga, Serie A, Bundesliga, UCL, World Cup; "ruled out" phrasing triggers the probability penalty); `bettingstats.py` — per-team BTTS/Over%/corners/cards stats for leagues fdco doesn't cover (friendlies, World Cup, minor leagues).
- **In-season filter:** `--sport all` scans only in-season sports for the current month (`SEASON_MONTHS` in value_bet_finder.py). Full scan ~5 min.
- **Sanity filter:** EV > 30% dropped; model/market divergence > 25% dropped.
- **Auto-settle:** ESPN scoreboard → SofaScore fallback. `python3 value_bet_finder.py --auto-settle`

---

## 8. Daily Pipeline (`value_bet_daily.sh`)

Order: DB backup → auto-settle → **learning loop** → record line → scan (band 1.30-2.50, EV 3%+) → filter 🟢🟡 → WhatsApp → (Mondays) long shot.

DB backups: `scripts/backup_bets_db.sh` → `data/backups/bets_YYYYMMDD.db.gz`, 7-day rotation. Suggested cron: `30 5 * * *`.

---

## 9. Dashboard

- URLs: `/` overview · `/picks` · `/betchain` · `/longshot` · `/history` · `/finance` (PIN) · `/diary` · `/strategies` · `/live`
- Restart: `systemctl --user restart sabiai-dashboard`
- **Write auth:** POST endpoints require `X-SabiAI-Key` header. Token: `data/.dashboard_token` (server-generated). Frontend exchanges the PIN via `GET /api/write-key?pin=`. PIN default 1234 (change in production), override with env `SABIAI_PIN`.

---

## 10. Key Rules Hendrix Has Set

1. **Kelly = 1xBet. Chain = SportyBet. Long shot = Bet9ja. Never mix.**
2. Scanner odds are reference only — log real bookmaker odds from screenshots.
3. Chain bet is Hendrix's choice. Never auto-select it from Kelly picks.
4. Long shot is fully automated when asked — script picks the surest legs.
5. A Kelly pick only counts toward the Performance Dashboard when SELECTED (`bets.selected=1`). Unselected model picks are history, not record.
6. Plain English, decimal odds. No "edge/units/sharp/fade".
7. Win → celebrate. Loss → acknowledge cleanly, move on.
8. From week of June 15, 2026: auto-generate the Bet9ja booking code with every weekly long shot.

---

## 11. Database Quick Reference

**Outcome dialects (IMPORTANT — they differ per table):**
- `bets.outcome`: `win` / `loss` / `not_placed` / NULL (pending)
- `accumulators.status`: `won` / `lost` / `pending` / `void`
- `weekly_long_shot.status`: `won` / `lost` / `pending` / `void`
- Week format everywhere: ISO `2026-W24`.

**Tables:** `bets` (all picks; `selected` flag = actually placed), `continuous_bet_state` (chain, id=1), `weekly_long_shot`, `accumulators` + `accumulator_legs`, `bankroll` (money ledger — see §5), `learned_adjustments` + `sabiai_insights` + `calibration` (learning loop), `diary`, `config`, `live_bets`.

**State checks:**
```bash
sqlite3 ~/.openclaw/workspace/data/bets.db \
  "SELECT streak_day, current_stake, streak_status, restrategy_until FROM continuous_bet_state WHERE id=1"
python3 record_pick.py pending
python3 record.py        # one-line W/L + bankroll
```

---

## 12. Odds Discrepancy Protocol

If real-book odds differ from scanner odds (expected — different markets):
- Log the slip odds, not scanner odds.
- If the real odds kill the value (below model threshold), say so — Hendrix decides.
