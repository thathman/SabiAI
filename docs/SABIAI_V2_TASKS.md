# SabiAI V2 — Living Task Board

> **Branch:** `v2`  
> **Rule:** Update this file as implementation progresses. Do not mark a phase complete until its exit gate in `SABIAI_V2_BUILD_PLAN.md` passes.

## Status key

- [ ] Not started
- [~] In progress
- [x] Complete
- [!] Blocked / decision needed

---

# Phase 0 — Audit / Preserve V1

- [ ] Inventory scripts
- [ ] Inventory OpenClaw skills/tools
- [ ] Inventory cron/systemd jobs
- [ ] Inventory DBs/tables
- [ ] Inventory dashboard routes/APIs
- [ ] Inventory data sources
- [ ] Inventory bookmaker integrations
- [ ] Inventory strategies
- [ ] Inventory secrets/config
- [ ] Map V1 -> V2 schema
- [ ] Backup all V1 data
- [ ] Create migration fixture
- [ ] Document rollback

# Phase 1 — Core Domain

- [ ] Create V2 package layout
- [ ] Shared configuration
- [ ] Canonical sport model
- [ ] Competition model
- [ ] Team/player/participant model
- [ ] Alias resolution
- [ ] Canonical event model
- [ ] Canonical market/selection model
- [ ] Bookmaker registry
- [ ] Pick model
- [ ] Ticket model
- [ ] Ticket leg model
- [ ] Bankroll ledger service
- [ ] Shared repository/data layer
- [ ] V2 schema
- [ ] Migration framework
- [ ] Core tests

# Phase 2 — OpenClaw Native Sabi

- [ ] Rewrite Sabi V2 skill
- [ ] Plain-language doctrine
- [ ] Decimal odds doctrine
- [ ] Explicit team/selection wording
- [ ] Free-first doctrine
- [ ] Broad-sports doctrine
- [ ] Read-only dashboard boundary
- [ ] Native `sports.*` tools
- [ ] Native `research.*` tools
- [ ] Native `bookmaker.*` tools
- [ ] Native `market.*` tools
- [ ] Native `ticket.*` tools
- [ ] Native `record.*` / `history.*` tools
- [ ] Native `blog.*` tools
- [ ] Native `system.*` tools
- [ ] AI Spine memory integration
- [ ] Temporary specialist-worker pattern
- [ ] Skeptic/reviewer worker
- [ ] Heartbeat/scheduler review

# Phase 3 — Free-First Sources

- [ ] Source Registry
- [ ] Cache/freshness engine
- [ ] Official-source adapters
- [ ] Public endpoint adapters
- [ ] Public web adapters
- [ ] Browser fallback
- [ ] Search fallback
- [ ] Source discovery
- [ ] Source health
- [ ] Paid API gate
- [ ] Paid usage log
- [ ] Duplicate-request prevention
- [ ] Source fallback tests

# Phase 4 — Sports Framework

## First wave
- [ ] Football
- [ ] Basketball
- [ ] Volleyball
- [ ] Tennis
- [ ] Table tennis
- [ ] Baseball
- [ ] Ice hockey
- [ ] Cricket
- [ ] Esports
- [ ] Golf

## Second wave
- [ ] Handball
- [ ] Rugby
- [ ] Darts
- [ ] Snooker
- [ ] Badminton
- [ ] MMA
- [ ] Boxing
- [ ] Motorsport
- [ ] Cycling
- [ ] Futsal
- [ ] Water polo
- [ ] Beach volleyball
- [ ] Padel
- [ ] Floorball
- [ ] Aussie rules

# Phase 5 — Market Interpreter

- [ ] Match win/draw/loss
- [ ] Double chance
- [ ] Handicap
- [ ] Totals
- [ ] Team totals
- [ ] Set/frame/map markets
- [ ] Corners
- [ ] Cards
- [ ] Shots / shots on target
- [ ] Player markets
- [ ] General count markets
- [ ] Race/field markets
- [ ] Period/scope support
- [ ] Overtime/extra-time rules
- [ ] Bookmaker label mappings
- [ ] Ambiguity detection
- [ ] Real market-name test corpus

# Phase 6 — Research V2

- [ ] Research request/orchestration
- [ ] Sport-specific checklist selection
- [ ] Market-specific checklist selection
- [ ] Recent form
- [ ] Home/away form
- [ ] H2H
- [ ] Injuries/availability
- [ ] Expected lineups/rosters
- [ ] Schedule/rest
- [ ] Match/competition context
- [ ] Market-specific stats
- [ ] Evidence persistence
- [ ] Evidence reuse
- [ ] Conflicting source handling
- [ ] Plain-language summaries
- [ ] Reviewer pass

# Phase 7 — Bookmakers

- [ ] Bookmaker adapter base
- [ ] Capability flags
- [ ] SportyBet adapter
- [ ] Bet9ja adapter
- [ ] 1xBet adapter
- [ ] Stake adapter
- [ ] Event search
- [ ] Market search
- [ ] Decimal odds extraction
- [ ] Booking-code import
- [ ] Booking-code creation where possible
- [ ] Slip parsing
- [ ] Bookmaker rule metadata
- [ ] Browser fallback
- [ ] Adapter fixtures/tests

# Phase 8 — Ticket Workshop

## Inputs
- [ ] Booking code
- [ ] Screenshot/image
- [ ] Copied text
- [ ] Bookmaker share text
- [ ] X post
- [ ] Plain instruction

## Normalize
- [ ] Resolve bookmaker
- [ ] Resolve events
- [ ] Resolve home/away
- [ ] Normalize markets
- [ ] Normalize odds
- [ ] Resolve duplicate legs
- [ ] Flag unresolved legs

## Edit
- [ ] Remove games
- [ ] Replace games
- [ ] Change markets
- [ ] Preserve locked picks
- [ ] Keep strongest N
- [ ] Lower-risk version
- [ ] Higher-odds version

## Split
- [ ] Split by number of slips
- [ ] Split by game count
- [ ] Distribute stronger picks
- [ ] Preserve groups

## Target odds
- [ ] Trim toward requested odds
- [ ] Minimum-game constraint
- [ ] Locked-pick constraint
- [ ] Compare candidate versions

## Lineage
- [ ] Ticket versions
- [ ] Parent/child split tracking
- [ ] Original vs edited tracking
- [ ] Sabi recommendation notes

# Phase 9 — Convert / Rebuild / Booking Codes

- [ ] Source-book import
- [ ] Target-book event mapping
- [ ] Equivalent-market mapping
- [ ] Missing-market alternatives
- [ ] Target-book odds
- [ ] Build target slip
- [ ] Create/extract booking code
- [ ] Verify rebuilt ticket
- [ ] Conversion history
- [ ] First end-to-end conversion pair

# Phase 10 — Odds Comparison / Arbitrage

- [ ] Odds snapshots
- [ ] Price timestamps
- [ ] Best price comparison
- [ ] Stale-price detection
- [ ] Two-outcome calculation
- [ ] Three-outcome calculation
- [ ] N-outcome calculation
- [ ] Settlement-rule compatibility check
- [ ] Stake split calculation
- [ ] Price recheck before result
- [ ] False-match rejection tests
- [ ] Opportunity history

# Phase 11 — Settlement / History Reliability

- [ ] Unified settlement service
- [ ] Sport-aware result mapping
- [ ] Won/Lost/Draw/Void/Pending
- [ ] Ticket settlement
- [ ] Postponed/cancelled handling
- [ ] Manual correction + audit
- [ ] Backlog monitoring
- [ ] Duplicate settlement protection
- [ ] Bankroll reconciliation
- [ ] Consistency checks

# Phase 12 — Historical Insights

- [ ] Overall W/L/D
- [ ] Win percentage
- [ ] P/L
- [ ] Bankroll change
- [ ] Current streak
- [ ] Best/worst streak
- [ ] By sport
- [ ] By competition
- [ ] By market
- [ ] By bookmaker
- [ ] By strategy
- [ ] By decimal-odds range
- [ ] By ticket size
- [ ] By combined-odds range
- [ ] Singles vs tickets
- [ ] Ticket killers
- [ ] Original vs edited tickets
- [ ] Ticket source/type

# Phase 13 — Read-Only Dashboard

- [ ] Refactor monolithic dashboard app
- [ ] Overview
- [ ] Games/Picks
- [ ] Tickets
- [ ] Performance
- [ ] Finance
- [ ] Strategies
- [ ] History
- [ ] Blog
- [ ] System
- [ ] Bankroll chart
- [ ] P/L chart
- [ ] W/L/D trend
- [ ] Streak chart
- [ ] Sport chart
- [ ] Market chart
- [ ] Bookmaker chart
- [ ] Strategy chart
- [ ] Odds-band chart
- [ ] Ticket-size chart
- [ ] Combined-odds chart
- [ ] Ticket-killer chart
- [ ] Remove browser write-token flow
- [ ] Read-only APIs
- [ ] Mobile/PWA regression

# Phase 14 — Sabi Blog

- [ ] Blog schema
- [ ] Diary migration
- [ ] Categories/tags
- [ ] Publication service
- [ ] OpenClaw blog tool
- [ ] Daily reflection workflow
- [ ] Weekly reflection workflow
- [ ] Event-driven posts
- [ ] Related picks/tickets
- [ ] Blog index
- [ ] Post page
- [ ] Related posts
- [ ] RSS/Atom if practical

# Phase 15 — Reliability / Security / Operations

- [ ] Job registry
- [ ] Retry/failure tracking
- [ ] Settlement backlog health
- [ ] Source freshness health
- [ ] Backup freshness
- [ ] DB integrity checks
- [ ] Remove default PIN
- [ ] Remove PIN-in-GET flow
- [ ] Remove browser localStorage write key
- [ ] Protect internal writes
- [ ] Server-side secrets only
- [ ] Automated backups
- [ ] Restore test
- [ ] Source health metrics
- [ ] Bookmaker adapter health
- [ ] Paid API usage metrics
- [ ] Cache metrics

# Phase 16 — V2 Release

- [ ] Full V1 -> V2 migration rehearsal
- [ ] Historical totals reconcile
- [ ] Bankroll reconciles
- [ ] Strategy history reconciles
- [ ] End-to-end OpenClaw acceptance tests
- [ ] Ticket Workshop acceptance tests
- [ ] Bookmaker conversion acceptance tests
- [ ] Multi-sport acceptance tests
- [ ] Dashboard acceptance tests
- [ ] Blog acceptance tests
- [ ] Backup/restore acceptance test
- [ ] Security review
- [ ] Local full test suite passes
- [ ] Deployment runbook complete
- [ ] Release notes complete
- [ ] Final V2 acceptance review
- [ ] Promote `v2` to `main`
