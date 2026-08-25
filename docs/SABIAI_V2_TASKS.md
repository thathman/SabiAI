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
- [x] Stable canonical bookmaker identities
- [x] Pick model
- [x] Ticket model
- [x] Ticket leg model
- [x] Bankroll ledger service
- [~] Shared repository/data layer — canonical SQLite repository, source cache/logging, ticket persistence, evidence persistence and history reads exist; more repositories remain
- [x] V2 schema
- [~] Migration framework — preservation/rollback and schema migration runner exist; V1 data migration is not implemented
- [~] Core tests — current local V2 harness passes 36 tests; controlled Dell/runtime acceptance remains a release gate

# Phase 2 — OpenClaw Native Sabi

- [x] Rewrite Sabi V2 skill
- [x] Plain-language doctrine
- [x] Decimal odds doctrine
- [x] Explicit team/selection wording
- [x] Free-first doctrine
- [x] Broad-sports doctrine
- [x] Read-only dashboard boundary
- [~] Native `sports.*` tools — list/describe core implemented; live event helpers remain
- [~] Native `research.*` tools — research plan and evidence save/read implemented; live research orchestration remains
- [~] Native `bookmaker.*` tools — canonical resolution/capability reporting implemented; search/code import/conversion remain
- [~] Native `market.*` tools — plain interpreter and rule-aware arbitrage implemented; wider bookmaker mappings and general price comparison remain
- [~] Native `ticket.*` tools — normalize/from-text/split/split-by-size/trim/remove/keep/change/replace implemented; booking-code import/conversion remain
- [~] Native `record.*` / `history.*` tools — bankroll write and read-only history summaries implemented; picks/tickets/settlement recording remains
- [ ] Native `blog.*` tools
- [~] Native `system.*` tools — V2 initialize/database health implemented; jobs/sources/backups/settlement health remain
- [~] AI Spine memory integration — existing agent integration retained; V2 research-memory conventions added to runtime doctrine
- [ ] Temporary specialist-worker pattern
- [ ] Skeptic/reviewer worker
- [~] Heartbeat/scheduler review — V2 heartbeat doctrine written; legacy schedules still require live review/migration

# Phase 3 — Free-First Sources

- [x] Source Registry core
- [x] Cache/freshness engine core — TTL cache and freshness checks implemented in SourceService/SQLite
- [ ] Official-source adapters
- [ ] Public endpoint adapters
- [ ] Public web adapters
- [ ] Browser fallback
- [ ] Search fallback
- [ ] Source discovery
- [ ] Source health
- [x] Paid API gate core
- [x] Paid usage log core — every source attempt can log paid/free, cache use, success/failure and reason
- [~] Duplicate-request prevention — stable request-key cache prevents repeated fresh fetches; concurrent/in-flight coalescing remains
- [x] Source fallback tests committed

# Phase 4 — Sports Framework

## First wave
- [~] Football — sport profile and market-aware research planning exist; dedicated live research adapters remain
- [~] Basketball — sport profile and market-aware research planning exist; dedicated live research adapters remain
- [~] Volleyball — sport profile and market-aware research planning exist; dedicated live research adapters remain
- [~] Tennis — sport profile and market-aware research planning exist; dedicated live research adapters remain
- [~] Table tennis — sport profile and market-aware research planning exist; dedicated live research adapters remain
- [~] Baseball — sport profile and market-aware research planning exist; dedicated live research adapters remain
- [~] Ice hockey — sport profile and market-aware research planning exist; dedicated live research adapters remain
- [~] Cricket — sport profile and market-aware research planning exist; dedicated live research adapters remain
- [~] Esports — patch/roster/map research profile exists; dedicated live research adapters remain
- [~] Golf — course/weather/tee-time research profile exists; dedicated live research adapters remain

## Second wave
- [~] Handball — generic profile exists
- [~] Rugby — generic profile exists
- [~] Darts — generic profile exists
- [~] Snooker — generic profile exists
- [~] Badminton — generic profile exists
- [~] MMA — generic profile exists
- [~] Boxing — generic profile exists
- [~] Motorsport — generic profile exists
- [~] Cycling — generic profile exists
- [~] Futsal — generic profile exists
- [~] Water polo — generic profile exists
- [~] Beach volleyball — generic profile exists
- [~] Padel — generic profile exists
- [~] Floorball — generic profile exists
- [~] Aussie rules — generic profile exists
- [x] Unknown-sport discovery behavior — unfamiliar sports return a discovery profile instead of `unsupported`

# Phase 5 — Market Interpreter

- [~] Match win/draw/loss — common 1/2/X and named-winner parsing implemented; bookmaker corpus remains
- [x] Double chance core
- [x] Handicap core — explicit team names and `Handicap 1/2 +/-line` parsing implemented
- [x] Totals core
- [x] Team totals core
- [~] Set/frame/map markets — totals/period recognition implemented; winner/handicap variants remain
- [~] Corners — totals/count recognition implemented; bookmaker variants remain
- [~] Cards — totals/count recognition implemented; bookmaker variants remain
- [~] Shots / shots on target — totals/player recognition implemented; bookmaker variants remain
- [~] Player markets — generic named-player over/under stats implemented; richer player market corpus remains
- [~] General count markets — broad metric vocabulary implemented; bookmaker variants remain
- [ ] Race/field markets
- [~] Period/scope support — halves, quarters, sets, maps and periods implemented; broader scope corpus remains
- [~] Overtime/extra-time rules — rule fingerprint exists for price compatibility; sport/bookmaker mappings remain
- [ ] Bookmaker label mappings
- [x] Ambiguity detection core — unresolved markets return explicit reason instead of silent guessing
- [~] Real market-name test corpus — expanded plain-language tests committed; large bookmaker corpus remains

# Phase 6 — Research V2

- [~] Research request/orchestration — planning and evidence layer exist; live source execution/reviewer orchestration remains
- [x] Sport-specific checklist selection core
- [x] Market-specific checklist selection core
- [ ] Recent form adapter/workflow
- [ ] Home/away form adapter/workflow
- [ ] H2H adapter/workflow
- [ ] Injuries/availability adapter/workflow
- [ ] Expected lineups/rosters adapter/workflow
- [ ] Schedule/rest adapter/workflow
- [ ] Match/competition context adapter/workflow
- [~] Market-specific stats — planner selects relevant focus; data adapters remain
- [x] Evidence persistence core
- [x] Evidence reuse core — freshness-limited reuse implemented
- [ ] Conflicting source handling
- [~] Plain-language summaries — evidence model requires a plain summary; full synthesis service remains
- [ ] Reviewer pass

# Phase 7 — Bookmakers

- [x] Bookmaker adapter base
- [x] Capability flags core — features are exposed only after an adapter proves them
- [~] SportyBet adapter — existing browser ticket-build/code-create path registered; runtime revalidation, import and search remain
- [~] Bet9ja adapter — existing browser ticket-build/code-create path registered; runtime revalidation, import and search remain
- [ ] 1xBet adapter
- [ ] Stake adapter
- [ ] Event search
- [ ] Market search
- [ ] Decimal odds extraction
- [ ] Booking-code import
- [~] Booking-code creation where possible — compatibility path registered for SportyBet and Bet9ja; V2 runtime validation remains
- [ ] Slip parsing from bookmaker code/page
- [~] Bookmaker rule metadata — rule fingerprint exists; bookmaker-specific mappings remain
- [ ] Browser fallback adapter
- [~] Adapter fixtures/tests — capability tests committed; live browser fixtures remain

# Phase 8 — Ticket Workshop

## Inputs
- [ ] Booking code
- [~] Screenshot/image — OpenClaw vision can extract visible ticket text/legs into the canonical normalization path; end-to-end runtime workflow remains
- [x] Copied text — deterministic importer implemented
- [~] Bookmaker share text — common copied/share formats supported; bookmaker-specific corpus remains
- [~] X post — OpenClaw can read/extract post content then use `ticket.from_text`/`ticket.normalize`; end-to-end runtime workflow remains
- [~] Plain instruction — normalized tool instruction path exists; broader natural-language extraction still required

## Normalize
- [x] Resolve bookmaker name/alias core
- [ ] Resolve canonical events against live bookmaker/source IDs
- [~] Resolve home/away — explicit names accepted and visible event labels survive all current ticket edits; live event identity resolution remains
- [~] Normalize markets — expanded interpreter implemented
- [x] Normalize decimal odds core
- [x] Detect duplicate legs
- [x] Flag unresolved/ambiguous legs without silently discarding them

## Edit
- [x] Remove games
- [x] Replace games core + OpenClaw gateway
- [x] Change markets core
- [x] Preserve locked picks in trim/remove/keep/change operations
- [x] Keep only selected games core
- [ ] Keep strongest N using research strength
- [ ] Lower-risk version
- [ ] Higher-odds version

## Split
- [x] Split by number of slips
- [x] Split by game count
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

- [ ] Source-book code import
- [ ] Target-book event mapping
- [ ] Equivalent-market mapping
- [ ] Missing-market alternatives
- [ ] Target-book odds
- [~] Build target slip — existing SportyBet/Bet9ja browser builders registered as compatibility integrations; canonical V2 orchestration remains
- [~] Create/extract booking code — existing SportyBet/Bet9ja builders can create/extract codes; controlled-runtime V2 validation remains
- [ ] Verify rebuilt ticket
- [ ] Conversion history
- [ ] First end-to-end conversion pair

# Phase 10 — Odds Comparison / Arbitrage

- [~] Odds snapshots — V2 schema exists; bookmaker ingestion not implemented
- [~] Price timestamps — quote objects/schema support timestamps; bookmaker ingestion not implemented
- [~] Best price comparison — best compatible price per outcome implemented inside arbitrage; general comparison service remains
- [x] Stale-price rejection core
- [x] Two-outcome calculation
- [x] Three-outcome calculation
- [x] N-outcome calculation
- [x] Settlement-rule compatibility check core
- [x] Stake split calculation core
- [ ] Price recheck before external result/booking
- [~] False-match rejection — normalized event/market keys are required; wider identity tests remain
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
- [~] Bankroll reconciliation — ledger reconciliation service exists; V1/V2 migration reconciliation remains
- [ ] Consistency checks

# Phase 12 — Historical Insights

- [x] Overall W/L/D/void/pending core
- [x] Win percentage core
- [ ] P/L summary service
- [~] Bankroll — current balance/history implemented; change-over-period insights remain
- [ ] Current streak
- [ ] Best/worst streak
- [x] By sport core
- [ ] By competition
- [x] By market core
- [x] By bookmaker core
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
- [ ] Source freshness health summary
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
- [~] Paid API usage metrics — raw paid/free usage log exists; dashboard/summary metrics remain
- [~] Cache metrics — cache-hit events are logged; aggregate metrics remain

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
- Source/sports/odds slice — broad open-ended sports registry, sport/market research planner, SourceService cache/free-first execution, schema migration runner and rule-aware arbitrage engine.
- `916c145` / `29b345f` — research evidence package and reusable evidence store.
- `3b4db05` / `676f18f` / `c01ea35` — bankroll ledger and read-only history services.
- `3a3d3e2` / `3bcb81f` — explicit event labels plus expanded Ticket Workshop editing/splitting.
- `945d36b` — OpenClaw gateway exposes research evidence, bankroll/history and expanded ticket tools.
- `34cf8ce` / `30f5fc9` — expanded plain-language market interpretation and home/away edge-case fix.
- `6e0e8d6` — stable canonical bookmaker identities.
- `85e82b7` / `5c80852` — expanded market-language and service regression tests.
- `83ce209` — OpenClaw V2 tool contract updated to match the foundation build.
- `e7f91e3` / `5a7adfd` — conservative bookmaker adapter/capability contract with SportyBet and Bet9ja compatibility builders.
- `c2532a5` / `90a15cc` — canonical ticket normalization with duplicate/ambiguity/invalid-odds checks.
- `8d44f62` — OpenClaw gateway unified around ticket normalization and bookmaker capability reporting.
- `d2f6ad1` — ticket normalizer/bookmaker capability regression tests.
- `7566635` / `ee6741e` — deterministic copied/share ticket text importer.
- `1ce100b` — OpenClaw `ticket.from_text` path for copied text and text extracted from X/screenshots.
- `00bc5c3` — copied/extracted ticket-text regression tests.
- `4abb2c1` — OpenClaw tool contract updated with ticket intake flow.
- Local V2 harness checkpoint — **36 tests passing** across the currently synced foundation/ticket/service test set.
