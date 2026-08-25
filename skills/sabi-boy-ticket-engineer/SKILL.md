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

## Research before quality edits

For requests such as `make this stronger`, `remove weak games`, or `check every game`:

1. `ticket.research.plan`;
2. gather evidence per leg;
3. run `ticket.research.snapshot` / match research where appropriate;
4. use a Skeptic pass when required;
5. only then rank/remove/replace based on actual research.

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

## Market changes

A proposed market change is not complete until the target bookmaker actually offers that exact alternative at a current decimal price.

Never invent replacement odds.

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
