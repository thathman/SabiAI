---
name: sabi-boy-ticket-engineer
description: Restore, normalize, research, edit, split, trim, convert, rebuild, and verify betting tickets without changing selections silently.
---

# Sabi Boy Ticket Engineer

Use for booking codes, screenshots, X posts, copied tickets, plain instructions, ticket edits and bookmaker conversions.

## Intake

Supported inputs may include:

- booking code;
- screenshot/image read by OpenClaw vision;
- X post/link read by OpenClaw;
- copied/share text;
- plain instruction;
- existing Sabi Boy draft.

Normalize everything before editing. Keep sport, visible event, exact selection, decimal odds, source and lineage.

If the input is ambiguous, preserve the ambiguity instead of guessing.

Most Ticket Workshop operations accept `draft_id` directly. Prefer that over manually unpacking/repacking a saved draft.

## Research before quality edits

For requests such as `make this stronger`, `remove weak games`, or `check every game`:

1. query `research.scan.context` when the leg came from the daily scan, so the exact event/source/observed price is carried forward;
2. `ticket.research.plan`;
3. create/reuse durable research cases when appropriate;
4. gather evidence per leg;
5. run `ticket.research.snapshot` / match research where appropriate;
6. use a Skeptic pass when required;
7. only then rank/remove/replace based on actual research.

Do not create a fake strength score from bookmaker odds alone.

## Editing tools

Use the canonical V2 Ticket Workshop tools for:

- remove/keep;
- replace;
- change market;
- split into N slips;
- split by games per slip;
- trim toward target combined odds;
- strongest-N from supplied research ranking;
- lower-risk market-change planning;
- draft save/revise/get/recent/lineage.

Locked selections remain protected unless the user explicitly changes them.

## Candidate versions

Use `ticket.candidates.compare` when the user wants multiple ticket versions compared. It reports structural/odds differences without pretending the highest combined odds is automatically the best choice.

Use `ticket.higher_odds.from_verified_offers` only when OpenClaw has just observed exact replacement offers at the target bookmaker. Every replacement needs the exact `leg_id`, market and fresh decimal price.

Never invent replacement odds or silently strengthen a market line.

## Market changes

A proposed market change is not complete until the target bookmaker actually offers that exact alternative at a current decimal price.

Use `market.settlement.profile` when the new market can be affected by overtime, retirement, dead heat, forfeits or event-format rules.

## Conversion/rebuild

Load `sabi-boy-bookmaker-workflows` when moving a ticket across bookmakers or creating a booking code.

Conversion must preserve exact event/market/line/period meaning. Generated codes must be restored and verified before being called successful.

## Explain changes

When material, tell the user plainly:

- which games were removed;
- which markets changed;
- why;
- old combined odds;
- new combined odds based on actual current prices when available.

Avoid technical model language.

## Lineage

Never overwrite the original silently. Preserve:

`original → edit(s) → conversion → built code → verified-built code`
