# SabiAI V2 — V1 Preservation Audit

> Status: repository inventory complete; live-runtime verification on the Dell is still required before migration.

This audit records the V1 surfaces that V2 must preserve. It is intentionally conservative: repository presence does not prove that a job/source is currently healthy or enabled in production.

## 1. Legacy databases

### `bets.db`

Repository schema shows these V1 tables:

- `bets`
- `bankroll`
- `predictions`
- `calibration`
- `meta`
- `config`
- `diary`
- `accumulators`
- `accumulator_legs`
- `continuous_bet_state`
- `sabiai_insights`
- `weekly_long_shot`
- `learned_adjustments`
- `live_bets`

This database contains the historical record that must reconcile before V2 promotion.

### legacy `sabiai_v2.db`

Repository schema shows:

- `matches`
- `upcoming`
- `update_log`

Despite its name, this is a legacy football-oriented data store and is not the new canonical V2 database.

### New V2 development database

V2 code uses `sabiai_v2_core.db` by default. It is deliberately separate while migration is being built and verified.

## 2. Major legacy scripts

The repository currently contains production/history code for:

- value scanning and filtering: `value_bet_finder.py`, `value_engine.py`, `filter_high_conf.py`, `dc_value_finder.py`;
- historical testing/analysis: `backtest.py`, `backtest_rolling.py`, `backtester.py`, `fast_backtest.py`, `sabiai_analyze.py`;
- data: `data_pipeline.py`, `sabiai_scraper.py`, `sofascore.py`, `apifootball.py`, `espn_odds.py`, `bettingstats.py`, `sportsgambler.py`, `sportsbook.py`, `sportybet_odds.py`;
- bookmaker/ticket paths: `bet9ja_book.py`, `sportybet_book.py`, `record_accumulator.py`, `record_chain.py`, `record_pick.py`;
- strategy/history: `continuous_bet.py`, `weekly_long_shot.py`, `live_bets.py`, `bet_history.py`, `money.py`;
- dashboard data: `sabiai_data.py`;
- diary/blog predecessor: `diary_auto.py`, `diary_save.py`;
- backup: `backup_bets_db.sh`.

Two especially large V1 files confirm why V2 is being separated into domains rather than extending monoliths: `value_bet_finder.py` is over 200 KB and `dashboard/app.py` is over 110 KB in the current repository tree.

## 3. OpenClaw skills

Current repository skills:

- `sabiai_SKILL.md`
- `sabiai-onboarding_SKILL.md`
- `value-bet-scanner_SKILL.md`
- `sportybet-researcher_SKILL.md`
- `betting-record_SKILL.md`
- `money_SKILL.md`

V2 rewrites the primary Sabi skill while retaining legacy skills until their functions have equivalent V2 tools.

## 4. Scheduled/runtime surfaces

Repository documentation contains OpenClaw cron definitions for at least:

- Weekly Value Bet Scanner;
- Daily Sports Value Picks.

The repository also contains `systemd/sabiai-dashboard.service`, serving the FastAPI dashboard on loopback port 8090.

Live `openclaw cron list`, user/system crontabs and systemd state must be inspected on the Dell before migration; repository docs can be stale.

## 5. Dashboard surfaces to preserve

V1 dashboard history includes overview, picks/games, compound chain, long shot, history, finance, diary, strategies and live views plus read APIs used by the UI.

V2 may redesign the code and presentation, but historical totals and strategy meaning must survive. The V2 dashboard remains read-only.

The old browser write-token/PIN flow is not a V2 feature and must be removed rather than migrated.

## 6. Data/source integrations found in repository

The codebase contains adapters/integrations for or references to:

- SofaScore;
- ESPN;
- API-Football;
- football/statistics pages;
- SportyBet;
- Bet9ja;
- 1xBet/reference odds;
- RapidAPI sportsbook/odds feeds;
- research/search tools referenced by OpenClaw skills.

V2 does not assume these are all healthy. Each source must enter the V2 Source Registry with cost, capability, freshness and health metadata.

## 7. Bookmaker integrations found

Known V1 bookmaker paths include:

- SportyBet;
- Bet9ja;
- 1xBet;
- external/reference sportsbook feeds.

Stake is a V2 target for import/conversion support. A bookmaker is not marked capable of code import/build until an adapter and fixture prove it.

## 8. Strategy/history semantics that must survive

At minimum:

- ordinary/single picks;
- Kelly historical channel;
- Compound/continuous chain history and state;
- Weekly Long Shot history;
- Live history;
- accumulator/ticket history;
- selected/unselected history where historically meaningful;
- bankroll ledger/history;
- closing odds/CLV fields where present;
- learned adjustments/insights as historical evidence, even if V2 learning architecture changes.

## 9. Configuration and secrets

V1 repository files contain configuration placeholders and environment-variable references. V2 policy is:

- no new secrets in source;
- new code reads secrets server-side from environment/configuration;
- preservation manifests contain paths/hashes only, never secret values;
- live environment variables/config files must be inventoried on the Dell without copying secret values into Git.

## 10. V1 → V2 mapping direction

| V1 | V2 destination |
|---|---|
| `bets` | canonical event + market + selection + `picks_v2` |
| `predictions` | historical prediction/pick evidence during migration |
| `bankroll` | `bankroll_ledger` |
| `accumulators` + legs | `tickets` + `ticket_legs` |
| `continuous_bet_state` | strategy state/history layer |
| `weekly_long_shot` | strategy-tagged ticket/history records |
| `live_bets` | strategy-tagged picks/history records |
| `diary` | `blog_posts` migration with diary category |
| `matches` / `upcoming` | canonical events plus sport-specific historical data adapters |
| learned adjustments / insights | preserved historical insight records; new learning logic remains separate |

This is a mapping direction, not permission to migrate yet. Field-by-field migration and reconciliation checks still need implementation.

## 11. Live-runtime checks still required

Before any migration rehearsal on the Dell:

1. locate actual DB files and sizes;
2. run SQLite integrity/quick checks;
3. create a V1 preservation snapshot;
4. enumerate live OpenClaw crons and systemd jobs;
5. enumerate actual database table counts;
6. record current bankroll and historical totals from the existing dashboard/data layer;
7. identify every writer to `bets.db`;
8. confirm backup/restore permissions;
9. verify no V2 job points at the V1 database accidentally.

Until those checks pass, V1 remains the authoritative production record.
