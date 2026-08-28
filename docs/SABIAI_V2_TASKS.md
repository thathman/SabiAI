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
- [x] Actual Dell environment/secrets inventory completed without committing or printing secrets
- [x] Actual production V1 backup created and checksum/integrity verified before V1 removal
- [x] Actual production migration rehearsal/reconciliation completed on Dell

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
- [x] Full expanded test suite — 234 tests pass locally and on the controlled Dell/runtime

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
- [x] Actual OpenClaw Research Scout/Skeptic/Ticket Engineer spawning and synthesis acceptance on Dell
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
- [x] OpenClaw Browser/Search fallback execution acceptance — live worker fan-out used current web search/fetch sources and persisted evidence

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
- [x] Current SportyBet and Bet9ja policy pages were checked for representative retirement, dead-heat/reduced-event and overtime cases; exact market labels still must match before equivalence is claimed

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
- [x] End-to-end live Research Scout → Skeptic → Ticket Engineer fan-out with durable evidence and Sabi Boy reconciliation
- [!] Conflicting live facts are deliberately **not** auto-resolved by guessing; Sabi Boy must recheck a fresher/more authoritative source and let the Skeptic challenge unresolved conflicts

## Phase 7 — Bookmakers

- [x] Bookmaker adapter contract and capability flags
- [x] Stable SportyBet / Bet9ja identities; other bookmaker targets removed from the active registry and browser playbooks by owner direction
- [x] Exact target-book search plan per ticket leg
- [x] Multi-book exact-search planner
- [x] Browser price-result normalization / wrong-book / duplicate / invalid-odds rejection
- [x] Fresh-price timestamps and default conversion freshness gate
- [x] Exact conversion verifier: event / sport / market / line / period / side
- [x] Controlled legacy builder runner
- [x] Legacy builder sport/market/period safety gate
- [x] Verified browser-restoration playbook: SportyBet
- [x] Verified browser-restoration playbook: Bet9ja
- [x] Verified market-search browser playbook: SportyBet
- [x] Verified market-search browser playbook: Bet9ja
- [x] Browser-restored slip verifier
- [x] Restored-slip leg-count and combined-odds consistency checks
- [x] Restored booking-code → draft persistence tool
- [x] Rebuilt booking-code structural verifier with price-change separation
- [x] Rich market-aware SportyBet browser builder plan
- [x] Rich market-aware Bet9ja browser builder plan
- [x] Bookmaker browser-health service/tool separates configured playbooks from recently exercised behavior
- [x] SportyBet rich booking-code creation/reload — future public event built, restored in a clean browser session and structurally verified without wagering
- [x] Bet9ja rich booking-number creation/reload — controlled Dell browser acceptance passed without wagering
- [x] Live event/market/odds extraction — controlled SportyBet/Bet9ja runtime acceptance persisted fresh validated observations
- [x] Removed bookmaker names are rejected by resolve, health, restore, search, build, conversion and current-price comparison paths

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
- [x] Real end-to-end SportyBet → Bet9ja conversion/rebuild and separate SportyBet build/reload verification passed on Dell

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
- [x] Live SportyBet/Bet9ja browser extraction and fresh-price comparison runtime acceptance

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
- [x] Current official SportyBet/Bet9ja rules checked for representative tennis retirement, golf dead-heat/reduced-event and basketball overtime cases; per-market matching remains mandatory
- [x] Real production history reconciliation — the intentionally reset source contained zero picks/tickets and reconciled exactly with V2

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
- [x] GET-only sports/history `/api/v2/*` surface, with a separate narrow origin-checked push subscribe/unsubscribe boundary
- [x] Tests forbidding dashboard mutation methods
- [x] No PIN/write token/localStorage write-key in V2 app
- [x] Overview
- [x] Picks
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
- [x] Installable PWA manifest with PNG/maskable icons and install affordance
- [x] Service-worker offline application shell and update lifecycle
- [x] Opt-in Web Push subscription/delivery path with private VAPID key outside the repository
- [x] Mobile drawer backdrop click, Escape close and focus restoration; no visible X by owner direction
- [x] Final PWA install/push/mobile visual regression on Dell and owner-confirmed iOS notification display
- [x] Production history correctness after migration — zero source picks/tickets and the ₦30,000 bankroll reconciled exactly

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
- [x] Daily/weekly automation execution acceptance on Dell/OpenClaw
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
- [x] Fixed ten-minute automatic-result systemd heartbeat service/timer
- [x] Runtime preparation generates VAPID keys outside the repository and installs the settlement timer
- [x] Backup timer/job/browser-health behavior observed on the real Dell runtime
- [x] Security review on actual Dell/OpenClaw deployment

## Phase 16 — Installation / Test / Release Gate

**The requested V2.1 repository changes are now frozen for controlled Dell acceptance. Do not promote `v2` to `main` until the applicable runtime gates below pass.**

- [x] Full current V2.1 pytest suite — 234 pass locally and on the Dell/runtime
- [x] V1 database snapshot taken and verified
- [x] V1 → V2 migration rehearsal on actual data passes
- [x] Historical pick/ticket totals reconcile
- [x] Bankroll reconciles exactly
- [x] Strategy/compound/long-shot history reviewed
- [x] Sabi Boy OpenClaw final-tool-surface acceptance
- [x] Current-format Sabi Boy skill visibility acceptance on the real agent
- [x] Research Scout/Skeptic/Ticket Engineer OpenClaw acceptance — a live three-role fan-out persisted 16 evidence items and produced a conservative Sabi Boy synthesis
- [x] Persistent research-case resume across OpenClaw sessions verified
- [x] Learned-source discovery/verify/reuse workflow verified
- [x] Multi-sport research acceptance across representative sports
- [x] SportyBet browser restoration acceptance — a newly generated reusable code restored the exact event/market/selection/price in a separate clean browser session
- [x] Bet9ja browser restoration acceptance
- [x] SportyBet rich booking-code build/reload verification acceptance — `bookmaker.build.verify` matched the restored future-event slip exactly; no wager was placed
- [x] Bet9ja rich booking-number build/reload verification acceptance
- [x] At least one real end-to-end bookmaker conversion/rebuild pair passes
- [x] Multi-book fresh-price comparison acceptance
- [x] Bookmaker browser-health observations reflect live tests correctly
- [x] Settlement profile/live-bookmaker rule verification tested for tennis/racquet, golf/field and basketball overtime cases against current official SportyBet/Bet9ja rules
- [x] Dashboard mobile/desktop acceptance against migrated data
- [x] Advanced History ticket-version/price panels verified against real data
- [x] Blog migration/display acceptance — the V1 source contained zero diary posts, that zero count reconciled exactly, and the full V2 draft/publish/display/archive lifecycle passed
- [x] Daily/weekly OpenClaw reflection automation acceptance
- [x] Event-driven `blog.triggers` behavior acceptance
- [x] Job success/failure/retry/readiness behavior acceptance
- [x] Settlement duplicate/correction acceptance
- [x] Automatic result heartbeat settles supported score-derived picks/ticket legs idempotently and audits every change
- [x] Automatic settlement leaves unsupported props/rule-sensitive cases pending and never infers payouts
- [x] PWA install/offline/push acceptance — live HTTPS controls passed and the owner confirmed the delivered test notification appeared on iOS
- [x] Backup timer + backup/restore drill passes on Dell
- [x] External route/cutover rehearsal documented
- [x] Security/secrets review
- [x] Repository deployment runbook exists
- [x] Release-candidate notes exist
- [x] ChatGPT Work installation/testing handoff exists
- [x] Final V2 acceptance review — installed replacement is operational and all required original-plan acceptance gates have passing evidence
- [ ] Promote/merge `v2` to `main` according to Forgejo-first release workflow
- [x] Final production state recorded — V2 is already the active replacement and no additional cutover action is required; `main` remains unmerged

### Phase 16 Dell evidence — 2026-08-27

- Exact installed and acceptance-tested code commit: `fc51e9168a42b72a1f6585dd48f36b2cf6991f0f` (`v2`, V2.1.0.4). Forgejo `thathman/SabiAI` resolves `v2` to the same commit; `main` remains unmerged.
- Full Dell suite: 234 passed with one known Starlette deprecation warning. The staged release acceptance repeated the same 234-test result with no failed gates at this commit.
- Verified private recovery archives: `~/sabi-boy-migration-archives/20260826T071240Z/v1-prediction-workspace.tar.gz` and `v1-repository-and-service.tar.gz`; both gzip checks and recorded SHA-256 checksums passed.
- Migration/reconciliation: source and V2 both contained zero picks/tickets after the intentional V1 reset; the bankroll reconciled exactly at ₦30,000 with no migration warnings. The separate pre-reset private archive was reviewed for historical strategy/compound/long-shot records.
- Active runtime: the existing OpenClaw agent ID is `prediction`, with name/identity Sabi Boy, seven required current-format skills, 131 V2 tools, five preserved bindings and READY status.
- Live research: one case resumed across independent OpenClaw sessions; an official FIVB source was verified and reused without rediscovery; football, basketball, tennis and volleyball examples passed.
- Live worker fan-out: OpenClaw created research case `research_case_69a23ea20f2b7c9e3aab5193` for Liverpool vs Nottingham Forest, ran separate Research Scout, Skeptic and Ticket Engineer workers, persisted 16 evidence items, exposed conflicting conclusions and completed a conservative Sabi Boy reconciliation. The worker session IDs and completion states are present in the Dell OpenClaw session registry.
- Bookmakers: Bet9ja restore/build/reload and SportyBet-to-Bet9ja conversion passed without wagering. A fresh Borneo Samarinda vs Madura United comparison observed SportyBet 1.70 and Bet9ja 1.72. SportyBet then generated booking code `KW8SGW` for Crystal Palace vs Man City, 1X2 Away at 1.69; a separate clean browser session restored the exact slip and `bookmaker.build.verify` returned `verified=true`, `ready_to_return_code=true`, no price change and no issues. The fresh observation is persisted and SportyBet browser health now reports `recently_exercised`. By owner direction, all other bookmaker targets remain removed from the active registry/playbooks.
- V2.1 runtime validation: 234 tests pass both locally and on the Dell, including PWA manifest/service worker/push-origin controls, secure VAPID key generation, removed-bookmaker rejection, automatic result settlement, audit idempotence and fixed-timer installation.
- Controlled settlement/Blog drill: duplicate protection, audited correction, correction trigger, tennis/golf/basketball profiles and the Blog lifecycle passed. Current official [SportyBet sports rules](https://lite.sportybet.com/ng/help?nav=sports) and [Bet9ja sports terms](https://help.bet9ja.com/sport-tcs/) were checked for tennis retirement, golf dead heat/reduced events and basketball overtime. The profiles correctly continue to require exact bookmaker/market verification instead of assuming equivalence.
- Blog reconciliation: the reset V1 source contained zero diary posts, so zero were eligible to migrate; that count reconciled exactly. The V2 draft/publish/display/archive lifecycle passed independently.
- Dashboard/PWA: the public HTTPS app was accepted at 390×844 and 1440×900 with the exact V1 `S` assets, Sabi Boy branding, the browser title “Sabi Boy knows ball,” one-line page titles, the Picks label, backdrop-only drawer close, installable manifest and a controlling V2.1.0.4 service worker. The top bar now reserves `env(safe-area-inset-top)` for iOS standalone mode so the header is not hidden behind the device status area. Versioned asset URLs fixed a live stale-script/new-markup cache mismatch. The iOS bell gives Home Screen guidance outside standalone mode and calls `PushManager.subscribe()` directly from the installed-PWA tap. The latest clearly labelled notification test reached both active subscriptions: attempted 2, delivered 2, expired 0, failed 0; the owner then confirmed that the notification visibly appeared on iOS.
- Operations: daily and weekly OpenClaw jobs completed successfully and correctly skipped empty publication; readiness/failure recovery passed. The automatic-settlement timer is enabled/active and its current heartbeat exited successfully. Backup manifest `data/backups/sabi-boy/20260827T001550Z/manifest.json` verified both V1 and V2 checksums/integrity; a separate restore reached schema 8 with `PRAGMA quick_check=ok`.
- Security: loopback-only application binding, disabled API docs, host validation, security headers, mode-600 Sabi Boy environment/VAPID key, zero tracked private keys/recognized secret patterns and a clean installed-package audit passed. The legacy OpenClaw secrets drop-in was tightened from mode 664 to 600. The Sabi Boy route runs through `cloudflared.service` using a root-owned configuration and a mode-400 credentials file; its process arguments contain no token. Three unrelated host tunnel services still expose tokens in their process arguments and should be remediated in their own authorized maintenance window. No external Cloudflare route was changed.
- V1 service and active V1 working copies were removed only after archive verification. The V2 service now owns the original port and external route; `main` remains unmerged.
- The cutover finalizer accepts an already inactive/removed V1 systemd unit as the required stopped state; regression coverage prevents the final report from failing after deliberate V1 removal.
- Release status: **READY FOR FINAL RELEASE**. Every required original-plan runtime gate has passing evidence. The optional Parse SportyBet marketplace source remains unavailable until the owner completes Parse's phone/card access requirements and adds that API to the account; this is not a V2 release blocker. `v2` has not been merged to `main`.

### Phase 16 follow-up evidence — 2026-08-27 (cron/source hardening)

- Current Forgejo/Dell checkout: `dc98ad6f9b4faf891d492470b4ff0e66382bcb1c` on `v2`; untracked Dell runtime evidence remains preserved.
- Full Dell pytest suite at this checkout: **243 passed, 1 warning** (the existing Starlette/httpx deprecation warning).
- OpenClaw wake layer is installed for agent `prediction` (human identity Sabi Boy): daily picks 08:00 Africa/Lagos, source/readiness monitor every 30 minutes, daily reflection 22:30, weekly reflection Sunday 20:00. Announcement delivery is explicit Matrix room/account and was verified delivered by a manual source-health run.
- The ten-minute `sabi-boy-settlement.timer`, daily `sabi-boy-backup.timer`, and dashboard service are active. A manual settlement heartbeat completed successfully with zero source errors and no state changes.
- The two acceptance-probe research cases were closed as test artifacts, and the `dell_acceptance_probe` database job was disabled so it cannot recreate synthetic research.
- Live source checks succeeded for ESPN Public Data (Premier League slug `eng.1`), football-data.org, Parse ESPN, Parse Flashscore, Parse LiveScore and Parse SportyBet; TheSportsDB remains healthy. The read-only Sports Betting AI Analyzer key is configured but its validation request timed out; it is retained as an optional source and is not treated as authoritative or a release gate.
- After the broad no-wager daily-picks dry run, the source monitor correctly delivered an actionable Matrix alert: Flashscore had three caller-side `422` responses while one fixture call succeeded, and the optional Sports Betting AI Analyzer timed out. The overall system stayed **READY** with zero stale settlements, zero paid calls and no pick/ticket mutations; these are source-input/availability follow-ups, not an authorization to place a wager.
- Follow-up implementation commit `37280c96e4156276150aad56ab81ac9b65b22a87` moves source/readiness monitoring out of the model wake layer: `sabi-boy-health.service` / `sabi-boy-health.timer` read the local V2 database every 30 minutes and use Web Push only for changed actionable state. The timer is enabled and active on the Dell; its manual run completed successfully and delivered the current two-source warning to both subscribed push endpoints. No language-model or provider request is made by this check.
- The prior `sabi-boy-source-health` OpenClaw cron is retained only as a disabled historical record. The active agent jobs are daily picks plus the quiet daily/weekly reflections. The daily picks job is configured with Alibaba `aliyun-token-plan/qwen3.8-max-preview` and falls back to OpenCode `opencode-go/qwen3.7-max`; both models are available in the Dell's configured model list. The Dell suite at this commit is `248 passed, 1 warning` (known Starlette/httpx deprecation).
- Live model probe on the Dell (2026-08-28) completed successfully with `aliyun-token-plan/qwen3.8-max-preview`: response `MODEL_PROBE_OK`, provider/model reported as `aliyun-token-plan` / `qwen3.8-max-preview`, fallback not used, and approximately 14.4 seconds elapsed. The probe used 70,501 input and 31 output tokens because the prediction agent loads its full workspace/tool context; this is why only the daily research workflow is model-backed and local health/settlement timers remain model-free.
- Dashboard follow-up: commit `2883d27f0312deb1f3388fe264ea5bad28f4b39e` renames the navigation/page/article label to **Sabi's Blog**, fixes Finance to use the canonical read-only overview payload, bumps the PWA cache version to `2.1.0.6`, and passed the full Dell suite (**244 passed, 1 warning**). The active Dell dashboard was restarted and serves the new shell.

### Phase 16 follow-up evidence — 2026-08-28 (direct research wake)

- Implementation commits `b96c42e49129c611583221afc5c5dc68c28cc8ff`, `51de663`, `e5311da` and `026b139` move daily research/picks out of the OpenClaw agent. `sabi-boy-research.service` / `sabi-boy-research.timer` collect direct TheSportsDB/Parse SportyBet fixture and price data, call Alibaba Qwen directly, write `data/reports/daily-picks-latest.json`, and send Web Push. The timer is enabled/active on the Dell and pinned to 08:00 `Africa/Lagos` (07:00 UTC); the old `sabi-boy-daily-picks` OpenClaw cron is retained only as a disabled historical record.
- The direct Dell dry run completed successfully with 53 events, zero source failures, one validated Liverpool vs Nottingham Forest recommendation (SportyBet 1.57, 62% confidence), two Web Push deliveries and no wager/pick-ledger mutation. Direct model usage was 6,399 prompt / 2,186 completion tokens (versus the earlier 70,501-token full-agent probe); the recommendation report records the exact usage and delivery result.
- Full Dell pytest suite at the new runtime commit: **252 passed, 1 warning** (the existing Starlette/httpx deprecation warning). The remaining OpenClaw jobs are the quiet daily/weekly Blog reflections; health, settlement and daily research are system-owned.

### Phase 16 follow-up evidence — 2026-08-28 (pick and scan context)

- Implementation commit `e5705e4` adds the `history.picks` gateway read, returning canonical recorded pick rows (event, market, selection, decimal odds, confidence, rationale, bookmaker and outcome) so Sabi Boy can answer questions about picks without relying on dashboard-only data. The core skill now requires this read for specific pick questions and reserves `history.summary` for aggregates.
- Migration `0009_daily_research_runs.sql` and `DailyResearchLog` persist each successful direct scan, including run time, model, event count, source failures, recommendations, notes, model usage and push delivery. The gateway exposes `system.daily_research`, `research.scan.latest`, `research.scan.history` and `research.scan.context`; `system.readiness`/`system.health` include the latest scan, and `ticket.research.plan` includes recent scan context automatically.
- Dell verification after `e8c78f6`: the 2026-08-28 scan persisted run `2026-08-28T00:10:02.866181+00:00` with 53 events, zero source failures and three recommendations; `system.readiness`, `research.scan.context` and `ticket.research.plan` all returned the same latest scan context. The direct scan remained an unplaced observation and ticket research still requires fresh price/rule/evidence checks.
- Targeted gateway/research acceptance: **25 passed**. Local full suite at the follow-up implementation: **255 passed, 1 warning** (the existing Starlette/httpx deprecation warning).

### Phase 16 follow-up evidence — 2026-08-28 (notification history)

- Implementation commit `0113b2f` adds migration `0010_notification_history.sql`, records every system push event with user-facing message and aggregate delivery result, and deliberately excludes browser endpoints and encryption keys. The read-only dashboard exposes `GET /api/v2/notifications` and a dedicated Notifications page with delivered, failed, expired and unavailable states.
- PWA cache version advanced to `2.1.0.7` so the new page and service-worker shell cannot be hidden by the prior iOS cache. The active Dell dashboard was restarted from the Forgejo `v2` checkout and served `/notifications` successfully; the notification history endpoint currently returns an empty list until the next system push (prior pushes predate migration 0010).
- Local dashboard/PWA acceptance: **11 passed, 1 warning**. The full local suite at this commit: **257 passed, 1 warning** (the existing Starlette/httpx deprecation warning). Dell dashboard/PWA acceptance also passed **11 tests, 1 warning**.
- Branding follow-up commit `171074a1c14adb47a21fdb590a33b1ddbeabcbe6` replaces the font-rendered S with the exact V1 pixel-block S across the sidebar, favicon, legacy icon URL and all PWA/maskable icon responses. It also replaces the Notifications navigation emoji with the existing monochrome SVG bell and advances the PWA cache to `2.1.0.8`. The full local suite remains **257 passed, 1 warning**; Dell `https://picks.hendrix.com.ng/health` identifies Sabi Boy V2 and the routed `icon-192.png?v=2.1.0.8` returns the expected 192×192 RGB PNG.

### Phase 16 follow-up evidence — 2026-08-28 (strategy records and ownership)

- The V2-native strategy layer now builds three inspectable plans from each direct scan: Precision Picks, a daily 1.30 chain and a weekly 1000+ long shot. The long shot uses the recent multi-sport scan window, deduplicates events and never pads a slip with weak legs. Every plan carries its target, combined decimal odds, confidence, bounded stake suggestion, rationale and candidate legs.
- A ready daily chain or weekly long shot is materialized as a Sabi Boy strategy ticket with linked candidate tips and a single ticket stake. The ledger therefore records the strategy exposure once, while the dashboard keeps individual candidate legs distinguishable from the primary Sabi Boy picks. This is an internal record only; no bookmaker endpoint is called and no wager is placed.
- Pick ownership is explicit: the dashboard overview, performance charts, history and OpenClaw aggregate reads default to Sabi Boy picks; Hendrix records remain separately addressable through the `/hendrix` view and `owner=hendrix` filter. Strategy plans and learning are exposed through `strategy.plans` and `strategy.learning` plus the read-only `/api/v2/strategies/*` routes.
- V2-native bounded learning is now visible and queryable. The policy waits for eight settled examples before confidence changes and fifteen decided examples before a strategy policy is eligible for review; it can report gathering-sample, hold, review or eligible-to-expand without rewriting history or silently changing stakes.
- Automatic settlement now prefers a known TheSportsDB event ID and can conservatively resolve a non-TheSportsDB source by exact event-name/date search before fetching the final score. Ambiguous matches remain pending. Linked strategy ticket legs propagate their confirmed outcome to the corresponding candidate record with the same audited, idempotent settlement rules.
- Product version/cache advanced to `2.2.0.0` for the strategy and ownership surface. Local validation: **272 passed, 1 warning** (the existing Starlette/httpx deprecation warning), JavaScript syntax checks passed for the dashboard app and service worker, and `git diff --check` passed.
- Dell was safely fast-forwarded from Forgejo to `4bacfdbcb03d1d0255e7d6fc0b21cf508a5d3c50`; its user-level dashboard, research, settlement, health and backup units/timers are active. The Dell suite at the runtime parent `6ed444078f4cb6393b4da844795378bfc748479b` is **272 passed, 1 warning**. No unknown tracked changes were overwritten; only pre-existing runtime evidence remains untracked.
- Live HTTPS/PWA smoke passed: `/health` identifies Sabi Boy V2, `/api/v2/strategies/learning` returns the bounded policy, the shell title is `Sabi Boy knows ball`, `/strategies` renders the strategy board and learning policy, and `/hendrix` renders the separate Hendrix record. The expected strict CSP blocks an optional Cloudflare Insights script; application functionality remains healthy.
- Dell OpenClaw acceptance passed at the current checkout: agent `prediction` resolves to `/home/hendrix/.openclaw/workspace-prediction`, all seven current-format Sabi Boy skills are visible, the V2 gateway exposes 140 tools with no required-tool gaps, and readiness reports `READY`. The latest persisted direct scan remains available to Sabi Boy with three recommendations and two successful push deliveries.

### Phase 16 follow-up evidence — 2026-08-28 (daily research timer recovery)

- The scheduled daily research timer did fire at 08:00 `Africa/Lagos` (07:00 UTC), but the Alibaba `qwen3.8-max-preview` request timed out before producing a report. No picks or tickets were written by that failed attempt.
- Fix commit `6afc997ff325f29faf803eba927fabe62f5b65cf` adds a default same-credential Alibaba `qwen3.6-flash` fallback when no explicit fallback endpoint is configured, and caps fallback output at 1,600 tokens. Explicit `SABIAI_RESEARCH_FALLBACK_*` variables can still point at another direct provider.
- Follow-up commit `618965d25e7e8e36abc07bbd4247e228572cf2aa` records a failure notification and installs bounded systemd retry (`Restart=on-failure`, two-minute delay, two starts per 30 minutes). The installed Dell unit was refreshed through the runtime preparation script and the research timer remains active.
- A manual recovery run at 09:44 UTC completed at 09:46 UTC with the primary model: 53 events, three validated recommendations, one Sabi Boy Precision pick, one Daily 1.30 Chain ticket, three delivered push notifications and no external wager. The public overview and strategy routes now expose the new records.

### Phase 16 follow-up evidence — 2026-08-28 (same-day fixtures and chained stake progression)

- Fix commits `eca09c990d3a99ca3e4b2aacd430a9600b4fd856`, `40be539265c27ace5d7c813aaf79628e7870594a`, `8b37498be9c72308172f976fb4e914d14e3981b6` and `2d6c9061cb31c4ccf3bc32c991685739283b8e8e` are the current tested `v2` candidate (HEAD `2d6c9061cb31c4ccf3bc32c991685739283b8e8e`) and are pushed to both Forgejo `v2` and GitHub `main` by a non-forced fast-forward from GitHub `f90b46a85c5d95385178cb845ac7140e9296e24b`.
- Daily fixture collection now rejects any event whose parsed start date is not the requested `Africa/Lagos` calendar date (including provider responses that ignore their date parameter). ISO, date-only, epoch-seconds and epoch-milliseconds timestamps are supported; events with an unknown start date are excluded rather than sent to the model, preventing future fixtures from repeating across daily runs.
- The Daily 1.30 Chain now has V2-native durable state: one eligible chain ticket per daily wake, Day N stake equals the previous fully won ticket's payout, a loss resets to the configured base stake and Day 1, void/partial results do not advance the chain, and a 30-win cycle is recorded before the next daily wake starts a new cycle.
- Chain state is visible through `GET /api/v2/strategies/chain`, the `strategy.chain` OpenClaw read, and the dashboard Strategies page. Existing pre-chain pending tickets are reconciled on the first post-migration daily wake: their ticket/leg history is retained, the stale exposure is voided, and its stake is refunded exactly once rather than being adopted as today's chain position.
- Local regression evidence at this commit: **282 passed, 1 warning** (the existing Starlette/httpx deprecation warning). Coverage includes date parsing/filtering, per-sport fallback, chain compounding, loss reset, 30-day completion/restart, calendar-day locking, stale-ticket reconciliation, settlement payout repair and API persistence.
- This code push does not itself claim a fresh Dell deployment or a green final-release gate; the Dell must pull this exact SHA through the controlled runtime workflow before its timers use the date/chain fixes.
- A read-only second-model review identified and the fix commit closes four correctness gaps: per-sport source fallback after Parse failure, one chain ticket per calendar date, safe void/refund reconciliation for pre-chain pending tickets, and retry-safe payout/chain side effects when a SQLite lock interrupts settlement.

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
