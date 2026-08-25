# Sabi Boy V2 — Living Task Board

> **Branch:** `v2`  
> **Human-facing product:** Sabi Boy  
> **Compatibility identifiers:** SabiAI / `sabiai` / `sabi-ai` remain where changing them would break runtime/data interfaces.  
> **Rule:** A task may be implemented without its phase being release-ready. Dell/OpenClaw runtime acceptance is a separate gate.

## Status

- [x] Implemented at code/task level
- [~] Implemented/partly implemented; live/runtime/coverage gate remains
- [ ] Not yet complete
- [!] Blocked or requires a deliberate live decision

---

## Phase 0 — Preserve V1

- [x] Repository/scripts/skills/systemd/dashboard/data-source/bookmaker inventory
- [x] V1 DB/table inventory and field-level migration mapping
- [x] V1 → V2 deterministic migration framework
- [x] Synthetic V1 migration fixture
- [x] Lossless `legacy_archive` for V1 rows without a direct V2 destination
- [x] Verified SQLite snapshot/checksum/restore tooling
- [x] Rollback design and script
- [~] Actual Dell environment/secrets inventory — must be performed without committing secrets
- [~] Actual production V1 backup — tooling ready; live snapshot is a release action
- [~] Actual production migration rehearsal/reconciliation — code ready; Dell run pending

## Phase 1 — Core Domain / Storage

- [x] V2 package layout and environment-driven settings
- [x] Canonical sport/competition/participant/event models
- [x] Canonical market/selection/pick/ticket/ticket-leg models
- [x] Stable bookmaker identities and aliases
- [x] Decimal-odds validation
- [x] Canonical V2 SQLite schema + migrations
- [x] Source cache/fetch log
- [x] Research evidence persistence
- [x] Ticket draft/version lineage persistence
- [x] Bankroll ledger and reconciliation
- [x] Blog persistence
- [x] Legacy archive
- [~] Full expanded test suite — many tests committed; complete current-suite run on controlled runtime still required

## Phase 2 — OpenClaw-Native Sabi Boy

- [x] `SABI_BOY.md`, identity, soul, operating manual, agent rules and heartbeat rewritten
- [x] Primary Sabi Boy skill rewritten
- [x] Old football-first scanner/research skills converted to V2 compatibility bridges
- [x] Old separate betting-record skill converted to canonical V2 history/settlement
- [x] Dynamic `system.tools` capability truth
- [x] Modular OpenClaw gateway
- [x] `system.*` health/readiness/source/economy tools
- [x] `source.*` free-first tools
- [x] `sports.*` registry/live lookup tools
- [x] `research.*` plan/evidence/assess/next/summary/reviewer tools
- [x] `market.*` interpreter/arbitrage tools
- [x] `bookmaker.*` capability/import-plan/restore/search/convert/build tools
- [x] `ticket.*` intake/edit/variant/draft tools
- [x] `record.*` / `history.*` tools
- [x] `settlement.*` tools
- [x] `blog.*` tools
- [x] Research Scout worker brief
- [x] Skeptic Reviewer worker brief
- [x] Ticket Engineer worker brief
- [~] Actual OpenClaw subagent spawning/swarm acceptance on Dell
- [~] AI Spine runtime integration acceptance after V2 upgrade

## Phase 3 — Free-First Sources

- [x] Source Registry
- [x] Cache/freshness reuse
- [x] Paid-source gate and reason requirement
- [x] Fetch logging / cache metrics / paid-call metrics
- [x] Source-health and API-economy summaries
- [x] TheSportsDB broad free adapter
- [x] Optional football-data.org free-tier adapter
- [x] TheSportsDB team/event/player lookup helpers
- [x] Partial form/schedule support with explicit coverage limits
- [x] Event lineup evidence with explicit warning that it is not a full injury feed
- [x] Event/player statistics helpers
- [~] Complete recent-form sourcing — current unmetered source is partial
- [~] Complete injury/suspension/withdrawal sourcing — needs official/team/news fallback execution
- [~] H2H workflow — research planner/browser/search path exists; dedicated complete source still needed
- [~] Schedule/rest/travel workflow — partial direct feed + browser/search/official fallback remains
- [~] Market-specific statistics across all sports — framework exists; source depth varies by sport
- [~] Official-source discovery and durable source-learning workflow
- [~] OpenClaw Browser/Search fetcher execution acceptance
- [ ] In-flight concurrent-request coalescing

## Phase 4 — Sports Universe

### Knowledge framework
- [x] Football
- [x] Basketball
- [x] Volleyball
- [x] Tennis
- [x] Table tennis
- [x] Baseball
- [x] Ice hockey
- [x] Cricket
- [x] Esports
- [x] Golf
- [x] Handball
- [x] Rugby
- [x] Darts
- [x] Snooker
- [x] Badminton
- [x] MMA / boxing
- [x] Motorsport / cycling
- [x] Futsal / water polo / beach volleyball / padel / floorball / Aussie rules and additional generic profiles
- [x] Unknown-sport discovery instead of `unsupported`

### Live depth
- [~] Multi-sport fixture/event/team/player discovery through broad source + OpenClaw fallback
- [~] Sport-specific deep statistics/availability coverage varies and must keep expanding organically

## Phase 5 — Market Interpreter

- [x] Explicit home/away winner language
- [x] 1/X/2 translation
- [x] Double Chance
- [x] Handicap 1/2 and named handicap
- [x] Match totals
- [x] Team totals
- [x] Corners/cards/shots/shots on target/general count markets
- [x] Generic player stat totals
- [x] Half/quarter/set/map/frame/period recognition core
- [x] Broad metric vocabulary
- [x] Ambiguity rejection instead of silent guessing
- [x] Settlement-rule fingerprint for cross-book compatibility
- [~] Race/field market depth
- [~] Large real bookmaker-label corpus
- [~] Bookmaker-specific overtime/retirement/dead-heat rule mappings

## Phase 6 — Research Intelligence

- [x] Sport-specific research plan
- [x] Market-specific research focus
- [x] Evidence persistence/reuse/freshness
- [x] Structured conflict detection
- [x] Research-case assessment: coverage / stale / weak / missing / conflicts
- [x] Free-first next-task planner
- [x] Plain-language research synthesis: what I know / worries / still to check
- [x] Skeptic-review planner
- [x] Research Scout worker doctrine
- [~] Persistent named research-case session object — evidence works now; richer case persistence is still being introduced
- [~] End-to-end multi-worker live research acceptance
- [~] Automatic official-source conflict resolution

## Phase 7 — Bookmakers

- [x] Bookmaker adapter contract and capability flags
- [x] Stable SportyBet / Bet9ja / Stake / 1xBet identities
- [x] Exact target-book search plan per ticket leg
- [x] Exact conversion verifier: event / sport / market / line / period / side
- [x] Controlled legacy builder runner
- [x] Legacy builder sport/market/period safety gate
- [x] Verified browser-restoration playbook: SportyBet
- [x] Verified browser-restoration playbook: Bet9ja
- [x] Verified browser-restoration playbook: Stake (region/account availability must be checked live)
- [~] 1xBet booking-code restore flow — intentionally discovery-only until live public flow is verified
- [x] Browser-restored slip verifier
- [x] Restored-slip leg-count and combined-odds consistency checks
- [x] Restored booking-code → draft persistence tool
- [~] SportyBet legacy booking-code creation — runtime revalidation required
- [~] Bet9ja legacy booking-code creation — runtime revalidation required
- [ ] Rich market-aware SportyBet builder beyond legacy proven scope
- [ ] Rich market-aware Bet9ja builder beyond legacy proven scope
- [ ] Stake target-ticket builder
- [ ] 1xBet target-ticket builder
- [~] Live event/market/odds extraction adapters

## Phase 8 — Ticket Workshop

### Inputs
- [x] Copied text
- [x] Structured browser-restored booking code
- [~] Screenshot → OpenClaw vision → normalize path; runtime acceptance pending
- [~] X post/link → OpenClaw read → normalize path; runtime acceptance pending
- [x] Plain structured instruction

### Editing
- [x] Remove games
- [x] Keep games
- [x] Replace game
- [x] Change market
- [x] Split into N slips
- [x] Split by games-per-slip
- [x] Trim toward target combined odds
- [x] Locked-leg protection
- [x] Strongest-N selection from supplied research ranking
- [x] Lower-risk market-change planning
- [~] Higher-odds variant using only live verified replacement prices
- [~] User-facing comparison of multiple candidate versions

### Lineage
- [x] Draft persistence
- [x] Parent/child lineage
- [x] Original/imported source preservation
- [x] Booking-code source preservation
- [~] Full dashboard original-vs-edited/conversion storytelling

## Phase 9 — Convert / Rebuild

- [x] Booking-code import planning
- [x] Browser-restored source slip validation
- [x] Target-book search tasks
- [x] Exact-market conversion engine
- [x] Target-book build plan
- [x] Controlled booking-code creation where legacy adapter scope is proven
- [x] Conversion/draft lineage foundations
- [~] Live target-book price discovery
- [~] First real end-to-end SportyBet ↔ Bet9ja conversion on Dell
- [~] End-to-end Stake conversion
- [ ] End-to-end 1xBet conversion after public restore/search flow verification

## Phase 10 — Odds Comparison / Arbitrage

- [x] Timestamped price quote model
- [x] Best compatible price per outcome
- [x] Stale-price rejection
- [x] 2-outcome arbitrage math
- [x] 3-outcome arbitrage math
- [x] N-outcome arbitrage math
- [x] Settlement-rule compatibility
- [x] Stake split / theoretical locked return
- [~] Live multi-book odds ingestion
- [~] Price recheck immediately before rebuild/output
- [~] Opportunity-history persistence and dashboard analytics

## Phase 11 — Settlement / History Reliability

- [x] Unified settlement service
- [x] Won / Lost / Draw / Void / Pending canonical vocabulary
- [x] Idempotent duplicate settlement protection
- [x] Ticket settlement derived from legs
- [x] Manual correction with mandatory reason/audit trail
- [x] Cancel/void propagation core
- [x] Duplicate payout protection
- [x] Settlement-backlog reporting
- [x] Bankroll reconciliation service
- [~] Sport/bookmaker-specific settlement-rule library depth
- [~] Real production history reconciliation

## Phase 12 — Historical Insights

- [x] Overall record and win percentage
- [x] Betting P/L separated from deposits/withdrawals
- [x] Bankroll history
- [x] Current/best/worst streaks
- [x] By sport
- [x] By competition
- [x] By market
- [x] By bookmaker
- [x] By strategy
- [x] By decimal-odds band
- [x] By ticket size
- [x] By combined-odds band
- [x] Ticket source/type
- [x] Ticket killers
- [x] Daily outcome series
- [x] Bankroll series
- [~] Original vs edited/conversion comparative outcome analysis

## Phase 13 — Read-Only Dashboard

- [x] New standalone `dashboard/v2_app.py` instead of extending the V1 monolith
- [x] GET-only `/api/v2/*`
- [x] Test forbidding dashboard mutation methods
- [x] No PIN/write token/localStorage write-key in V2 app
- [x] Overview
- [x] Games/Picks
- [x] Tickets
- [x] Performance
- [x] Finance
- [x] Strategies
- [x] History
- [x] Sabi Boy Blog
- [x] System
- [x] Bankroll/outcome/performance charts and breakdowns
- [x] Ticket-killer view
- [~] Mobile/PWA/browser visual regression on Dell/real phone
- [~] Production history correctness after migration

## Phase 14 — Sabi Boy Blog

- [x] Blog schema/service
- [x] Draft/publish/archive
- [x] Categories/tags/related records
- [x] OpenClaw blog tools
- [x] Reflection context based on our recent blog/history
- [x] V1 diary → published historical blog migration
- [x] Dashboard blog index/post read path
- [~] Daily reflection scheduling
- [~] Weekly reflection scheduling
- [~] Event-driven post rules
- [ ] RSS/Atom if still useful after acceptance

## Phase 15 — Reliability / Security / Operations

- [x] READY / DEGRADED / OBSERVE ONLY / ACTION LOCKED logic
- [x] DB integrity checks
- [x] Bankroll integrity checks
- [x] Source health/API economy
- [x] Settlement backlog health
- [x] Verified backup/restore/checksum tooling
- [x] V2 environment template; secrets server-side only
- [x] Separate V2 systemd service on 127.0.0.1:8091
- [x] Checkout-portable runtime preparation
- [x] Release acceptance runner
- [x] Guarded staging script
- [x] External-route cutover verifier
- [x] Explicit rollback helper
- [x] Deployment/upgrade runbook
- [~] Automated scheduled backups on Dell
- [~] Job retry/failure runtime registration
- [~] Bookmaker browser-adapter health checks
- [~] Security review on actual Dell/OpenClaw deployment

## Phase 16 — Release Gate

**Do not promote `v2` to `main` and do not issue the final OpenClaw upgrade prompt until the applicable gates below pass.**

- [ ] Full current pytest suite passes on controlled Dell/runtime
- [ ] V1 database snapshot taken and verified
- [ ] V1 → V2 migration rehearsal on actual data passes
- [ ] Historical pick/ticket totals reconcile
- [ ] Bankroll reconciles exactly
- [ ] Strategy/compound/long-shot history reviewed
- [ ] Sabi Boy OpenClaw tool acceptance
- [ ] Research Scout/Skeptic/Ticket Engineer OpenClaw acceptance
- [ ] Multi-sport research acceptance across representative sports
- [ ] SportyBet browser restoration acceptance
- [ ] Bet9ja browser restoration acceptance
- [ ] Stake browser restoration acceptance where region allows
- [ ] At least one real end-to-end bookmaker conversion/rebuild pair passes
- [ ] Dashboard mobile/desktop acceptance against migrated data
- [ ] Blog migration/display acceptance
- [ ] Settlement duplicate/correction acceptance
- [ ] Backup/restore drill passes on Dell
- [ ] External route/cutover rehearsal documented
- [ ] Security/secrets review
- [x] Repository deployment runbook exists
- [ ] Release notes complete
- [ ] Final V2 acceptance review
- [ ] Promote/merge `v2` to `main` according to Forgejo-first release workflow
- [ ] Provide the user the final one-shot OpenClaw V2 upgrade/setup prompt

---

## Current release commands

Prepare only (no migration/service cutover):

```bash
bash scripts/sabi_v2_prepare_runtime.sh
```

Stage safely beside V1:

```bash
bash scripts/sabi_v2_stage.sh
```

Run release acceptance directly:

```bash
.venv/bin/python scripts/sabi_v2_acceptance.py --migrate-v1
```

After the real external route has been changed and verified by the Dell-side operator/OpenClaw:

```bash
.venv/bin/python scripts/sabi_v2_finalize_cutover.py --health-url 'https://YOUR-SABI-HOST/health'
```

Rollback helper:

```bash
.venv/bin/python scripts/sabi_v2_rollback.py
```

Detailed runbook: `docs/SABI_BOY_V2_DEPLOYMENT.md`.
