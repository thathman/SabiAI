# SabiAI V1 — Legacy Operational Reference

> Preserved from the former root `SABIAI.md` during the Sabi Boy V2 rename. This document records V1 architecture and operating behavior for migration, reconciliation and rollback. **Do not assume every runtime detail below is currently healthy or active without live verification.**

## 1. What V1 SabiAI Was

SabiAI V1 was Hendrix's personal betting analyst, with a FastAPI dashboard at `picks.hendrix.com.ng` / `localhost:8090`, Python scripts, and a SQLite database at `~/.openclaw/workspace/data/bets.db`.

`value_bet_daily.sh` was the full daily pipeline: settle → learn → backup → scan → WhatsApp, runnable manually or by cron.

## 2. Three Historical Bet Types

### Kelly Picks

- value picks where model probability beat implied bookmaker price;
- V1 scanner command: `value_bet_finder.py`;
- historical routing: 1xBet;
- scanner surfaced candidates; Hendrix selected what was actually placed.

### Compound Chain

- one compounding ticket/day;
- historical starting stake ₦1,000;
- historical routing: SportyBet;
- state in `continuous_bet_state`;
- loss triggered reset/restrategy behavior.

### Weekly Long Shot

- large weekly accumulator;
- historical routing: Bet9ja;
- `weekly_long_shot.py` plus `bet9ja_book.py` for booking-code creation where browser automation succeeded.

## 3. Historical Bookmaker Routing

| V1 channel | Bookmaker |
|---|---|
| Kelly | 1xBet |
| Live | 1xBet |
| Compound chain | SportyBet |
| Weekly Long Shot | Bet9ja |

Scanner/reference prices were not automatically the same as Nigerian bookmaker slip prices. Actual placed prices should come from the real slip/bookmaker.

## 4. Historical Screenshot Workflow

V1 commonly used screenshots to extract match, pick, price and bookmaker before calling recording scripts such as `record_pick.py` / `record_chain.py`.

This workflow is superseded in V2 by the canonical ticket-normalization path, but old records/scripts must remain understandable during migration.

## 5. V1 Bankroll Ledger

The legacy `bankroll` table recorded settled money events. Dashboard logic derived bankroll from the starting figure plus ledger deltas.

Do not hand-edit historical balances during V2 migration. Reconcile instead.

## 6. V1 Learning Loop

`sabiai_analyze.py` wrote `sabiai_insights` and `learned_adjustments` and the V1 scanner applied those adjustments.

Important historical lesson: do not mark every accumulator leg lost merely because the overall ticket failed; legs must settle from actual results.

## 7. V1 Scanner Architecture

The repository contains historical integrations/references for TheRundown, ESPN, SofaScore, API-Football, ClubElo/national-team Elo, nfelo and additional football evidence scripts.

Repository presence is not proof that a source is currently healthy or enabled.

## 8. V1 Daily Pipeline

Historical order:

1. backup;
2. auto-settle;
3. learning loop;
4. scan;
5. filter;
6. notification;
7. Monday long-shot workflow.

V2 should not simply copy this sequence; V2 adds explicit source/system health, canonical market identity, ticket lineage and controlled learning.

## 9. V1 Dashboard

Historical routes included overview, picks, compound chain, long shot, history, finance, diary, strategies and live.

The old dashboard included a browser PIN/write-key flow. V2 security policy is to remove that write path rather than preserve it.

## 10. Historical Rules Worth Preserving as History

- actual placed bookmaker price matters more than scanner reference price;
- user-selected vs unselected model picks must remain distinguishable;
- chain/long-shot/live/Kelly histories must not be lost;
- plain language and decimal odds are preferred;
- long-shot leg outcomes must be real outcomes, not inferred from ticket death.

Historical bookmaker-routing rules should be preserved in history/migration semantics, but V2 product capabilities are broader and adapter-driven.

## 11. Legacy Database Dialects

Historical tables use different status/outcome vocabularies. V2 migration must map them into canonical outcomes without mutating the originals in place.

Important V1 tables include:

- `bets`;
- `continuous_bet_state`;
- `weekly_long_shot`;
- `accumulators` / `accumulator_legs`;
- `bankroll`;
- `learned_adjustments`;
- `sabiai_insights`;
- `calibration`;
- `diary`;
- `config`;
- `live_bets`.

The legacy `sabiai_v2.db` also contains historical match/upcoming/update data despite its confusing name.

## 12. Migration Rule

This file is for V1 preservation/reconciliation only.

For the canonical V2 product/persona, read:

- `SABI_BOY.md`
- `SOUL.md`
- `OPERATING_MANUAL.md`
- `skills/sabiai_SKILL.md`
- `docs/SABIAI_V2_TASKS.md`
