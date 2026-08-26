# Sabi Boy V2 — Living Task Board

> **Branch:** `v2`  
> **Human-facing product:** Sabi Boy  
> **Compatibility identifiers:** SabiAI / `sabiai` remain where changing them would break runtime/data interfaces. The existing OpenClaw machine agent ID is `prediction`; its human-facing name is Sabi Boy.
> **Rule:** A task may be implemented without its phase being release-ready. Dell/OpenClaw/runtime acceptance is a separate gate.

## Status

- [x] Implemented at code/task level
- [~] Code/path exists; live/runtime/data-coverage acceptance remains
- [ ] Release/acceptance action not yet performed
- [!] Deliberately deferred or live-dependent; do not fake implementation before verification

## Development freeze status

- [x] V2 repository-side development is complete for the installation/testing candidate.
- [x] Current-format OpenClaw skills are synchronized with the final V2 tool surface.
- [x] OpenClaw acceptance requires the final V2 capabilities, not an earlier V2 subset.
- [x] Read-only dashboard exposes our ticket-version and bookmaker-price history analytics.
- [x] Remaining open items are Dell/OpenClaw/live-browser/data acceptance or explicitly deferred optional/live-dependent capabilities.
- [x] Any code change after this point should be driven by a failing test, migration discrepancy, real browser incompatibility, security finding, or explicit new product decision.

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
- [x] Persistent named research-case/session storage
- [x] Ticket draft/version lineage persistence
- [x] Bookmaker offer/price-observation persistence
- [x] Durable learned-source registry
- [x] Bankroll ledger and reconciliation
- [x] Blog persistence
- [x] Legacy archive
- [x] Ticket round-trip participant derivation from explicit `Home vs Away` labels
- [~] Full expanded test suite — regression coverage committed; complete current-suite run on controlled Dell/runtime required

## Phase 2 — OpenClaw-Native Sabi Boy

- [x] `SABI_BOY.md`, identity, soul, operating manual, agent rules and heartbeat rewritten
- [x] Primary Sabi Boy behavior rewritten
- [x] Old football-first scanner/research skills converted to V2 compatibility bridges
- [x] Old separate betting-record skill converted to canonical V2 history/settlement
- [x] Current OpenClaw directory/`SKILL.md` packages with frontmatter for Sabi Boy Core
- [x] Current OpenClaw skill package: bookmaker workflows
- [x] Current OpenClaw skill package: Research Scout
- [x] Current OpenClaw skill package: Skeptic Reviewer
- [x] Current OpenClaw skill package: Ticket Engineer
- [x] Current OpenClaw skill package: Records/Settlement
- [x] Current OpenClaw skill package: Blog
- [x] Final skill sync includes durable research cases, source learning, settlement profiles, verified variants, advanced history, bookmaker browser health and Blog triggers
- [x] Dynamic `system.tools` capability truth
- [x] Modular OpenClaw gateway
- [x] `system.*` health/readiness/source/economy/job tools
- [x] `source.*` free-first + durable discovery/learning tools
- [x] `sports.*` registry/live lookup/form/H2H/injury/match-snapshot tools
- [x] `research.*` plan/evidence/persistent-case/assess/next/summary/reviewer tools
- [x] `market.*` interpreter/settlement-profile/price-comparison/arbitrage tools
- [x] `bookmaker.*` capability/import/restore/search/multi-book/convert/build/verify/health tools
- [x] `ticket.*` intake/edit/verified-variant/draft/research tools
- [x] `record.*` / `history.*` tools including advanced lineage/price analytics
- [x] `settlement.*` tools
- [x] `blog.*` tools including event-driven reflection triggers
- [x] Safe OpenClaw agent ensure/create helper — never silently retargets a mismatched existing agent
- [x] Fail-closed OpenClaw workspace/skill/final-tool-surface acceptance verifier
- [x] Guarded post-staging OpenClaw activation flow
- [~] Actual OpenClaw subagent spawning/swarm acceptance on Dell
- [~] AI Spine runtime integration acceptance after V2 upgrade

## Phase 3 — Free-First Sources

- [x] Source Registry
- [x] Cache/freshness reuse
- [x] In-flight concurrent-request coalescing for identical requests
- [x] Paid-source gate and reason requirement
- [x] Fetch logging / cache metrics / paid-call metrics
- [x] Source-health and API-economy summaries
- [x] TheSportsDB broad free adapter
- [x] ESPN public-data secondary free adapter for supported major leagues
- [x] Optional football-data.org free-tier adapter
- [x] Provider-scoped source IDs — never reuse a TheSportsDB id at ESPN or vice versa
- [x] TheSportsDB/ESPN team/event/player lookup helpers where supported
- [x] Multi-source recent-form pipeline with explicit completeness status
- [x] Plain W/D/L form summaries and home/away splits
- [x] Recent-available H2H workflow with explicit history-coverage limits
- [x] ESPN injury feed integration with official-confirmation requirement
- [x] Event lineup evidence with explicit warning that it is not a full injury feed
- [x] Event/player statistics helpers
- [x] `sports.match_snapshot` composed pre-play research view
- [x] Official/public source-discovery planning and durable source-learning workflow
- [x] Candidate → verified/rejected/retired learned-source lifecycle and health checks
- [~] Complete recent-form sourcing for every sport/competition — source depth is a live coverage property, not a finite code task
- [~] Complete injury/suspension/withdrawal sourcing — official/team/news fallback execution must be proven live
- [~] Complete long-history H2H across every sport/competition — depends on available public history
- [~] Schedule/rest/travel workflow — direct feeds + browser/search/official fallback must be exercised live
- [~] Market-specific statistics across all sports — framework exists; source depth expands organically
- [~] OpenClaw Browser/Search fallback execution acceptance

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
- [~] Multi-sport fixture/event/team/player discovery through broad sources + OpenClaw fallback
- [~] Sport-specific deep statistics/availability coverage varies and must keep expanding organically

## Phase 5 — Market Interpreter

- [x] Explicit home/away winner language
- [x] 1/X/2 translation
- [x] Double Chance
- [x] Draw No Bet normalization
- [x] Handicap 1/2 and named handicap
- [x] Common `spread` ingestion normalized to plain handicap language
- [x] Match totals
- [x] Team totals
- [x] Corners/cards/shots/shots on target/general count markets
- [x] Generic player stat totals
- [x] Half/quarter/set/map/frame/period recognition core
- [x] Broad metric vocabulary
- [x] Ambiguity rejection instead of silent guessing
- [x] Settlement-rule fingerprint for cross-book compatibility
- [x] Round-trip winner/double-chance interpretation from explicit event label context
- [x] Race/field core: outright/race/tournament winner, Top-N finish, podium, make/miss cut, group winner
- [x] Sport-level settlement profiles for overtime/retirement/dead-heat/forfeit/event-format concerns
- [~] Additional bookmaker-specific label aliases will be learned from real live menus as encountered
- [~] Exact bookmaker policy values for variable settlement rules must be verified against current live rule pages before equivalence is claimed

## Phase 6 — Research Intelligence

- [x] Sport-specific research plan
- [x] Market-specific research focus
- [x] Evidence persistence/reuse/freshness
- [x] Persistent named research-case/session object
- [x] Evidence attachment and case resume across workers/sessions
- [x] Batch Scout evidence intake
- [x] Structured conflict detection
- [x] Research-case assessment: coverage / stale / weak / missing / conflicts
- [x] Free-first next-task planner
- [x] Plain-language research synthesis: what I know / worries / still to check
- [x] Skeptic-review planner
- [x] Research Scout worker doctrine
- [x] Ticket-wide per-leg research planner
- [x] Ticket-wide match-snapshot orchestration
- [x] Large-ticket automatic Skeptic-review trigger
- [~] End-to-end multi-worker live research acceptance
- [!] Conflicting live facts are deliberately **not** auto-resolved by guessing; Sabi Boy must recheck a fresher/more authoritative source and let the Skeptic challenge unresolved conflicts

## Phase 7 — Bookmakers

- [x] Bookmaker adapter contract and capability flags
- [x] Stable SportyBet / Bet9ja / Stake / 1xBet identities
- [x] Exact target-book search plan per ticket leg
- [x] Multi-book exact-search planner
- [x] Browser price-result normalization / wrong-book / duplicate / invalid-odds rejection
- [x] Fresh-price timestamps and default conversion freshness gate
- [x] Exact conversion verifier: event / sport / market / line / period / side
- [x] Controlled legacy builder runner
- [x] Legacy builder sport/market/period safety gate
- [x] Verified browser-restoration playbook: SportyBet
- [x] Verified browser-restoration playbook: Bet9ja
- [x] Verified browser-restoration playbook: Stake (region/account availability must be checked live)
- [x] Verified market-search browser playbook: SportyBet
- [x] Verified market-search browser playbook: Bet9ja
- [x] Verified market-search browser playbook: Stake (region/account availability runtime check)
- [x] Browser-restored slip verifier
- [x] Restored-slip leg-count and combined-odds consistency checks
- [x] Restored booking-code → draft persistence tool
- [x] Rebuilt booking-code structural verifier with price-change separation
- [x] Rich market-aware SportyBet browser builder plan
- [x] Rich market-aware Bet9ja browser builder plan
- [x] Bookmaker browser-health service/tool separates configured playbooks from recently exercised behavior
- [~] SportyBet legacy/rich booking-code creation — real browser revalidation required
- [~] Bet9ja legacy/rich booking-code creation — real browser revalidation required
- [~] Live event/market/odds extraction — playbooks/validation ready; controlled runtime acceptance pending
- [!] 1xBet restore/search/build remains discovery-only until Work verifies the configured regional public flow; do not invent selectors or claim support before then
- [!] Stake target booking-code creation remains unclaimed until Work confirms that a current reusable-code creation flow exists for the accessible region/account state

## Phase 8 — Ticket Workshop

### Inputs
- [x] Copied text
- [x] Structured browser-restored booking code
- [~] Screenshot → OpenClaw vision → normalize path; runtime acceptance pending
- [~] X post/link → OpenClaw read → normalize path; runtime acceptance pending
- [x] Plain structured instruction
- [x] Persistent `draft_id` accepted by common Ticket Workshop operations

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
- [x] Higher-odds variant using only fresh verified replacement prices tied to exact ticket legs
- [x] Candidate-version comparison without equating higher combined odds with better quality

### Lineage
- [x] Draft persistence
- [x] Parent/child lineage
- [x] Original/imported source preservation
- [x] Booking-code source preservation
- [x] Converted-draft price-observation preservation
- [x] Verified-built child draft after code reload/verification
- [x] Parent→child outcome/odds analytics
- [x] Dashboard History view for ticket edit/conversion outcome storytelling
- [~] Visual correctness against migrated production history is part of Work acceptance

## Phase 9 — Convert / Rebuild

- [x] Booking-code import planning
- [x] Browser-restored source slip validation
- [x] Target-book search tasks
- [x] Fresh target-price validation
- [x] Exact-market conversion engine
- [x] Target-book build plan
- [x] Controlled booking-code creation where legacy adapter scope is proven
- [x] Rich SportyBet/Bet9ja browser build-plan path for visible markets
- [x] Conversion/draft lineage foundations
- [x] Price-observation lineage on converted draft
- [x] Generated-code reload/structural verification tool
- [x] Build-plan target inferred from converted draft with cross-book mismatch protection
- [~] First real end-to-end SportyBet ↔ Bet9ja conversion/rebuild on Dell
- [~] End-to-end Stake restoration/search/conversion where region permits
- [!] End-to-end 1xBet conversion is live-dependent on verifying its current regional restore/search/build flow

## Phase 10 — Odds Comparison / Arbitrage

- [x] Timestamped price quote model
- [x] Fresh browser bookmaker-price observation store
- [x] Best compatible price per outcome
- [x] Ticket-leg best-price comparison across multiple freshly searched bookmakers
- [x] Source-ticket historical odds excluded from current best-price ranking unless freshly re-searched
- [x] Wrong-line/period offers excluded from exact price comparison
- [x] Stale-price rejection
- [x] Price recheck requirement immediately before conversion/rebuild
- [x] 2-outcome arbitrage math
- [x] 3-outcome arbitrage math
- [x] N-outcome arbitrage math
- [x] Expanded settlement-rule compatibility fingerprint
- [x] Stake split / theoretical locked return
- [x] Historical bookmaker price-movement/disagreement analytics
- [x] Read-only dashboard History display for recorded price movement/disagreement
- [~] Live multi-book browser extraction runtime acceptance

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
- [x] Sport-level settlement-rule library with bookmaker-verification flags for variable policies
- [~] Exact current bookmaker-specific retirement/dead-heat/overtime/forfeit policies must be verified live before cross-book equivalence
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
- [x] Original vs edited/conversion parent-child comparative outcome analysis
- [x] Historical bookmaker price movement
- [x] Historical cross-book price disagreement

## Phase 13 — Read-Only Dashboard

- [x] New standalone `dashboard/v2_app.py` instead of extending the V1 monolith
- [x] GET-only `/api/v2/*`
- [x] Tests forbidding dashboard mutation methods
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
- [x] Advanced ticket-version comparison on History
- [x] Recorded bookmaker price movement/disagreement on History
- [~] Mobile/PWA/browser visual regression on Dell/real phone
- [~] Production history correctness after migration

## Phase 14 — Sabi Boy Blog

- [x] Blog schema/service
- [x] Draft/publish/archive
- [x] Categories/tags/related records
- [x] OpenClaw blog tools
- [x] Current-format OpenClaw Blog skill
- [x] Reflection context based on our recent blog/history
- [x] Event-driven trigger evaluator: corrections, streaks, ticket killers, source discoveries, busy result windows, bookmaker disagreement
- [x] Trigger timestamp handling supports SQLite and ISO timestamps safely
- [x] V1 diary → published historical blog migration
- [x] Dashboard blog index/post read path
- [x] Idempotent OpenClaw daily-reflection automation installer
- [x] Idempotent OpenClaw weekly-reflection automation installer
- [~] Daily/weekly automation execution acceptance on Dell/OpenClaw
- [!] RSS/Atom is deliberately deferred; it is not required for V2 installation/acceptance and can be added later if there is a real consumer

## Phase 15 — Reliability / Security / Operations

- [x] READY / DEGRADED / OBSERVE ONLY / ACTION LOCKED logic
- [x] DB integrity checks
- [x] Bankroll integrity checks
- [x] Source health/API economy
- [x] Settlement backlog health
- [x] Durable job registry with start/success/failure/consecutive-failure tracking
- [x] Verified backup/restore/checksum tooling
- [x] Daily verified-backup systemd service/timer + conservative retention pruner
- [x] Runtime preparation installs rendered dashboard + backup units
- [x] Staging enables backup timer only after V2 acceptance
- [x] Rollback restores the pre-stage backup-timer posture
- [x] V2 environment template; secrets server-side only
- [x] Explicit OpenClaw compatibility agent-id setting
- [x] Separate V2 systemd service on 127.0.0.1:8091
- [x] Checkout-portable runtime preparation
- [x] Release acceptance runner
- [x] Guarded staging script
- [x] Safe OpenClaw agent ensure/create script
- [x] OpenClaw exact-workspace/skill/final-tool-surface acceptance script
- [x] Guarded post-staging OpenClaw activation script
- [x] Current OpenClaw automation-scheduler integration
- [x] Bookmaker browser-health service/tool
- [x] External-route cutover verifier
- [x] External finalizer requires green OpenClaw activation and the exact staged commit
- [x] Explicit rollback helper
- [x] Deployment/upgrade runbook
- [~] Backup timer/job/browser-health behavior must be observed on the real Dell runtime
- [~] Security review on actual Dell/OpenClaw deployment

## Phase 16 — Installation / Test / Release Gate

**Repository development is frozen. Do not promote `v2` to `main` until the applicable runtime gates below pass.**

- [ ] Full current pytest suite passes on controlled Dell/runtime
- [ ] V1 database snapshot taken and verified
- [ ] V1 → V2 migration rehearsal on actual data passes
- [ ] Historical pick/ticket totals reconcile
- [ ] Bankroll reconciles exactly
- [ ] Strategy/compound/long-shot history reviewed
- [ ] Sabi Boy OpenClaw final-tool-surface acceptance
- [ ] Current-format Sabi Boy skill visibility acceptance on the real agent
- [ ] Research Scout/Skeptic/Ticket Engineer OpenClaw acceptance
- [ ] Persistent research-case resume across OpenClaw sessions verified
- [ ] Learned-source discovery/verify/reuse workflow verified
- [ ] Multi-sport research acceptance across representative sports
- [ ] SportyBet browser restoration acceptance
- [ ] Bet9ja browser restoration acceptance
- [ ] Stake browser restoration acceptance where region allows
- [ ] SportyBet rich booking-code build/reload verification acceptance
- [ ] Bet9ja rich booking-number build/reload verification acceptance
- [ ] At least one real end-to-end bookmaker conversion/rebuild pair passes
- [ ] Multi-book fresh-price comparison acceptance
- [ ] Bookmaker browser-health observations reflect live tests correctly
- [ ] Settlement profile/live-bookmaker rule verification tested for at least tennis/racquet, golf/field and overtime sport cases
- [ ] Dashboard mobile/desktop acceptance against migrated data
- [ ] Advanced History ticket-version/price panels verified against real data
- [ ] Blog migration/display acceptance
- [ ] Daily/weekly OpenClaw reflection automation acceptance
- [ ] Event-driven `blog.triggers` behavior acceptance
- [ ] Job success/failure/retry/readiness behavior acceptance
- [ ] Settlement duplicate/correction acceptance
- [ ] Backup timer + backup/restore drill passes on Dell
- [ ] External route/cutover rehearsal documented
- [ ] Security/secrets review
- [x] Repository deployment runbook exists
- [x] Release-candidate notes exist
- [x] ChatGPT Work installation/testing handoff exists
- [ ] Final V2 acceptance review
- [ ] Promote/merge `v2` to `main` according to Forgejo-first release workflow
- [ ] Produce the final production OpenClaw/cutover instruction only after runtime acceptance is green

---

## Current release commands

Prepare only (no migration/service/OpenClaw cutover):

```bash
bash scripts/sabi_v2_prepare_runtime.sh
```

Rehearse safely on a separate port before the approved in-place replacement:

```bash
bash scripts/sabi_v2_stage.sh
```

Run application release acceptance directly:

```bash
.venv/bin/python scripts/sabi_v2_acceptance.py --migrate-v1
```

After staging is green, activate/verify the Sabi Boy OpenClaw agent without changing external routing:

```bash
bash scripts/sabi_v2_activate_openclaw.sh
```

Run OpenClaw-only acceptance manually:

```bash
.venv/bin/python scripts/sabi_v2_openclaw_acceptance.py --report data/release/openclaw-manual-check.json
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
ChatGPT Work installation/testing handoff: `docs/SABI_BOY_V2_WORK_HANDOFF.md`.  
Release-candidate notes: `docs/SABI_BOY_V2_RELEASE_CANDIDATE.md`.
