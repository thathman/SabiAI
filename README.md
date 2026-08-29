# Sabi Boy V2

**Sabi Boy** is an OpenClaw-native, multi-sport sports intelligence system.

He researches sports, understands bookmaker markets in plain language, compares prices, checks form/injuries/context, reads and edits tickets, restores booking codes, plans bookmaker conversions, keeps our history, reviews his own work and writes a first-person blog about what he is seeing and learning.

The repository is still named **SabiAI** and technical identifiers such as `sabiai`, `sabi-ai`, existing DB names and environment-variable prefixes remain for compatibility while V2 is maintained.

> **Production release:** `v2.4.0` (`2ead1725b7b0eac4a95f05eef78bbbb5556cfdcd`) is released on Forgejo and GitHub `main`.
> `v2` remains the matching controlled development line.

---

## Product rule

> **OpenClaw Sabi Boy does the work. The dashboard records our story.**

The dashboard is **not** a sports portal. It is read-only and visualizes our own:

- games/picks;
- Won / Lost / Draw / Void / Pending history;
- streaks;
- tickets and ticket killers;
- bankroll and betting P/L;
- performance by sport, market, bookmaker, strategy and odds range;
- Sabi Boy Blog;
- source/system health.

Sports research, bookmaker search, booking-code restoration, ticket editing and conversion happen through Sabi Boy/OpenClaw.

---

## User-facing language

Sabi Boy should sound like a knowledgeable sports person, not a technical statistics package.

Use:

- `Arsenal to win — 1.72`
- `Chelsea or Draw — Double Chance — 1.31`
- `Over 2.5 goals — 1.84`
- `Arsenal +1.5 handicap — 1.40`
- `Over 8.5 corners — 1.76`
- `LeBron James — Over 7.5 rebounds — 1.90`

Rules:

- decimal odds only;
- explicit team/player names;
- home/away where useful;
- translate 1/X/2, 1X, X2, Handicap 1/2 and bookmaker shorthand;
- no unexplained American betting language;
- internal technical implementation stays behind the interface unless specifically requested.

---

## Broad sports

Football is not the coverage boundary.

The V2 sports framework includes knowledge profiles for football, basketball, volleyball, tennis, table tennis, baseball, ice hockey, cricket, golf, esports, handball, rugby, darts, snooker, badminton, MMA, boxing, motorsport, cycling, futsal, water polo, beach volleyball, padel, floorball, Aussie rules and more.

An unfamiliar sport triggers **discovery/research**, not `unsupported`.

---

## Major V2 capabilities

### Sports and research

Sabi Boy can plan/check:

- fixtures/events;
- team/player identity;
- recent form;
- home/away or venue context;
- H2H where relevant;
- injuries, suspensions, withdrawals, lineups/rosters;
- rest/travel/schedule context;
- market-specific statistics;
- official/public evidence and source conflicts.

Research is market-aware: corners research is different from cards, player rebounds, volleyball set handicaps, golf matchups or esports map markets.

### Free-first source system

Default order:

1. fresh local/cache/evidence;
2. open/public data;
3. official source;
4. public structured endpoint;
5. public webpage;
6. OpenClaw browser;
7. search/source discovery;
8. another free source;
9. paid source only when free paths are insufficient and paid use is explicitly allowed/justified.

Built-in direct sources currently include TheSportsDB and an optional football-data.org adapter. OpenClaw Browser/Search are broader fallbacks.

### Ticket Workshop

Inputs/workflows include:

- booking code;
- screenshot/image through OpenClaw vision;
- copied/share text;
- X post/link content;
- plain instruction;
- existing Sabi Boy draft.

Operations include:

- split into smaller slips;
- remove/keep/replace games;
- change markets;
- trim toward target combined odds;
- preserve locked selections;
- rank/keep strongest selections from research;
- plan lower-risk market changes;
- preserve original/edit/conversion lineage.

### Bookmakers

Canonical bookmaker identities include:

- SportyBet
- Bet9ja

Capability reporting is conservative: recognizing a bookmaker is not the same as having a proven importer/builder for every market.

Current V2 includes:

- booking-code import plans;
- verified browser-restoration playbooks for SportyBet and Bet9ja;
- browser-restored slip validation;
- exact target-bookmaker search plans;
- exact conversion verification;
- controlled compatibility builders for proven legacy SportyBet/Bet9ja scope.

### Price comparison / arbitrage

V2 can normalize compatible prices, reject stale quotes, compare settlement rules, calculate 2/3/N-outcome price combinations and calculate stake splits. Live multi-book price ingestion is still a release-work item.

### Settlement / history

V2 has one canonical settlement/history path with:

- idempotent settlement;
- audited corrections;
- ticket status derived from legs;
- duplicate payout protection;
- bankroll reconciliation;
- settlement backlog monitoring.
- a fixed ten-minute free-result heartbeat for deterministic score-derived markets;
- audited, idempotent automatic pick/ticket-leg outcomes without inferred payouts;
- Web Push notifications when automatic settlement changes recorded outcomes.

The V2 dashboard is an installable PWA with 192/512 and maskable icons, a service worker,
offline shell, install controls, mobile drawer close/backdrop controls and opt-in Web Push.
Sports/history data remains read-only; only the narrow push subscribe/unsubscribe endpoints
accept browser writes.

### Sabi Boy Blog

The blog is a first-person intelligence journal, not generic sports news. It can cover what changed Sabi Boy's mind, mistakes, recurring ticket killers, bookmaker disagreement, source lessons, new sports/markets and weekly reflections.

---

## Architecture

```text
                         SABI BOY
                    OpenClaw Main Agent
                           │
        memory • browser • search • tools • skills
            heartbeat • workers • AI Spine
                           │
       ┌───────────────────┼───────────────────┐
       │                   │                   │
    RESEARCH            SPORTS             MARKET
    evidence            knowledge          bookmakers
    sources             rules              prices
    context             formats            tickets
       └───────────────────┼───────────────────┘
                           │
                    INTELLIGENCE CORE
                           │
       research cases • price comparison • risk
       ticket workshop • settlement • history
                           │
             BET / WATCH / WAIT / PASS
                           │
                RECORD / BLOG / LEARN
                           │
                 READ-ONLY DASHBOARD
```

---

## Repository layout

```text
SabiAI/
├── SABI_BOY.md                  # canonical V2 product/agent reference
├── IDENTITY.md
├── SOUL.md
├── OPERATING_MANUAL.md
├── AGENTS.md
├── HEARTBEAT.md
├── TOOLS.md
├── V2.md
├── sabiai/
│   ├── domain/
│   ├── storage/
│   ├── sports/
│   ├── research/
│   ├── sources/
│   ├── markets/
│   ├── bookmakers/
│   ├── tickets/
│   ├── odds/
│   ├── settlement/
│   ├── blog/
│   ├── system/
│   ├── dashboard/
│   ├── migration/
│   ├── ops/
│   └── openclaw/
├── dashboard/
│   ├── app.py                   # preserved V1 dashboard
│   ├── v2_app.py                # Sabi Boy read-only dashboard
│   └── v2/                      # V2 dashboard assets
├── scripts/
│   ├── sabiai_v2_tool.py        # OpenClaw JSON gateway bridge
│   ├── sabi_v2_prepare_runtime.sh
│   ├── sabi_v2_stage.sh
│   ├── sabi_v2_acceptance.py
│   ├── sabi_v2_migrate.py
│   ├── sabi_v2_backup.py
│   ├── sabi_v2_finalize_cutover.py
│   └── sabi_v2_rollback.py
├── skills/
│   ├── sabiai_SKILL.md           # primary Sabi Boy skill, compatibility filename
│   ├── sabi-boy-research-scout_SKILL.md
│   ├── sabi-boy-skeptic_SKILL.md
│   └── sabi-boy-ticket-engineer_SKILL.md
├── docs/
│   ├── SABIAI_V2_PRODUCT_BIBLE.md
│   ├── SABIAI_V2_BUILD_PLAN.md
│   ├── SABIAI_V2_TASKS.md
│   └── SABI_BOY_V2_DEPLOYMENT.md
├── tests/
├── requirements-v2.txt
└── config/sabi-boy.env.example
```

Legacy V1 scripts/data remain during migration and are not silently deleted.

---

## OpenClaw tool gateway

Use:

```bash
printf '%s\n' '{"tool":"system.tools","args":{}}' | \
  .venv/bin/python scripts/sabiai_v2_tool.py
```

Never assume a capability from an old document. `system.tools` + the living task board define current implementation truth.

Representative namespaces:

```text
system.*
source.*
sports.*
research.*
market.*
bookmaker.*
ticket.*
record.*
history.*
settlement.*
blog.*
```

---

## V2 runtime preparation

V2 has its own requirements and environment file.

```bash
git checkout v2
bash scripts/sabi_v2_prepare_runtime.sh
```

This prepares `.venv`, dependencies, V2 DB/schema, source catalog and the `sabi-boy-dashboard.service` user unit. It does **not** migrate V1, stop V1, start V2 or change external routing.

Runtime environment:

```text
~/.config/sabi-boy/sabi-boy.env
```

Template:

```text
config/sabi-boy.env.example
```

Secrets remain outside Git.

---

## Safe staging / migration

When release gates are ready:

```bash
bash scripts/sabi_v2_stage.sh
```

The staging flow:

1. verifies/snapshots V1 and existing V2 databases;
2. migrates V1 → V2 deterministically;
3. reconciles history/bankroll;
4. runs the complete release acceptance runner;
5. performs backup/restore drill;
6. starts Sabi Boy V2 beside V1 on `127.0.0.1:8091`;
7. checks V2 health/overview;
8. leaves V1 unchanged.

The repository does not guess Cloudflare/reverse-proxy routing. The production route has been inspected and verified against the accepted V2 runtime at `127.0.0.1:8090`.

Full runbook:

`docs/SABI_BOY_V2_DEPLOYMENT.md`

---

## Read-only V2 dashboard

V2 app:

```text
dashboard/v2_app.py
```

Local staging address:

```text
http://127.0.0.1:8091
```

API prefix:

```text
/api/v2
```

The V2 browser API is GET-only. No PIN unlock, no localStorage write token and no browser mutation endpoints are part of the V2 dashboard.

---

## Development / tests

```bash
.venv/bin/python -m pytest -q
```

Release acceptance:

```bash
.venv/bin/python scripts/sabi_v2_acceptance.py --migrate-v1
```

The current branch contains a substantially expanded test suite. Any future candidate must pass the full current suite and Dell/OpenClaw acceptance gates in `docs/SABIAI_V2_TASKS.md`; the v2.4.0 baseline has already passed them.

---

## V1 compatibility

`main` is the Sabi Boy V2.4 production line. V1 recovery data and compatibility tooling remain retained for rollback and historical reference.

On `v2`:

- V1 database is opened read-only by the migration process;
- raw legacy rows are preserved in `legacy_archive`;
- V1 dashboard/service can remain live while V2 is staged;
- legacy scripts/builders are capability-gated rather than assumed safe for new markets;
- rollback state is recorded before external cutover.

Old operational history/reference material is preserved under `docs/` and legacy files rather than being treated as the V2 product definition.

---

## Current build status

Authoritative living board:

`docs/SABIAI_V2_TASKS.md`

Phase 16 records the completed v2.4.0 promotion and remains the authority for any future release.

Future upgrade prompts should be issued only after the applicable release gates are complete, so they can execute real repo tooling instead of improvising migration.

## License

Private / personal.
