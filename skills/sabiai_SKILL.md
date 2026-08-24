# SabiAI V2 Skill

Use this skill for SabiAI sports research, bookmaker/ticket work, Sabi history and the Sabi blog.

Authoritative product rules live in:

- `V2.md`
- `docs/SABIAI_V2_PRODUCT_BIBLE.md`
- `docs/SABIAI_V2_BUILD_PLAN.md`
- `SOUL.md`

## Product Boundary

Sabi/OpenClaw is the active sports researcher and ticket worker.

The dashboard is read-only and displays our own history, performance, streaks, tickets, bankroll, strategies, charts and Sabi’s blog. Do not turn it into a general sports portal.

## User-Facing Language

Always use:

- plain English;
- decimal odds;
- explicit team/player names;
- explicit home/away wording where useful;
- clear market names.

Examples:

- `Arsenal to win — 1.72`
- `Chelsea or Draw — Double Chance — 1.31`
- `Over 2.5 goals — 1.84`
- `Arsenal +1.5 handicap — 1.40`
- `Over 8.5 corners — 1.76`
- `Player A over 4.5 rebounds — 1.90`

Do not use American-facing terms in normal output. Do not expose internal modelling jargon unless explicitly asked.

## V2 Tool Gateway

New V2 behavior must go through the Sabi domain gateway instead of giving every skill direct database access.

Script:

```bash
python3 ~/.openclaw/workspace/scripts/sabiai_v2_tool.py
```

Input/output is JSON.

### Current implemented tools

#### `system.health`

```bash
echo '{"tool":"system.health","args":{}}' | python3 ~/.openclaw/workspace/scripts/sabiai_v2_tool.py
```

Returns V2 version/database health without exposing secrets.

#### `market.interpret`

```bash
echo '{"tool":"market.interpret","args":{"text":"X2","home":"Arsenal","away":"Chelsea"}}' \
  | python3 ~/.openclaw/workspace/scripts/sabiai_v2_tool.py
```

Example plain result: `Chelsea or Draw — Double Chance`.

Use this whenever bookmaker wording/shorthand needs normalizing.

#### `bookmaker.resolve`

```bash
echo '{"tool":"bookmaker.resolve","args":{"name":"Sporty Bet"}}' \
  | python3 ~/.openclaw/workspace/scripts/sabiai_v2_tool.py
```

Current canonical bookmaker registry includes SportyBet, Bet9ja, 1xBet and Stake. Capability flags stay conservative until each adapter proves what it can do.

#### `ticket.split`

```bash
echo '{
  "tool":"ticket.split",
  "args":{
    "bookmaker":"SportyBet",
    "slips":2,
    "legs":[
      {"event_id":"a","home":"Arsenal","away":"Chelsea","market":"1","odds":"1.45"},
      {"event_id":"b","home":"Inter","away":"Milan","market":"X2","odds":"1.38"},
      {"event_id":"c","home":"PSG","away":"Lyon","market":"Over 2.5 goals","odds":"1.70"},
      {"event_id":"d","home":"Ajax","away":"PSV","market":"Over 8.5 corners","odds":"1.62"}
    ]
  }
}' | python3 ~/.openclaw/workspace/scripts/sabiai_v2_tool.py
```

Creates child ticket versions and keeps parent/child lineage.

#### `ticket.trim`

```bash
echo '{
  "tool":"ticket.trim",
  "args":{
    "target_odds":"20.00",
    "min_legs":3,
    "legs":[...]
  }
}' | python3 ~/.openclaw/workspace/scripts/sabiai_v2_tool.py
```

Finds a combination nearest the requested combined decimal odds. A leg with `"locked":true` must stay.

### Database initialization

V2 uses its own database during development so V1 remains untouched:

```bash
python3 ~/.openclaw/workspace/scripts/sabiai_v2_tool.py --init-db \
  --request '{"tool":"system.health","args":{}}'
```

Default V2 DB: `~/.openclaw/workspace/data/sabiai_v2_core.db`.

## Broad-Sports Rule

Never assume football is the primary or only sport.

When the request does not specify a sport, search broadly enough for the task. Coverage should grow across all useful bookmaker sports and competitions.

If Sabi lacks a dedicated adapter for a sport or league, research and source discovery are the fallback—not “unsupported sport.”

## Free-First Research

Use the cheapest reliable source path in this order:

1. Sabi cache/local database;
2. open/public dataset;
3. official sport/league/team/tournament source;
4. public endpoint;
5. ordinary public webpage;
6. OpenClaw browser;
7. search/source discovery;
8. another free source;
9. paid API only after the free path is exhausted or when specifically needed for confirmation.

Do not use a paid token just because it is convenient.

Cache reusable results and avoid duplicate requests.

## Match Research

Research must follow the market.

General checks can include form, home/away performance, H2H, injuries/availability, lineups/rosters, schedule/rest, competition context and relevant sport-specific information.

Then add market-specific checks:

- goals → scoring/conceding patterns and attacking availability;
- corners → corner creation/concession, width, territory and game-state tendencies;
- cards → disciplinary records, likely match intensity and referee information when available;
- shots → expected minutes/role and shot volume;
- basketball → points, rebounds, assists, threes, quarters/halves as relevant;
- volleyball → match/set records, straight-set patterns, serving/receiving/blocks when available;
- tennis/table tennis → surface/format, recent match/set form, serve/return where available;
- cricket → format, venue, batting/bowling roles, weather/pitch where relevant;
- golf → course fit, recent performance, weather/wave and matchup context;
- esports → game title, patch/version, roster, map pool/veto and format where relevant.

Never force the same football-style checklist onto every sport.

## Ticket Inputs

V2 target inputs:

- booking code;
- screenshot;
- copied ticket text;
- bookmaker share text;
- X post/link;
- plain instruction;
- user plan.

Current V2 implementation has the normalized ticket core plus split/trim. Importers, screenshot/X extraction, bookmaker conversion and booking-code creation are still being migrated/built. Do not pretend an unfinished adapter exists.

## Ticket Editing Rules

When editing a ticket:

1. identify every event and selection;
2. normalize confusing bookmaker wording;
3. preserve anything the user locked;
4. make requested changes;
5. show what changed;
6. retain ticket lineage for history.

Supported V2 core operations currently include split, trim-to-target and remove at the domain layer.

## Bookmaker Conversion Target

Target flow:

1. import source slip/code;
2. resolve source events and markets;
3. find equivalent target-book events;
4. map equivalent target-book markets;
5. compare current decimal odds;
6. handle unavailable markets explicitly;
7. build target slip;
8. verify selections;
9. return booking code where supported;
10. store conversion lineage.

Never assume two similarly named markets settle the same way.

## Existing V1 Compatibility

Until migration is complete, legacy scripts still contain historical production behavior.

Important existing stores:

- `~/.openclaw/workspace/data/bets.db`
- legacy `sabiai_v2.db` match/upcoming data
- accumulator/chain/long-shot/live tables in `bets.db`

Do not delete, reset or silently rewrite them during V2 development.

New V2 writes should target the V2 domain database unless a migration/compatibility path explicitly says otherwise.

## Dashboard Rule

Dashboard means **our records**, not today’s sports information.

Allowed dashboard data includes:

- history;
- W/L/D/void/pending;
- streaks;
- bankroll and P/L;
- by-sport/by-market/by-bookmaker/by-strategy performance;
- ticket history and ticket killers;
- original vs edited ticket history;
- Sabi blog;
- system health.

General match stats, fixture discovery, injury searches and bookmaker browsing belong in Sabi/OpenClaw, not the dashboard.

## Sabi Blog

The blog is Sabi’s first-person record of observations and lessons. It should build continuity over time and can reference our own performance/history.

Do not write generic sports-news filler.

## AI Spine / Agent Coordination

Follow `AGENTS.md` for AI Spine and Matrix rules.

Use memory search before repeating expensive research. Ask Clawson/relevant agents when their context materially helps. Use temporary research workers when parallel work is useful, but Sabi owns the final answer.

## Development Truth

The V2 living task board is:

`docs/SABIAI_V2_TASKS.md`

Do not claim a capability complete merely because this skill describes its intended final behavior. Check the task board and actual tools first.
