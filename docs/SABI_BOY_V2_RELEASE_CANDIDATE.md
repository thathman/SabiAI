# Sabi Boy V2 — Installation/Test Release Candidate

**Branch:** `v2`  
**Human-facing product:** Sabi Boy  
**OpenClaw agent ID:** `prediction`
**Candidate status:** Repository development complete; Dell/OpenClaw/live-browser acceptance pending.  
**Promotion status:** **Do not merge to `main` yet.**

This document describes the V2 code candidate that is ready to enter installation and runtime testing. It is not a claim that production acceptance has passed.

## Product boundary

Sabi Boy V2 is an OpenClaw-native, broad multi-sport sports-intelligence assistant and Ticket Workshop.

Sabi Boy/OpenClaw handles sports research, source discovery, bookmaker research, ticket intake/editing/conversion/rebuild, settlement/history writes and Sabi Boy Blog writes.

The dashboard is intentionally read-only and is only about **our** records: games/picks, tickets, streaks, bankroll, performance, strategies, ticket-version history, observed bookmaker-price history and Sabi Boy Blog. It is not a generic scores/fixtures/news site.

User-facing language remains explicit and simple: named participants, Win/Lose/Draw, clear markets such as `Over 2.5 goals` or `Arsenal +1.5 handicap`, and decimal odds only.

## What is complete in the repository

### Core / storage

- canonical V2 event/participant/sport/market/ticket/pick/history model;
- deterministic V1 → V2 migration and reconciliation framework;
- lossless legacy archive for unmapped V1 rows;
- bankroll ledger and reconciliation;
- ticket draft/version lineage;
- research evidence persistence;
- persistent named research cases across workers/sessions;
- bookmaker offer/price observations;
- durable learned-source registry;
- settlement audit/history;
- Sabi Boy Blog persistence.

### Free-first research

- fresh-cache reuse;
- in-flight duplicate-request coalescing;
- TheSportsDB/ESPN/free-tier football-data adapters where configured;
- provider-specific source identity isolation;
- form, home/away form, H2H, injuries/availability helpers and match snapshots;
- broad sport registry and unknown-sport discovery;
- persistent source discovery: candidate → verify/reject/retire → health/reuse;
- paid-source access remains gated and must have an explicit reason.

Source depth is intentionally open-ended. A niche league can be researched through verified public/official sources and OpenClaw Browser/Search rather than being classified as unsupported.

### Market / settlement understanding

- 1/X/2 and explicit named winner language;
- Double Chance and Draw No Bet;
- handicap/spread normalization;
- totals/team totals;
- cards/corners/shots/player/count markets;
- half/quarter/set/map/frame/period handling;
- race/field core: outright winner, Top-N finish, podium, make/miss the cut and group winner;
- expanded settlement fingerprints;
- sport-level settlement profiles that flag bookmaker-specific verification needs for overtime, retirement, dead heat, forfeits and format changes.

Exact bookmaker policy values are not guessed. They remain live-verification data.

### Ticket Workshop

- text/plain instruction intake;
- restored booking-code normalization;
- screenshot/X ingestion path through OpenClaw vision/browser;
- remove/keep/replace/change market;
- split and trim;
- strongest-N from actual research ranking;
- lower-risk planning;
- candidate-version comparison;
- higher-odds versions only from fresh exact observed replacement offers;
- persistent `draft_id` support for common workflows;
- complete parent/child lineage.

### Bookmakers

- stable SportyBet, Bet9ja, Stake and 1xBet identities;
- exact event/market/line/period search plans;
- multi-book fresh-price comparison;
- strict conversion validation;
- fresh-price gating;
- price-observation lineage;
- browser restore/search playbooks for supported books;
- rich SportyBet/Bet9ja booking-code build plans;
- generated-code reload and structural verification;
- browser-health reporting separates `configured` from `recently exercised`.

**Live-dependent boundaries:**

- SportyBet and Bet9ja build/restore/search must still be proven against the current live pages.
- Stake reusable booking-code creation is not claimed until a current accessible flow is verified.
- 1xBet restore/search/build remains discovery-only until the configured regional public flow is verified.
- No browser workflow may bypass CAPTCHA, authentication or access controls.
- Booking-code creation is not wager placement. Runtime testing must not spend money or place a wager.

### History / dashboard

Read-only history includes:

- overall outcomes and win rate;
- bankroll and betting P/L;
- streaks;
- sport, competition, market, bookmaker and strategy breakdowns;
- odds bands and ticket-size performance;
- ticket killers;
- original/edited/conversion parent→child outcomes;
- historical observed bookmaker price movement;
- historical cross-book price disagreement;
- Sabi Boy Blog.

The History UI now shows the advanced parent→child and bookmaker-price read models while preserving the read-only boundary.

### Sabi Boy Blog

- draft/publish/archive;
- continuity with prior posts/history;
- daily and weekly OpenClaw reflection automation installer;
- event-driven trigger evaluator for settlement corrections, meaningful streaks, one-leg ticket killers, newly verified sources, busy result windows and notable recorded bookmaker-price disagreement;
- scheduled jobs may skip publication when nothing meaningful happened.

RSS/Atom is deliberately deferred because it is not required for V2 acceptance and currently has no confirmed consumer.

### Reliability / operations

- READY / DEGRADED / OBSERVE ONLY / ACTION LOCKED states;
- source/API-economy health;
- settlement backlog checks;
- durable job start/success/failure/consecutive-failure bookkeeping;
- verified SQLite backup/checksum/restore;
- daily systemd user backup timer with conservative retention;
- checkout-portable runtime preparation;
- guarded staging on a separate loopback port before the approved in-place replacement;
- fail-closed OpenClaw agent/workspace/skill/final-tool-surface acceptance;
- guarded OpenClaw activation;
- external-route finalizer;
- explicit rollback.

## Schema migrations included

The V2 initialization applies the base schema and repository migrations in order. Current migration files include:

- `0002_source_cache.sql`
- `0003_ticket_drafts.sql`
- `0004_legacy_archive.sql`
- `0005_bookmaker_offer_observations.sql`
- `0006_research_cases.sql`
- `0007_source_discoveries.sql`

Do not manually edit migration history during installation. A migration/reconciliation discrepancy is a release blocker and should be fixed in code with a regression test.

## OpenClaw runtime contract

Current-format skill packages required by acceptance:

- `sabi-boy-core`
- `sabi-boy-bookmaker-workflows`
- `sabi-boy-research-scout`
- `sabi-boy-skeptic`
- `sabi-boy-ticket-engineer`
- `sabi-boy-records`
- `sabi-boy-blog`

The human-facing identity is Sabi Boy. The existing machine identity remains `prediction` for compatibility with the Dell's bindings.

`scripts/sabi_v2_openclaw_acceptance.py` is the authority for the required final V2 tool surface. It includes durable research cases, source learning, verified ticket variants, settlement profiles, bookmaker browser health, advanced history and Blog triggers in addition to the earlier research/bookmaker/build tools.

## Test status

A broad regression suite is committed for the V2 code, including migration, source service/coalescing, learned sources, persistent research cases, market language, settlement profiles, ticket candidates, bookmaker conversion/build verification, advanced analytics, Blog triggers, job tracking, dashboard read-only behavior and OpenClaw acceptance parsing/tool requirements.

**The full current suite has not been declared green on the Dell in this development phase.** That is the first installation/testing gate. The candidate must not be promoted based only on committed tests.

## Required runtime acceptance before promotion

The authoritative checklist is Phase 16 in `docs/SABIAI_V2_TASKS.md`. It includes:

- full current pytest suite;
- verified V1 snapshot and migration rehearsal on actual data;
- exact history and bankroll reconciliation;
- real OpenClaw final-tool/skill/subagent acceptance;
- persistent research case and learned-source resume/reuse tests;
- representative multi-sport research;
- real SportyBet/Bet9ja restore/search/build/reload checks;
- Stake restore/search where accessible;
- at least one real booking-code conversion/rebuild pair without placing a wager;
- fresh multi-book price comparison;
- settlement-policy verification examples;
- desktop/mobile dashboard acceptance against migrated history;
- Blog automation/trigger checks;
- job failure/readiness checks;
- backup timer + restore drill;
- security/secrets review;
- cutover rehearsal.

## Failure policy

Do not work around a failed acceptance gate by editing the report or disabling the check.

If installation/testing finds a defect:

1. keep V1 intact until its data, migration and recovery archives are verified;
2. stop/rollback V2 if integrity is affected;
3. fix the defect on `v2`;
4. add/regress the failing case;
5. rerun the affected checks and then the full applicable acceptance suite;
6. record the fix and evidence.

Never force-reset an unknown working tree, rewrite published history or silently repoint an unrelated OpenClaw agent.

## Next document

ChatGPT Work should execute the installation/testing phase using:

`docs/SABI_BOY_V2_WORK_HANDOFF.md`

and the detailed deployment mechanics in:

`docs/SABI_BOY_V2_DEPLOYMENT.md`
