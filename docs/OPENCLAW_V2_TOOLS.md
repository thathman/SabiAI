# SabiAI V2 — OpenClaw Tool Contract

This document defines the boundary between OpenClaw and the SabiAI V2 domain code.

## Rule

OpenClaw calls a stable Sabi tool contract. Skills orchestrate Sabi; they do not duplicate market, ticket, bankroll, history, source-selection or storage rules and they do not query V2 SQLite directly.

Current bridge:

```bash
python3 scripts/sabiai_v2_tool.py
```

Request:

```json
{"tool":"market.interpret","args":{"text":"X2","home":"Arsenal","away":"Chelsea"}}
```

Response:

```json
{"ok":true,"tool":"market.interpret","data":{...}}
```

## Language contract

Tool output that can reach the user must follow the Sabi language rules:

- decimal odds only;
- explicit team/player names where context exists;
- plain selections such as `Arsenal to win`, `Chelsea or Draw — Double Chance`, `Over 2.5 goals`, `Arsenal +1.5 handicap`;
- no American-facing betting vocabulary in user-facing wording;
- internal technical details stay internal unless explicitly needed for maintenance.

## Implemented tools

### System

- `system.initialize` — initialize/upgrade the separate V2 database.
- `system.health` — V2 database/schema/table health.

### Sports

- `sports.list` — current built-in sport knowledge. The list is explicitly open-ended rather than a coverage wall.
- `sports.describe` — scoring structure, event parts, useful metrics and research topics for a sport. Unknown sports return a discovery profile instead of `unsupported`.

### Research

- `research.plan` — creates a sport- and market-aware research checklist before sources are queried.
- `research.evidence.save` — persist a plain-language evidence item with source/freshness/reliability metadata.
- `research.evidence.list` — read persisted evidence for an event, optionally filtered by evidence type.

Research source access is governed separately by the V2 `SourceService`: cache first, free/public sources first, paid escalation only after free options fail and a reason is supplied.

### Markets and prices

- `market.interpret` — normalize bookmaker/user market wording into explicit Sabi language.
- `market.arbitrage` — compare a complete set of fresh prices after verifying event, market and settlement-rule compatibility; supports two, three or more outcomes and optional stake allocation.

### Bookmakers

- `bookmaker.resolve` — resolve supported bookmaker aliases to stable canonical bookmaker identities.
- `bookmaker.capabilities` — report only capabilities currently proven by a registered integration.

The current compatibility layer recognizes the existing SportyBet and Bet9ja browser builders as ticket-build/booking-code-create integrations only. Import/search/conversion capabilities are not claimed until those paths are implemented and revalidated.

### Ticket intake and normalization

- `ticket.normalize` — normalize already-extracted legs and report ambiguity/duplicate/price issues.
- `ticket.from_text` — import common copied/share text. It is also the deterministic path for text OpenClaw extracts from an X post or screenshot.

`ticket.from_text` never silently discards lines it cannot parse; it returns them in `unparsed_lines` for OpenClaw to resolve.

### Ticket Workshop

- `ticket.split` — split one ticket into a requested number of slips.
- `ticket.split_by_size` — split by games per slip.
- `ticket.trim` — trim toward requested combined decimal odds while respecting locked selections and minimum game count.
- `ticket.remove` — remove selected games by leg ID or explicit event name.
- `ticket.keep` — keep only selected games while preserving locked selections.
- `ticket.change_market` — change one game to another understood market and optional new decimal odds.
- `ticket.replace` — replace one game/selection with another normalized leg.

Ticket responses retain visible event labels such as `Arsenal vs Chelsea`; OpenClaw should not expose draft/internal event IDs as the primary match description.

### Our records/history

- `record.bankroll` — write a signed V2 bankroll ledger event through the domain service.
- `history.summary` — read our own W/L/D/void/pending totals, ticket totals and bankroll.
- `history.by_sport` — read our results grouped by sport.
- `history.by_market` — read our results grouped by market.
- `history.by_bookmaker` — read our results grouped by bookmaker.
- `history.bankroll` — read bankroll balance and ledger history.

These are our records. They are not general sports-site statistics.

## Input flow for screenshots and X posts

The V2 domain does not need its own screenshot reader or X client. OpenClaw already has the right eyes for those inputs.

```text
Screenshot / X post / copied share text
        ↓
OpenClaw reads/extracts visible content
        ↓
ticket.from_text OR ticket.normalize
        ↓
Canonical explicit ticket
        ↓
research.plan / research evidence
        ↓
Ticket Workshop edits
        ↓
Bookmaker adapter / booking code when supported
```

This keeps vision/browser changes outside ticket rules and avoids building one parser per input surface.

## Namespaces still to grow behind this same boundary

- `sports.*` — discovery/fixture/event helpers as free-source adapters arrive.
- `research.*` — source orchestration, form, H2H, injuries, lineups, context and reviewer pass.
- `bookmaker.*` — event/market search, booking-code import/build and conversion adapters.
- `market.*` — broader market mappings, price comparison and movement history.
- `ticket.*` — booking-code import, stronger/lower-risk variants, grouping rules and bookmaker conversion.
- `record.*` — picks/tickets/settlement recording.
- `history.*` — streaks, P/L, strategy and ticket-analysis summaries.
- `blog.*` — Sabi blog publication and retrieval.
- `system.*` — job/source/backup/settlement health.

The namespace list is a contract direction, not a claim that every tool already exists.

## Why one gateway

- one canonical interpretation of events, markets and tickets;
- one place to enforce decimal odds and explicit wording;
- one place to apply free-first source policy;
- one place to protect V2 writes;
- one place to keep dashboard reads separate from active Sabi work;
- easier local testing;
- easier future MCP exposure;
- OpenClaw can change orchestration without changing domain rules.

## Compatibility

V1 scripts remain available during migration. New V2 functionality should prefer this gateway. Any temporary legacy fallback must be explicit and removable once the V2 equivalent exists.
