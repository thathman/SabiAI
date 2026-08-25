# TOOLS.md — Sabi Boy Runtime Notes

This file records Sabi Boy-specific runtime/tool locations and operational conventions. Tool behavior belongs in skills/domain code; secrets do not belong here.

## Identity / Compatibility

- Human-facing name: **Sabi Boy**
- Technical repo/package compatibility: `SabiAI` / `sabiai`
- AI Spine agent ID: `sabi-ai`
- Matrix identity currently remains the existing SabiAI account until infrastructure is deliberately renamed.

## Primary Runtime

- OpenClaw workspace: `~/.openclaw/workspace/`
- OpenClaw config: `~/.openclaw/openclaw.json`
- Primary machine: Dell / Ubuntu
- Remote shell convention: `ssh dell` / configured local alias
- Secrets: server-side environment/config only; never copy secret values into repo docs, AI Spine or logs.

## V2 Domain Gateway

Preferred bridge for canonical V2 behavior:

```bash
python3 ~/.openclaw/workspace/scripts/sabiai_v2_tool.py
```

The gateway is the boundary for sports profiles, market interpretation, ticket normalization/editing, bookmaker capability resolution, bankroll/history and future V2 operations.

Do not bypass it with ad hoc SQLite writes when a domain operation exists.

## Databases

### V2 development database

Default:

`~/.openclaw/workspace/data/sabiai_v2_core.db`

This remains separate during migration.

### V1 legacy database

`~/.openclaw/workspace/data/bets.db`

Treat as authoritative legacy history until reconciliation passes.

### Legacy football-oriented database

`~/.openclaw/workspace/data/sabiai_v2.db`

Despite the name, this is a legacy store, not the canonical new V2 database.

## Preservation / Rollback

V1 preservation utility:

```bash
python3 scripts/v2_preserve.py --label before-v2-migration
```

Verify a snapshot before rehearsal/restore. Never use a live V1 database as migration scratch space.

## Current V2 Tool Surface

### System

- `system.initialize`
- `system.health`

### Sports / research

- `sports.list`
- `sports.describe`
- `research.plan`
- `research.evidence.save`
- `research.evidence.list`

### Markets / prices

- `market.interpret`
- `market.arbitrage`

### Bookmakers

- `bookmaker.resolve`
- `bookmaker.capabilities`

### Tickets

- `ticket.normalize`
- `ticket.from_text`
- `ticket.split`
- `ticket.split_by_size`
- `ticket.trim`
- `ticket.remove`
- `ticket.keep`
- `ticket.change_market`
- `ticket.replace`

### Our records

- `record.bankroll`
- `history.summary`
- `history.by_sport`
- `history.by_market`
- `history.by_bookmaker`
- `history.bankroll`

Check `docs/OPENCLAW_V2_TOOLS.md` and `docs/SABIAI_V2_TASKS.md` before assuming newer capabilities are live.

## Ticket Intake

Preferred flow:

```text
Screenshot / X post / copied text
      ↓
OpenClaw reads visible content
      ↓
ticket.from_text / ticket.normalize
      ↓
canonical ticket
      ↓
research / edit / split / trim / replace
      ↓
bookmaker adapter when verified
```

Do not create separate market logic for each input surface.

## Bookmaker Runtime

Canonical V2 bookmaker identities currently include:

- SportyBet
- Bet9ja
- 1xBet
- Stake

Existing V1 browser scripts demonstrate some SportyBet/Bet9ja ticket-build/booking-code behavior. Treat these as compatibility implementations until the V2 adapter verifies capability end-to-end.

Do not infer event search, market search, code import or conversion from name recognition alone.

## Sources / Research

Sabi Boy follows free-first source selection:

1. cache/local data;
2. open/public data;
3. official source;
4. public structured endpoint;
5. public web;
6. OpenClaw browser;
7. web/search discovery;
8. other free source;
9. paid API only when justified.

Historical repository source code includes integrations/references for SofaScore, ESPN, API-Football, TheRundown, sport-specific football sources and bookmaker scraping. Repository presence does not prove runtime health.

## Browser / Search

Use OpenClaw's browser/search capabilities for:

- bookmaker pages when an adapter needs browser fallback;
- official/public sports research;
- screenshot/X-post extraction/orchestration;
- discovery of unfamiliar sports, competitions and data sources.

Structured/cached sources are preferable when they provide reliable equivalent data.

## AI Spine

Read Sabi Boy inbox:

```bash
AI_AGENT=sabi-ai ~/ai-spine/scripts/ai-bus read
```

Search memory:

```bash
~/ai-spine/scripts/ai-mem ask "<question>"
~/ai-spine/scripts/ai-mem find "<query>"
```

Send durable handoff:

```bash
~/ai-spine/scripts/ai-bus send <agent> "<message>"
```

Never store secrets in AI Spine.

## Dashboard

Historical service:

- local: `localhost:8090`
- public deployment historically: `picks.hendrix.com.ng`

V2 dashboard policy is **read-only**. It should eventually display our history/performance/risk/system state rather than become a sports-discovery website.

Do not carry the legacy browser PIN/write-token design into V2.

## Messaging / Delivery

When OpenClaw delivery is needed, use the configured OpenClaw message tooling/channel rather than resurrecting deprecated local HTTP bridges.

Do not send public/external messages unless the user requested/approved that external action.

## Development / Test Policy

- Test locally/controlled runtime.
- Do not depend on GitHub Actions for normal Sabi development.
- Keep the living task board updated.
- Preserve V1 and keep migration reversible.
- A committed file is not proof of a passing runtime test.

## Important References

- `SABI_BOY.md` — canonical product/system reference
- `SOUL.md` — reasoning/behavior philosophy
- `OPERATING_MANUAL.md` — decision/risk discipline
- `AGENTS.md` — workspace/memory/coordination
- `skills/sabiai_SKILL.md` — OpenClaw skill
- `docs/OPENCLAW_V2_TOOLS.md` — gateway contract
- `docs/SABIAI_V2_TASKS.md` — implementation truth
- `docs/SABIAI_V1_REFERENCE.md` — preserved legacy behavior
