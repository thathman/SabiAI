# Betting Record — Sabi Boy V2 Compatibility Skill

This filename is retained for older OpenClaw references. V2 records live in the canonical Sabi Boy database and services, not a separate JSON expense-tracker file.

## Purpose

Use this skill when the user reports:

- a pick/ticket they actually used;
- stake or payout information;
- a Win / Lose / Draw / Void result;
- a correction to a previous result;
- a bankroll deposit/withdrawal/adjustment;
- a request for our history, streaks or performance.

## Rules

- decimal odds only;
- preserve the explicit event and selection;
- preserve bookmaker and strategy where known;
- do not duplicate records when the same result is reported twice;
- settlement corrections require a reason and audit trail;
- bankroll changes go through the V2 ledger;
- ticket outcomes derive from leg outcomes;
- the dashboard only reads these records; it does not write them.

## V2 tools

Query `system.tools` for current capability truth.

Relevant namespaces include:

- `record.*`
- `history.*`
- `settlement.*`
- `ticket.draft.*`

Use the unified settlement service rather than directly editing outcome fields.

## Outcome vocabulary

Use:

- Won
- Lost
- Draw
- Void
- Pending

Translate old `win/loss` data into the canonical V2 values internally while keeping user-facing wording simple.

## History

Our history can be viewed by:

- overall record;
- sport;
- competition;
- market;
- bookmaker;
- strategy;
- decimal-odds range;
- ticket size;
- combined-odds range;
- streak;
- ticket source;
- ticket killers;
- bankroll and betting P/L.

Do not present generic sports statistics from this skill. These are **our records**.
