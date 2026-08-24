# SabiAI V2 — Living Task Board

> **Branch:** `v2`  
> **Rule:** Update this file as implementation progresses. Do not mark a phase complete until its exit gate in `SABIAI_V2_BUILD_PLAN.md` passes.

## Status key

- [ ] Not started
- [~] In progress / implementation exists but its phase gate has not passed
- [x] Complete at task level
- [!] Blocked / decision needed

---

# Phase 0 — Audit / Preserve V1

- [x] Inventory scripts
- [x] Inventory OpenClaw skills/tools
- [x] Inventory repository cron/systemd definitions
- [x] Inventory repository DBs/tables
- [x] Inventory dashboard routes/APIs
- [x] Inventory repository data sources
- [x] Inventory repository bookmaker integrations
- [x] Inventory strategies/history surfaces
- [~] Inventory live secrets/config — repository policy mapped; actual Dell environment still requires secret-free runtime inventory
- [~] Map V1 -> V2 schema — top-level mapping documented; field-level migration mapping remains
- [~] Backup all V1 data — verified snapshot tooling implemented; live Dell snapshot not yet executed
- [ ] Create migration fixture
- [x] Document rollback

# Phase 1 — Core Domain

- [x] Create V2 package layout
- [x] Shared configuration
- [x] Canonical sport model
- [x] Competition model
- [x] Team/player/participant model
- [x] Alias resolution
- [x] Canonical event model
- [x] Canonical market/selection model
- [x] Bookmaker registry
- [x] Pick model
- [x] Ticket model
- [x] Ticket leg model
- [ ] Bankroll ledger service — schema exists; service behavior/reconciliation still required
- [~] Shared repository/data layer — V2 SQLite repository started
- [x] V2 schema
- [~] Migration framework — preservation/rollback foundation exists; data migration not implemented
- [~] Core tests — test suite committed; full execution on controlled runtime remains a gate

# Phase 2 — OpenClaw Native Sabi

- [x] Rewrite Sabi V2 skill
- [x] Plain-language doctrine
- [x] Decimal odds doctrine
- [x] Explicit team/selection wording
- [x] Free-first doctrine
- [x] Broad-sports doctrine
- [x] Read-only dashboard boundary
- [ ] Native `sports.*` tools
- [ ] Native `research.*` tools
- [~] Native `bookmaker.*` tools — canonical bookmaker resolution implemented
- [~] Native `market.*` tools — market interpreter implemented; wider market coverage remains
- [~] Native `ticket.*` tools — split/trim gateway implemented; full workshop remains
- [ ] Native `record.*` / `history.*` tools
- [ ] Native `blog.*` tools
- [~] Native `system.*` tools — V2 system/database health implemented
- [~] AI Spine memory integration — existing agent integration retained; V2 research-memory conventions added to runtime doctrine
- [ ] Temporary specialist-worker pattern
- [ ] Skeptic/reviewer worker
- [~] Heartbeat/scheduler review — V2 heartbeat doctrine written; legacy schedules still require live review/migration

# Phase 3 — Free-First Sources

- [x] Source Registry core
- [ ] Cache/freshness engine
- [ ] Official-source adapters
- [ ] Public endpoint adapters
- [ ] Public web adapters
- [ ] Browser fallback
- [ ] Search fallback
- [ ] Source discovery
- [ ] Source health
- [x] Paid API gate core
- [~] Paid usage log — schema exists; request service still required
- [ ] Duplicate-request prevention
- [~] Source fallback tests — test cases committed; controlled-runtime execution remains

# Phase 4 — Sports Framework

## First wave
- [~] Football — generic canonical sport support only; dedicated research adapter not complete
- [~] Basketball — generic canonical sport support only
- [~] Volleyball — generic canonical sport support only
- [~] Tennis — generic canonical sport support only
- [~] Table tennis — generic canonical sport support only
- [~] Baseball — generic canonical sport support only
- [~] Ice hockey — generic canonical sport support only
- [~] Cricket — generic canonical sport support only
- [~] Esports — generic canonical sport support only
- [~] Golf — generic canonical sport support only

## Second wave
- [~] Handball — generic canonical sport support only
- [~] Rugby — generic canonical sport support only
- [~] Darts — generic canonical sport support only
- [~] Snooker — generic canonical sport support only
- [~] Badminton — generic canonical sport support only
- [~] MMA — generic canonical sport support only
- [~] Boxing — generic canonical sport support only
- [~] Motorsport — generic canonical sport support only
- [~] Cycling — generic canonical sport support only
- [~] Futsal — generic canonical sport support only
- [~] Water polo — generic canonical sport support only
- [~] Beach volleyball — generic canonical sport support only
- [~] Padel — generic canonical sport support only
- [~] Floorball — generic canonical sport support only
- [~] Aussie rules — generic canonical sport support only

# Phase 5 — Market Interpreter

- [~] Match win/draw/loss — common 1/2/X parsing implemented; broader bookmaker fixtures remain
- [x] Double chance core
- [~] Handicap — explicit-team generic parsing implemented; bookmaker variants remain
- [~] Totals — generic over/under counts implemented
- [ ] Team totals
- [ ] Set/frame/map markets
- [~] Corners — generic total/count recognition only
- [~] Cards — generic total/count recognition only
- [~] Shots / shots on target — generic total/count recognition only
- [ ] Player markets
- [~] General count markets — generic metric recognition started
- [ ] Race/field markets
- [~] Period/scope support — domain field exists; parser coverage remains
- [ ] Overtime/extra-time rules
- [ ] Bookmaker label mappings
- [x] Ambiguity detection core — unresolved markets return explicit reason instead of silent guessing
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
- [~] Evidence persistence — V2 schema exists; service not yet implemented
- [ ] Evidence reuse
- [ ] Conflicting source handling
- [ ] Plain-language summaries
- [ ] Reviewer pass

# Phase 7 — Bookmakers

- [ ] Bookmaker adapter base
- [~] Capability flags — conservative capability field exists; no adapter should claim unsupported features
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
- [~] Plain instruction — normalized JSON/tool instruction path exists; natural-language extraction still required

## Normalize
- [x] Resolve bookmaker name/alias core
- [ ] Resolve events
- [~] Resolve home/away — explicit names accepted by interpreter; event identity resolution remains
- [~] Normalize markets — initial interpreter implemented
- [x] Normalize decimal odds core
- [ ] Resolve duplicate legs
- [~] Flag unresolved legs — interpreter identifies ambiguity; ticket import pipeline not yet wired

## Edit
- [x] Remove games domain operation
- [ ] Replace games
- [ ] Change markets
- [x] Preserve locked picks in trim/remove operations
- [ ] Keep strongest N
- [ ] Lower-risk version
- [ ] Higher-odds version

## Split
- [x] Split by number of slips
- [ ] Split by game count
- [~] Distribute stronger picks — current balancing uses odds/product, not research strength yet
- [ ] Preserve groups

## Target odds
- [x] Trim toward requested odds core
- [x] Minimum-game constraint
- [x] Locked-pick constraint
- [ ] Compare candidate versions in user-facing explanation

## Lineage
- [~] Ticket versions — parent/source fields and V2 persistence schema exist; version service remains
- [x] Parent/child split tracking core
- [~] Original vs edited tracking — parent lineage exists; history/reports remain
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

- [~] Odds snapshots — V2 schema exists; ingestion not implemented
- [~] Price timestamps — V2 schema exists; ingestion not implemented
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
- [~] Won/Lost/Draw/Void/Pending — canonical outcome vocabulary exists; settlement service remains
- [ ] Ticket settlement
- [ ] Postponed/cancelled handling
- [~] Manual correction + audit — audit schema exists; service remains
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

- [~] Blog schema — V2 table exists; service/UI not implemented
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

- [~] Job registry — V2 schema exists; runtime service remains
- [ ] Retry/failure tracking
- [ ] Settlement backlog health
- [ ] Source freshness health
- [ ] Backup freshness
- [~] DB integrity checks — V1 preservation tool checks snapshots; V2 periodic health remains
- [ ] Remove default PIN
- [ ] Remove PIN-in-GET flow
- [ ] Remove browser localStorage write key
- [~] Protect internal writes — OpenClaw gateway boundary established; authentication/permissions remain
- [x] Server-side secrets only for new V2 code
- [~] Automated backups — preservation tool exists; scheduler not configured
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

---

## Build log

- `479ae37` — V2 core domain, decimal-odds validation, bookmaker registry, market interpreter, free-first source registry, initial tests.
- `dddd4e8` — V2 canonical SQLite schema, alias resolution and repository layer.
- `be17779` — OpenClaw JSON gateway plus Ticket Workshop split/trim core.
- `05c9d62` — V2 OpenClaw runtime doctrine, rewritten Sabi skill, heartbeat rules and tool contract.
- `4393cb3` — V1 repository audit, verified preservation snapshot tool and rollback runbook.
