# SabiAI V2 Build Plan

> **Status:** Authoritative implementation roadmap  
> **Development branch:** `v2`  
> **Product definition:** `docs/SABIAI_V2_PRODUCT_BIBLE.md`

---

# 1. Development Rule

`v2` is the main development branch for SabiAI V2 until the V2 build is complete and approved.

`main` remains the stable V1 line during development.

All V2 work must be planned against the V2 Product Bible and must not silently change the product definition.

Recommended flow:

```text
main
  |
  +-- v2                  <- long-lived V2 integration/development branch
       |
       +-- feature/...    <- optional short-lived implementation branches
       +-- fix/...
       +-- refactor/...
```

Feature/fix branches should merge back into `v2`, not `main`.

When V2 is complete:

1. run full local acceptance testing;
2. validate migration/rollback;
3. validate OpenClaw integration;
4. validate dashboard history/statistics;
5. validate bookmaker/ticket workflows;
6. validate source fallbacks;
7. prepare release notes;
8. merge/promote `v2` to `main` only after the release gate passes.

No GitHub Actions are required for this project. Testing and release validation should run locally/on the controlled staging environment.

---

# 2. Build Objective

Transform the current SabiAI system into an OpenClaw-native, broad-sports betting research and ticket intelligence agent while preserving and improving the useful V1 history, bankroll, strategies, settlement and read-only dashboard.

The build has five major layers:

```text
1. OpenClaw Sabi
2. Research + Sports Knowledge
3. Bookmakers + Markets + Tickets
4. History + Settlement + Learning
5. Read-only Dashboard + Blog
```

The V2 build is complete only when these layers operate as one coherent system.

---

# 3. Architectural Direction

## 3.1 Keep one Sabi identity

Do not turn each sport into a separate product or permanent bot.

Sabi is the one OpenClaw agent.

Temporary specialist workers may help with research, source discovery, bookmaker lookup or review.

## 3.2 Move business rules out of the dashboard

The existing dashboard application is too large and owns too much logic.

V2 should split domain logic from presentation.

Suggested structure:

```text
sabiai/
  core/
    config.py
    types.py
    errors.py
    time.py

  domain/
    sports/
    competitions/
    participants/
    events/
    markets/
    selections/
    odds/
    research/
    tickets/
    picks/
    bankroll/
    settlement/
    performance/
    blog/

  sources/
    registry.py
    cache.py
    official/
    public_web/
    datasets/
    search/

  bookmakers/
    base.py
    registry.py
    sportybet/
    bet9ja/
    one_x_bet/
    stake/
    ...

  research/
    orchestrator.py
    sport_profiles/
    evidence.py
    source_discovery.py

  tickets/
    parser.py
    normalizer.py
    editor.py
    splitter.py
    target_odds.py
    converter.py
    builder.py
    lineage.py

  pricing/
    compare.py
    arbitrage.py
    rules.py

  records/
    repository.py
    settlement.py
    stats.py

  openclaw/
    tools/
    skills/
    workers/

  dashboard/
    app.py
    routes/
    views/
    api/

  jobs/
    scheduler.py
    settlement.py
    research_refresh.py
    blog.py
    backups.py
```

This does not require microservices. One deployable application is acceptable.

## 3.3 One canonical operational database

V2 should stop relying on multiple operational databases that can drift.

Initial target: one canonical SQLite database if that remains reliable for the current single-host deployment.

Design repositories/interfaces so migration to PostgreSQL later does not require rewriting the application.

Large historical odds/research snapshots may eventually move to a history-oriented store such as Parquet/DuckDB, but that is not a blocker for V2.

---

# 4. Canonical Data Model

The V2 schema should be designed before major feature coding.

Core entities:

## Sports and identity

- `sports`
- `competitions`
- `seasons`
- `participants` (teams/players where useful)
- `participant_aliases`
- `events`
- `event_aliases`
- `source_event_mappings`

## Markets and odds

- `market_definitions`
- `event_markets`
- `selections`
- `bookmakers`
- `bookmaker_market_mappings`
- `odds_snapshots`
- `bookmaker_rules`

## Research

- `sources`
- `source_capabilities`
- `research_runs`
- `research_evidence`
- `team_news`
- `injury_status`
- `source_health`

## Our betting history

- `picks`
- `tickets`
- `ticket_legs`
- `ticket_versions`
- `ticket_lineage`
- `strategies`
- `settlements`
- `bankroll_ledger`

## Sabi content

- `blog_posts`
- `blog_categories`
- `blog_tags`
- `blog_relations`

## Operations

- `jobs`
- `job_runs`
- `paid_api_usage`
- `system_events`

Existing V1 tables should be migrated into these structures without losing history.

---

# 5. Status Vocabulary

V2 must standardize record states.

## Pick/ticket leg result

- `pending`
- `won`
- `lost`
- `draw`
- `void`
- `cancelled`

## Ticket result

- `pending`
- `won`
- `lost`
- `void`
- `partial` where necessary for complex bookmaker settlement cases

## Research/source health

- `healthy`
- `stale`
- `degraded`
- `unavailable`

User-facing labels must remain simple: Won, Lost, Draw, Void, Pending.

---

# 6. Phase 0 — Freeze, Audit and Migration Map

## Goal

Understand exactly what V1 already does and prevent accidental loss during refactor.

## Tasks

- [ ] inventory all current scripts;
- [ ] inventory all cron/systemd/OpenClaw jobs;
- [ ] inventory all current SQLite databases and tables;
- [ ] document every dashboard route and API endpoint;
- [ ] document current strategy flows: Kelly, Compound, Long Shot, Live;
- [ ] document current bookmaker dependencies;
- [ ] document current paid/free data sources;
- [ ] identify duplicate code and duplicate data stores;
- [ ] identify current environment variables/secrets;
- [ ] map V1 tables to V2 schema;
- [ ] back up all current databases;
- [ ] create repeatable migration fixture using a copy of production data;
- [ ] document rollback procedure.

## Exit gate

- Full V1 inventory exists.
- No current history can be lost by planned migration.
- Every V1 scheduled job has an explicit V2 disposition: keep, replace or retire.

---

# 7. Phase 1 — Core Domain Foundation

## Goal

Create a clean foundation before adding new capabilities.

## Tasks

- [ ] create V2 package structure;
- [ ] centralize configuration;
- [ ] implement canonical IDs;
- [ ] create shared repository/data-access layer;
- [ ] implement canonical sport/competition/team/player/event models;
- [ ] implement alias resolution;
- [ ] implement canonical market/selection models;
- [ ] implement bookmaker registry;
- [ ] implement ticket/pick models;
- [ ] implement result/status vocabulary;
- [ ] implement bankroll ledger service;
- [ ] implement database migration framework;
- [ ] add schema tests;
- [ ] add migration tests.

## Important rule

The dashboard, OpenClaw tools and background jobs must use these services rather than direct ad-hoc SQL wherever practical.

## Exit gate

A single test event can be created, mapped to two external source names, given markets/odds, added to a ticket, settled and displayed from the shared domain layer.

---

# 8. Phase 2 — OpenClaw Core Integration

## Goal

Make Sabi an OpenClaw-first agent instead of a script wrapper.

## Tasks

- [ ] rewrite/replace Sabi skill instructions around V2 product bible;
- [ ] define Sabi’s plain-language rules;
- [ ] define decimal-odds-only rule;
- [ ] define explicit team/selection naming rule;
- [ ] define free-first research doctrine;
- [ ] define broad-sports doctrine;
- [ ] define dashboard read-only boundary;
- [ ] expose domain tools to OpenClaw;
- [ ] integrate AI Spine memory/search/message bus;
- [ ] add Sabi memory rules for durable sports/source lessons;
- [ ] add temporary specialist-worker pattern;
- [ ] add skeptic/reviewer worker;
- [ ] add heartbeat tasks for useful awareness;
- [ ] ensure exact scheduled jobs remain scheduler/cron tasks rather than heartbeat assumptions.

## Initial tool families

- `sports.*`
- `research.*`
- `bookmaker.*`
- `market.*`
- `ticket.*`
- `record.*`
- `history.*`
- `blog.*`
- `system.*`

## Exit gate

Sabi can answer a test request using native tools without being instructed to manually execute a particular script or query the database directly.

---

# 9. Phase 3 — Free-First Source Layer

## Goal

Make public/free information acquisition the default behavior.

## Tasks

- [ ] implement Source Registry;
- [ ] classify each source as free/open/paid;
- [ ] record sport/competition/data coverage;
- [ ] implement cache with freshness rules;
- [ ] implement official-source adapters;
- [ ] implement public structured endpoint adapters;
- [ ] implement public page reader/scraper adapters;
- [ ] integrate OpenClaw browser fallback;
- [ ] integrate search fallback;
- [ ] implement source discovery workflow;
- [ ] implement source health checks;
- [ ] implement paid API gate;
- [ ] log paid calls and reasons;
- [ ] avoid duplicate paid calls using cache;
- [ ] add source fallback tests;
- [ ] add stale-data tests.

## Free-first decision flow

```text
Have fresh local data?
  yes -> use it
  no  -> public/open source
          -> official site/feed
          -> public web source
          -> browser/search
          -> alternate free source
          -> only then paid fallback
```

## Exit gate

For a representative set of sports, Sabi can complete ordinary form/result/team-news research without requiring a paid API call.

---

# 10. Phase 4 — Sports Registry and Broad Coverage Framework

## Goal

Remove the current hard-coded narrow sport assumptions.

## Tasks

- [ ] implement Sports Registry;
- [ ] implement pluggable sport profiles;
- [ ] define event structure per sport;
- [ ] define common stats per sport;
- [ ] define common markets per sport;
- [ ] define research checklist per sport;
- [ ] define result/settlement behavior per sport;
- [ ] add source recommendations per sport;
- [ ] allow sport profiles to be added without changing core logic.

## First-wave sport profiles

Build deeply enough to prove the architecture:

1. Football
2. Basketball
3. Volleyball
4. Tennis
5. Table Tennis
6. Baseball
7. Ice Hockey
8. Cricket
9. Esports
10. Golf

## Second-wave profiles

- Handball
- Rugby
- Darts
- Snooker
- Badminton
- MMA
- Boxing
- Motorsport
- Cycling
- Futsal
- Water polo
- Beach volleyball
- Padel
- Floorball
- Aussie rules

Second-wave sports do not all need identical analytical depth before V2 release, but the architecture must accept them cleanly.

## Exit gate

Adding a new sport profile does not require editing football-specific core code.

---

# 11. Phase 5 — Market Interpreter

## Goal

Make Sabi understand equivalent markets across bookmakers and sports.

## Tasks

- [ ] define canonical market families;
- [ ] define period/scope model;
- [ ] define handicap/line representation;
- [ ] define player/team/event scope;
- [ ] build alias/synonym mappings;
- [ ] normalize common bookmaker labels;
- [ ] store bookmaker-specific market mappings;
- [ ] detect ambiguous markets;
- [ ] handle overtime/extra-time distinctions;
- [ ] handle tennis retirement/void distinctions;
- [ ] handle esports map/format distinctions;
- [ ] handle golf dead-heat/field rules where needed;
- [ ] build test corpus of real bookmaker market names.

## Core market families

- win/draw/loss;
- double chance;
- handicap;
- totals;
- team totals;
- set/frame/map;
- corners;
- cards;
- shots;
- player props;
- count markets;
- race/field placement markets;
- sport-specific extensions.

## Exit gate

Equivalent markets from at least three bookmakers normalize to the same canonical meaning and non-equivalent markets are not falsely matched.

---

# 12. Phase 6 — Research Engine V2

## Goal

Make research independent, market-aware and reusable.

## Tasks

- [ ] build research request object;
- [ ] determine research checklist from sport + market;
- [ ] fetch recent form;
- [ ] fetch home/away splits where relevant;
- [ ] fetch H2H where useful;
- [ ] fetch injury/availability/team news;
- [ ] fetch expected lineup/roster where available;
- [ ] fetch schedule/rest/context;
- [ ] fetch market-specific statistics;
- [ ] store evidence with source/time;
- [ ] reuse cached evidence across multiple ticket legs;
- [ ] support conflicting-source notes;
- [ ] produce plain-language summary;
- [ ] integrate skeptic/reviewer pass for important/uncertain cases;
- [ ] support “I could not confirm X yet” rather than inventing data.

## Market-aware examples

- football cards -> referee/cards/fouls/context;
- football corners -> corners/crosses/pressure;
- basketball rebounds -> player minutes/role/rebound environment;
- volleyball handicap -> set performance;
- tennis -> surface/serve-return/fatigue;
- esports -> patch/roster/maps/format;
- golf -> course/weather/tee wave.

## Exit gate

A research run can produce a sourced, timestamped evidence packet and a clear user-facing explanation for multiple sports and market types.

---

# 13. Phase 7 — Bookmaker Adapter Framework

## Goal

Create a clean path for bookmaker search, ticket import and ticket creation.

## Tasks

- [ ] define bookmaker adapter interface;
- [ ] define capability flags;
- [ ] implement event search;
- [ ] implement market search;
- [ ] implement decimal odds extraction;
- [ ] implement booking-code import where possible;
- [ ] implement booking-code creation where possible;
- [ ] implement slip state parsing;
- [ ] implement bookmaker rule metadata;
- [ ] implement resilient browser fallback for public pages;
- [ ] implement throttling/cache;
- [ ] create adapter tests using saved fixtures/screenshots/pages where legally/technically appropriate.

## Priority adapters

1. SportyBet
2. Bet9ja
3. 1xBet
4. Stake

Then add other bookmakers based on actual use and public accessibility.

## Capability example

```text
SportyBet
- search events: yes
- read odds: yes
- import booking code: yes
- create booking code: target capability
- public browser access: yes/variable
```

Do not assume every bookmaker supports every function.

## Exit gate

At least two bookmakers can resolve the same event/market through the canonical event/market layer.

---

# 14. Phase 8 — Ticket Workshop Core

## Goal

Deliver the flagship ticket manipulation workflows.

## Tasks

### Import
- [ ] booking-code importer;
- [ ] screenshot importer using vision;
- [ ] copied-text parser;
- [ ] bookmaker-share text parser;
- [ ] X post parser where accessible;
- [ ] plain instruction parser.

### Normalize
- [ ] resolve bookmaker;
- [ ] resolve events;
- [ ] resolve home/away teams;
- [ ] normalize market labels;
- [ ] normalize decimal odds;
- [ ] detect duplicates;
- [ ] identify unresolved legs.

### Edit
- [ ] remove selection;
- [ ] replace selection;
- [ ] change market;
- [ ] preserve locked selections;
- [ ] exclude requested sports/leagues;
- [ ] “keep strongest N” workflow;
- [ ] “make lower odds” workflow;
- [ ] “make higher odds” workflow.

### Split
- [ ] split evenly by count;
- [ ] split by requested number of slips;
- [ ] distribute stronger/weaker selections;
- [ ] preserve selected combinations;
- [ ] calculate resulting combined odds.

### Target odds
- [ ] trim toward requested combined odds;
- [ ] support minimum number of games;
- [ ] support selections that must remain;
- [ ] compare candidate ticket versions;
- [ ] explain changes plainly.

### Lineage
- [ ] persist original ticket;
- [ ] persist edits/versions;
- [ ] parent/child relation for split tickets;
- [ ] preserve Sabi recommendation notes.

## Exit gate

Given a real saved ticket fixture, Sabi can import it, remove games, change a market, split it and produce traceable ticket versions with recalculated combined decimal odds.

---

# 15. Phase 9 — Ticket Conversion and Booking-Code Creation

## Goal

Convert normalized tickets between supported bookmakers and create usable booking codes where technically supported.

## Tasks

- [ ] source-bookmaker ticket import;
- [ ] target-bookmaker event matching;
- [ ] equivalent-market matching;
- [ ] target price retrieval;
- [ ] missing-market handling;
- [ ] closest-equivalent suggestion;
- [ ] target slip build;
- [ ] booking-code extraction/creation;
- [ ] final ticket verification;
- [ ] conversion history.

## Required UX

Show:

- original bookmaker;
- target bookmaker;
- unchanged selections;
- changed/unavailable selections;
- original combined odds;
- new combined odds;
- final booking code.

## Exit gate

At least one supported cross-bookmaker conversion path works end to end in staging with real current events.

---

# 16. Phase 10 — Odds Search, Comparison and Arbitrage

## Goal

Let Sabi independently compare bookmaker prices and find genuine cross-book differences.

## Tasks

- [ ] timestamp all collected prices;
- [ ] canonicalize event/market/selection before comparison;
- [ ] show best price by bookmaker;
- [ ] detect stale prices;
- [ ] calculate two-outcome opportunities;
- [ ] calculate three-outcome opportunities;
- [ ] support N-outcome calculation;
- [ ] verify bookmaker settlement-rule compatibility;
- [ ] calculate stake split from chosen total amount;
- [ ] include price age;
- [ ] detect price movement during verification;
- [ ] reject mismatched market false positives;
- [ ] log found opportunities for later analysis.

## Later extensions

- middles;
- stale-line detection;
- market outliers;
- exchange/bookmaker combinations;
- related-market inconsistencies.

## Exit gate

Saved multi-bookmaker fixtures prove that true matching opportunities are detected and common false matches are rejected.

---

# 17. Phase 11 — Settlement and History Reliability

## Goal

Make historical performance trustworthy.

## Tasks

- [ ] replace fragmented settlement paths with one settlement service;
- [ ] map final event results to all relevant picks/ticket legs;
- [ ] support sport-specific scoring/results;
- [ ] support Won/Lost/Draw/Void/Pending;
- [ ] settle ticket result from legs;
- [ ] handle postponed/cancelled events;
- [ ] preserve bookmaker-specific void cases;
- [ ] implement manual correction with audit trail;
- [ ] add settlement backlog monitoring;
- [ ] add duplicate-settlement protection;
- [ ] reconcile bankroll ledger from settled records;
- [ ] add consistency checks.

## Exit gate

A representative historical test set settles deterministically, and rerunning settlement does not duplicate bankroll events.

---

# 18. Phase 12 — Historical Insight Layer

## Goal

Turn our accumulated data into useful plain-language monitoring.

## Measures to compute

- overall Won/Lost/Draw;
- win percentage;
- profit/loss;
- bankroll change;
- current streak;
- longest winning streak;
- longest losing streak;
- results by sport;
- results by competition;
- results by market;
- results by bookmaker;
- results by strategy;
- results by decimal-odds band;
- results by ticket size;
- results by combined-odds range;
- singles vs multi-game tickets;
- ticket-killer frequency;
- edited vs original ticket outcomes where both can be observed;
- Sabi-built vs imported tickets;
- screenshot/X/code/instruction ticket sources;
- selected confidence ranges versus actual outcomes, displayed in plain language.

## Exit gate

All dashboard metrics can be derived from canonical V2 records and reconcile against the bankroll ledger.

---

# 19. Phase 13 — Read-Only Dashboard V2

## Goal

Refactor the dashboard into a focused visual monitor of our own history.

## Non-negotiable boundary

Do not add a general sports portal, fixture browser, injury center, bookmaker explorer or betting-action buttons to the dashboard.

Those are Sabi/OpenClaw capabilities.

## Pages

### Overview
- current bankroll;
- total profit/loss;
- today/week/month;
- Won/Lost/Draw;
- current streak;
- best/worst streak;
- pending count;
- stake in play where tracked;
- recent games;
- recent tickets;
- latest blog post;
- key graphs.

### Games / Picks
Our actual recorded selections.

### Tickets
Our ticket history, ticket versions, splits and killers.

### Performance
Charts only from our own historical data.

### Finance
Bankroll and money history.

### Strategies
Kelly / Compound / Long Shot / Live / future strategies.

### History
Full archive with filters/search.

### Blog
Sabi’s blog.

### System
Read-only maintenance/health data.

## Chart set

- bankroll over time;
- profit/loss over time;
- win percentage trend;
- W/L/D counts over time;
- sport performance;
- market performance;
- bookmaker performance;
- strategy performance;
- odds-band performance;
- ticket-size performance;
- combined-odds-range performance;
- streak timeline;
- ticket killer counts.

## Dashboard implementation tasks

- [ ] split current monolithic `dashboard/app.py`;
- [ ] preserve current visual identity where useful;
- [ ] remove/retire write-token pattern from browser;
- [ ] eliminate dashboard mutations;
- [ ] create read-only APIs;
- [ ] add pagination/filtering;
- [ ] mobile-first responsive review;
- [ ] PWA regression test;
- [ ] accessibility basics;
- [ ] chart data validation;
- [ ] cache expensive aggregates.

## Exit gate

A user can fully understand our history and trends from the dashboard without the dashboard becoming a sports-information website or action interface.

---

# 20. Phase 14 — Sabi Blog

## Goal

Turn the diary into a continuing Sabi-written blog.

## Tasks

- [ ] create blog schema;
- [ ] migrate useful diary entries;
- [ ] create categories/tags;
- [ ] create blog publication service;
- [ ] create OpenClaw blog-writing tool;
- [ ] create daily/weekly prompts;
- [ ] link posts to our own picks/tickets/sports where useful;
- [ ] render blog index;
- [ ] render article pages;
- [ ] add related posts;
- [ ] add RSS/Atom feed if easy;
- [ ] add blog search/filter;
- [ ] add draft mode if needed;
- [ ] ensure posts are not generic filler.

## Suggested schedules

- Daily: short optional reflection when something worth writing happened.
- Weekly: “What I learned this week.”
- Event-driven: interesting streak, unusual ticket, strategy milestone, major mistake, new sport discovery.

## Exit gate

Sabi can independently generate and publish a useful post grounded in our actual history and/or its documented research, and the post appears on the read-only site.

---

# 21. Phase 15 — Reliability, Security and Operations

## Goal

Make V2 dependable enough for daily use.

## Tasks

### Jobs
- [ ] job registry;
- [ ] last success/failure;
- [ ] retry rules;
- [ ] settlement backlog;
- [ ] stale-source detection;
- [ ] backup freshness;
- [ ] database integrity checks.

### Security
- [ ] remove default PIN behavior;
- [ ] remove PIN in GET query;
- [ ] remove long-lived browser write key/localStorage design;
- [ ] ensure dashboard is read-only;
- [ ] protect internal mutation endpoints;
- [ ] keep bookmaker credentials/session material server-side;
- [ ] sanitize logs;
- [ ] audit sensitive configuration.

### Backups
- [ ] automatic DB backups;
- [ ] retention policy;
- [ ] restore test;
- [ ] migration rollback test.

### Observability
- [ ] source health;
- [ ] source freshness;
- [ ] bookmaker adapter health;
- [ ] research failures;
- [ ] settlement backlog;
- [ ] scheduled job health;
- [ ] paid API usage;
- [ ] cache hit rate;
- [ ] DB size/growth;
- [ ] blog job health.

## Exit gate

A maintenance page can explain whether the system is healthy without inspecting logs manually, and a tested backup can restore the operational database.

---

# 22. Phase 16 — Breadth Expansion

## Goal

Use the V2 framework to continuously expand Sabi’s sports and bookmaker knowledge.

## Tasks

- [ ] add second-wave sports;
- [ ] add regional competitions;
- [ ] add additional bookmakers;
- [ ] add more market mappings;
- [ ] enrich sport-specific research checklists;
- [ ] add source adapters discovered by Sabi;
- [ ] add source-quality notes from real use;
- [ ] add new ticket formats encountered in the wild;
- [ ] add more result sources;
- [ ] improve cross-book mapping.

This phase continues after V2 launch. Broad coverage is a living capability rather than a finished static list.

---

# 23. V2 Milestones

## Milestone A — Foundation Alpha

Includes:

- canonical data layer;
- single operational DB path;
- OpenClaw-native tools;
- free-first source registry;
- first sport profiles;
- market interpreter foundation.

Success condition: Sabi can research across multiple sports through the new layer and V1 history is safely migratable.

## Milestone B — Research Beta

Includes:

- market-aware research;
- source discovery;
- broad first-wave sport coverage;
- evidence persistence;
- bookmaker adapter framework;
- odds comparison.

Success condition: Sabi can independently investigate multiple sports without football-first assumptions or routine paid API dependence.

## Milestone C — Ticket Workshop Beta

Includes:

- code import;
- screenshot import;
- text import;
- X post import where accessible;
- split;
- remove;
- replace;
- market changes;
- target-odds trimming;
- ticket lineage.

Success condition: real-world ticket examples can be transformed reliably.

## Milestone D — Bookmaker Conversion Beta

Includes:

- cross-book event mapping;
- market conversion;
- target slip creation;
- booking-code generation where supported;
- arbitrage/price comparison.

Success condition: at least one real end-to-end bookmaker conversion flow works in staging.

## Milestone E — Dashboard + Blog RC

Includes:

- V2 dashboard;
- migrated history;
- ticket history;
- performance graphs;
- finance;
- strategy views;
- Sabi blog;
- system health.

Success condition: dashboard is fully read-only, coherent, reconciled and useful.

## Milestone F — V2 Release Candidate

Includes:

- reliability hardening;
- security cleanup;
- full migration rehearsal;
- full backup/restore rehearsal;
- OpenClaw end-to-end tests;
- local acceptance suite;
- documentation update.

---

# 24. Testing Strategy

All test actions should run locally/on the controlled server or staging environment. Do not depend on GitHub Actions.

## Unit tests

Focus on deterministic logic:

- event identity;
- aliases;
- market normalization;
- decimal odds parsing;
- combined odds;
- ticket splitting;
- target-odds search;
- settlement;
- bankroll ledger;
- arbitrage math;
- rule matching.

## Fixture tests

Save sanitized representative inputs:

- bookmaker HTML/JSON snippets;
- booking codes when stable enough;
- screenshots;
- X post text/media examples;
- market labels;
- source responses;
- sports result examples.

These allow repeatable testing without constantly hitting live sites.

## Integration tests

Test:

- OpenClaw -> Sabi tool -> domain service -> DB;
- research fallback chain;
- bookmaker search;
- ticket conversion;
- settlement;
- dashboard APIs;
- blog publication.

## Staging tests

Use the controlled SabiAI environment for live bookmaker/browser/source checks.

Do not make production the first place live adapters are tested.

## Migration tests

Run migration against copies of the real V1 database and reconcile:

- pick counts;
- settled counts;
- W/L/D;
- bankroll;
- strategy history;
- tickets/accumulators;
- diary/blog migration.

---

# 25. Acceptance Test Catalogue

V2 should not be considered done until these representative requests work.

## Sports breadth

- “Find today’s volleyball games.”
- “Check basketball, no football.”
- “Compare these tennis players.”
- “Research this esports match.”
- “Look at golf matchups.”

## Match research

- “Check form, H2H and injuries.”
- “Check the card market for this football match.”
- “Check corners.”
- “Check player shots.”
- “Check volleyball set handicap.”

## Ticket input

- booking code;
- screenshot;
- copied ticket text;
- X post;
- plain instructions.

## Ticket edit

- “Split this ticket into two.”
- “Remove the weakest three.”
- “Change BTTS to Double Chance where it makes sense.”
- “Trim this to around 20 odds.”
- “Keep these two games no matter what.”

## Conversion

- “Convert this Bet9ja code to SportyBet.”
- “Convert this Stake ticket.”

## Build

- “Use these picks and book the games.”
- “Build a three-game volleyball ticket.”

## Bookmaker research

- “Which bookmaker has the best decimal odds for this selection?”
- “Check whether these prices create an arbitrage.”

## History

- “What is our current streak?”
- “How have we done in volleyball?”
- “Which market has hurt us most?”
- “How often does one game kill our large tickets?”

## Blog

- “Write today’s blog.”
- automated weekly reflection grounded in real history.

---

# 26. Migration Plan

## Step 1 — Snapshot

Create immutable backups of all V1 operational databases and relevant JSON/files.

## Step 2 — Dry-run migration

Import into V2 schema on staging.

## Step 3 — Reconcile

Compare V1 and V2 totals.

## Step 4 — Dual-read validation if useful

For a short validation window, compare old and new statistics outputs without creating two independent sources of truth.

## Step 5 — Cut over scheduled jobs

Disable old settlement/scan jobs only after V2 replacements are confirmed.

## Step 6 — Cut over dashboard

Dashboard reads V2 canonical records.

## Step 7 — Preserve rollback

Keep the last V1 database snapshot and code state available until V2 has completed an agreed stable period.

---

# 27. Documentation Deliverables During Build

Maintain:

- `docs/SABIAI_V2_PRODUCT_BIBLE.md` — what the product is;
- `docs/SABIAI_V2_BUILD_PLAN.md` — build sequence;
- `docs/SABIAI_V2_TASKS.md` — living implementation checklist;
- source registry documentation;
- bookmaker adapter notes;
- sport profile notes;
- migration notes;
- deployment/runbook;
- OpenClaw skill/tool reference;
- schema/data dictionary;
- release notes.

The Product Bible is authoritative on product behavior. The Build Plan is authoritative on sequence. The Tasks file is authoritative on current execution state.

---

# 28. Implementation Priorities

When tradeoffs arise, prioritize in this order:

1. preserve our historical data;
2. keep OpenClaw as Sabi’s brain;
3. make event/market identity correct;
4. make research broad and free-first;
5. make ticket workflows reliable;
6. make bookmaker mappings accurate;
7. make settlement trustworthy;
8. make dashboard statistics reconcile;
9. expand sports/markets continuously;
10. polish optional extras.

Do not prioritize flashy dashboard features over data correctness, ticket correctness or Sabi’s research capability.

---

# 29. V2 Definition of Done

SabiAI V2 is done when:

- `v2` contains the complete production-ready system;
- OpenClaw is the primary intelligence/interface layer;
- Sabi can research a broad range of sports;
- the system is not structurally football-first;
- Sabi prefers free/public data and uses paid sources only as fallback;
- Sabi independently researches beyond bookmaker odds;
- Sabi understands common result, handicap, total, set, count and player markets;
- Sabi speaks plain language and uses decimal odds;
- team selections are explicit;
- booking codes can be imported where supported;
- screenshots can be read and reconstructed;
- ticket text can be parsed;
- X posts can be turned into structured tickets where accessible;
- tickets can be split, trimmed, edited and rebuilt;
- bookmaker conversion works for supported pairs;
- booking codes can be created where supported;
- bookmaker odds can be compared;
- genuine matching price/arbitrage opportunities can be identified;
- our picks/tickets settle reliably;
- our historical data is preserved;
- bankroll/statistics reconcile;
- the dashboard is read-only and focused only on our history/performance;
- dashboard charts work across sports/markets automatically;
- Sabi maintains a meaningful blog;
- backups and restoration are tested;
- no insecure browser write-key/PIN pattern remains;
- the full local acceptance suite passes;
- migration from V1 is rehearsed and reversible;
- release documentation is complete.

Only after this gate should `v2` be promoted to `main`.
