# Sabi Boy V2 — OpenClaw Tool Contract

This document defines the boundary between OpenClaw and the Sabi Boy V2 domain code.

`SabiAI`/`sabiai` remain compatibility identifiers in filenames, package names and environment variables during the V2 migration. The human-facing agent is **Sabi Boy**.

## Rule

OpenClaw calls a stable Sabi Boy tool contract. Skills orchestrate Sabi Boy; they do not duplicate market, ticket, bankroll, history, source-selection or storage rules and they do not query V2 SQLite directly.

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

Tool output that can reach the user must follow Sabi Boy's language rules:

- decimal odds only;
- explicit team/player names where context exists;
- explicit sport/event context where ambiguity is possible;
- plain selections such as `Arsenal to win`, `Chelsea or Draw — Double Chance`, `Over 2.5 goals`, `Arsenal +1.5 handicap`;
- no American-facing betting vocabulary in normal replies;
- internal implementation/model terminology stays internal unless explicitly needed for maintenance.

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

- `market.interpret` — normalize bookmaker/user market wording into explicit Sabi Boy language.
- `market.arbitrage` — compare a complete set of fresh prices after verifying event, market and settlement-rule compatibility; supports two, three or more outcomes and optional stake allocation.

### Bookmakers

- `bookmaker.resolve` — resolve bookmaker aliases to stable canonical identities.
- `bookmaker.capabilities` — report only capabilities currently proven by a registered integration.
- `bookmaker.booking_code.import_plan` — validate a booking-code request and return the correct import route. Until a direct importer is proven, the route is the controlled OpenClaw browser: load the public slip, extract every leg, do not place a wager, then call `ticket.normalize`.
- `bookmaker.convert.plan` — map a normalized source ticket against target-book offers. Conversion is ready only when every leg has an exact verified equivalent event/market/line/period/side.
- `bookmaker.build.plan` — turn a normalized target ticket into the structured payload expected by a proven bookmaker builder.
- `bookmaker.build.execute` — execute only the allow-listed SportyBet/Bet9ja ticket-builder command from `SABIAI_REPO_ROOT`, capture its result and return the booking code when verified.

The compatibility layer currently recognizes the existing SportyBet and Bet9ja browser builders as ticket-build/booking-code-create integrations. Stake and 1xBet remain known bookmakers but do not falsely advertise builder capabilities until a verified adapter exists.

### Booking-code flow

A booking code is not treated as magic text. The workflow is explicit:

```text
booking code + bookmaker
        ↓
bookmaker.booking_code.import_plan
        ↓
OpenClaw/browser restores the public slip
        ↓
extract sport + event + home/away + market + selection + decimal odds
        ↓
ticket.normalize
        ↓
research / edit / split / trim if requested
        ↓
find target-book offers
        ↓
bookmaker.convert.plan
        ↓
exact equivalents only
        ↓
bookmaker.build.plan
        ↓
bookmaker.build.execute (where proven)
        ↓
verified booking code
```

A similarly named market is not enough. Different line, period, participant, overtime treatment or settlement meaning must remain unresolved until explicitly handled.

### Ticket intake and normalization

- `ticket.normalize` — normalize already-extracted legs and report ambiguity/duplicate/price issues.
- `ticket.from_text` — import common copied/share text. It is also the deterministic path for text OpenClaw extracts from an X post or screenshot.

Ticket legs retain sport context as well as visible event names so cross-sport bookmaker rebuilding does not depend on guesswork.

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

### Unresolved ticket drafts

V2 has a separate `ticket_drafts` store for imported/edited/conversion work that is not yet resolved into canonical events. This avoids inserting fake event IDs into the canonical ticket history.

Drafts preserve:

- original source type/reference;
- source bookmaker;
- target bookmaker when converting;
- normalized payload;
- issues/unresolved legs;
- parent/child revision lineage.

Once event identity and settlement data are canonical, final records can move into the normal ticket/history model.

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
Canonical explicit ticket/draft
        ↓
research.plan / research evidence
        ↓
Ticket Workshop edits
        ↓
conversion / bookmaker build when requested
```

This keeps vision/browser changes outside ticket rules and avoids building one parser per input surface.

## Bookmaker builder isolation

`bookmaker.build.execute` is deliberately narrow:

- no shell execution;
- only explicitly allow-listed scripts;
- only from the configured repository root;
- structured leg JSON only;
- no stake/payment submission;
- builder result must contain a verifiable booking code before success is claimed;
- dry-run placeholders are never treated as real codes.

## Namespaces still to grow behind this same boundary

- `sports.*` — discovery/fixture/event helpers as free-source adapters arrive.
- `research.*` — source orchestration, form, H2H, injuries, lineups, context, synthesis and reviewer pass.
- `bookmaker.*` — direct booking-code import, event/market discovery and additional verified bookmaker adapters.
- `market.*` — broader market mappings, price comparison and movement history.
- `ticket.*` — strength-ranked variants, grouping rules and richer conversion alternatives.
- `record.*` — picks/tickets/settlement recording.
- `history.*` — streaks, P/L, strategy and ticket-analysis summaries.
- `blog.*` — Sabi Boy blog publication and retrieval.
- `system.*` — job/source/backup/settlement health.

The namespace list is a contract direction, not a claim that every tool already exists.

## Why one gateway

- one canonical interpretation of events, markets and tickets;
- one place to enforce decimal odds and explicit wording;
- one place to apply free-first source policy;
- one place to protect V2 writes;
- one place to keep dashboard reads separate from active Sabi Boy work;
- one place to prevent unsafe/silent bookmaker market substitutions;
- easier local testing;
- easier future MCP exposure;
- OpenClaw can change orchestration without changing domain rules.

## Compatibility

V1 scripts remain available during migration. New V2 functionality should prefer this gateway. Any temporary legacy fallback must be explicit and removable once the V2 equivalent exists.
