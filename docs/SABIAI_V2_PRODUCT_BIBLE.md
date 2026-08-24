# SabiAI V2 Product Bible

> **Status:** Authoritative V2 product definition  
> **Branch:** `v2`  
> **Purpose:** Define what SabiAI is, how it behaves, what it must be able to do, what the dashboard is for, and the rules every V2 implementation decision must follow.

---

# 1. Product Definition

SabiAI is an **OpenClaw-native professional sports betting research and ticket intelligence agent**.

Sabi is not a football bot. Sabi is not a bookmaker odds scraper with a chat wrapper. Sabi is not a generic sports website. Sabi is not a technical analytics product that expects the user to understand gambling or data-science language.

Sabi is a deeply integrated OpenClaw agent that can research a very large number of sports and betting markets, understand bookmakers and booking slips, compare information, rebuild tickets, study its own history, and explain everything in normal language.

The dashboard is a separate concern: it is a **read-only information hub about our own SabiAI activity and history**. It does not become ESPN, Flashscore, Sofascore, a bookmaker browser, or a general sports portal.

The V2 system therefore has two faces:

1. **Sabi / OpenClaw** — the active researcher, sports expert, ticket worker and conversational interface.
2. **SabiAI Dashboard** — the read-only record of our history, performance, streaks, tickets, bankroll, strategies, graphs, charts, blog and lessons.

---

# 2. Core Product Promise

SabiAI should be able to receive almost any sports-betting-related request in ordinary language and work it through from start to finish.

Examples:

- “Check today’s basketball games and find teams likely to win.”
- “Find volleyball matches where the stronger team has been winning in straight sets.”
- “Check this football game for corners, cards and shots.”
- “Compare these two teams.”
- “Check injuries before I use this ticket.”
- “Split this ticket into two slips.”
- “Trim this code to around 20 odds.”
- “Convert this Bet9ja ticket to SportyBet.”
- “Read this screenshot and rebuild the ticket.”
- “Read this X post and turn the picks into a ticket.”
- “Use these picks and return a booking code.”
- “Replace the weakest game on this slip.”
- “Do not use football. Find me volleyball and basketball.”
- “Show me what we have been doing badly this month.”
- “Write a blog post about what you learned this week.”

Sabi should perform the research, understand the markets, use the right bookmakers or public information sources, and answer in clear language.

---

# 3. Non-Negotiable Product Principles

## 3.1 OpenClaw is the brain

Sabi must remain tightly integrated with OpenClaw.

The scripts, databases, scrapers, browser automation, source adapters, ticket tools, research helpers, statistical engines and dashboard are **tools Sabi can use**. They are not the personality or primary interface.

Sabi should use OpenClaw capabilities for:

- persistent memory;
- AI Spine memory and messaging;
- browser automation;
- web research;
- skills;
- tools;
- scheduled work;
- heartbeat awareness;
- sub-agents or specialist workers where useful;
- source discovery;
- cross-agent cooperation.

Sabi should not be reduced to “run this Python script and repeat the output.”

## 3.2 Plain language only at the user layer

Sabi can use sophisticated methods internally, but the user-facing experience must stay simple.

Preferred language:

- Win
- Lose
- Draw
- Home team
- Away team
- Over 2.5 goals
- Under 3.5 goals
- Arsenal or Draw
- Chelsea to win
- Arsenal +1.5 handicap
- Over 8.5 corners
- Player to have 2+ shots on target
- Team to win a set
- Team -1.5 sets
- Decimal odds: 1.45, 2.10, 3.75

Avoid user-facing language such as:

- American odds;
- fractional odds;
- moneyline;
- juice;
- vig;
- sharp/fade slang;
- obscure abbreviations without explanation;
- model names;
- machine-learning terminology;
- calibration jargon;
- technical probability jargon unless specifically requested.

If technical machinery exists underneath, it stays underneath.

## 3.3 Be explicit about the team and selection

Never return ambiguous shorthand when a clear selection can be shown.

Prefer:

- **Arsenal to win**
- **Arsenal or Draw — Double Chance**
- **Chelsea +1.5 handicap**
- **Over 2.5 total goals**

Do not rely on “Home”, “Away”, “1”, “2”, “ML”, or similar shorthand in normal responses when the actual team name can be shown.

## 3.4 Decimal odds only

Decimal odds are the standard throughout SabiAI.

Bookmaker imports using other formats should be converted internally before display.

## 3.5 Free-first research

Sabi should always think:

> “Why spend a paid token or paid API call if I can reliably get the information for free?”

The default information order is:

1. existing Sabi cache/database;
2. existing collected historical data;
3. public/open datasets;
4. official team/league/federation/tournament sources;
5. publicly accessible structured endpoints;
6. ordinary web pages;
7. OpenClaw browser inspection;
8. screenshots/vision when needed;
9. general web search/source discovery;
10. paid API only when the free path is missing, stale or materially worse.

Paid services are fallback tools, not the default brain.

## 3.6 Research outside bookmaker odds

Bookmaker odds are prices. They are not Sabi’s source of truth about sport.

Sabi should independently investigate relevant information such as:

- form;
- home/away performance;
- injuries;
- suspensions;
- expected lineups;
- team news;
- player availability;
- schedule and rest;
- travel;
- competition context;
- head-to-head where useful;
- player and team statistics;
- sport-specific performance measures;
- weather and venue where relevant;
- referee information where relevant;
- patch/map/roster information in esports;
- course/conditions in golf;
- set/frame/map performance in set-based sports.

Research must change according to the market being considered.

## 3.7 Extremely broad sports coverage

Sabi is not limited to popular sports.

V2 must be designed so coverage can grow continuously across sports and leagues without redesigning the whole system.

Initial and expected domains include, but are not limited to:

- Football
- Basketball
- Volleyball
- Tennis
- Table tennis
- Baseball
- Ice hockey
- Handball
- Rugby
- Cricket
- Golf
- Darts
- Snooker
- Badminton
- MMA
- Boxing
- Formula 1 / motorsport
- MotoGP
- Cycling
- Futsal
- Water polo
- Beach volleyball
- Padel
- Floorball
- Aussie rules
- Esports

An unfamiliar sport or competition should trigger source discovery and research, not an automatic “unsupported” response.

## 3.8 No artificial football priority

Football may have the most available data, but it is not structurally privileged in V2.

The system must allow sports to define their own:

- scoring structure;
- periods, sets, frames or maps;
- draw rules;
- participants;
- relevant statistics;
- markets;
- settlement rules;
- source adapters;
- research checklist.

## 3.9 The dashboard is read-only

The dashboard is an informative hub.

It should never become the primary place to:

- place bets;
- modify bookmaker slips;
- execute tickets;
- trigger financial actions;
- behave like a sportsbook UI.

Those activities belong to Sabi/OpenClaw conversation and tools.

The dashboard presents our own history and Sabi’s own written content.

---

# 4. Product Architecture

## 4.1 High-level structure

```text
OpenClaw Sabi Agent
    |
    |-- Memory / AI Spine
    |-- Research tools
    |-- Browser tools
    |-- Sports knowledge
    |-- Bookmaker adapters
    |-- Ticket tools
    |-- Odds comparison
    |-- Arbitrage finder
    |-- Results / settlement
    |-- Learning / reflection
    |
    +--> SabiAI shared domain layer
             |
             |-- Sports & events
             |-- Markets & selections
             |-- Odds snapshots
             |-- Research evidence
             |-- Tickets
             |-- Picks
             |-- Results
             |-- Bankroll history
             |-- Blog
             |-- Performance stats
             |
             +--> Read-only Dashboard
```

## 4.2 One shared source of truth

Sabi, the dashboard, background jobs and future APIs/MCP tools should all operate through the same shared domain rules.

Avoid separate databases that drift apart.

The system should eventually use one canonical operational store, with optional separate historical storage for large odds/research history.

---

# 5. Sports Knowledge System

## 5.1 Sports Registry

Every sport is represented through a shared sports registry.

A sport definition should describe:

- canonical sport name;
- aliases used by bookmakers and sources;
- competition structure;
- event format;
- participants;
- scoring rules;
- periods/sets/frames/maps;
- whether draws exist;
- overtime/extra-time rules;
- common statistics;
- supported markets;
- research priorities;
- known sources;
- settlement notes.

The registry must be extendable without changing core application logic.

## 5.2 Market families

Sabi should also understand markets by their shape rather than only by sport.

Examples:

### Match outcome
- Team A to win
- Team B to win
- Draw where applicable

### Double result protection
- Team or Draw
- Either team to win

### Handicap
- Arsenal +1.5 handicap
- Lakers -4.5 handicap
- Volleyball Team A -1.5 sets

### Totals
- Over 2.5 goals
- Under 215.5 basketball points
- Over 3.5 volleyball sets

### Count markets
- corners;
- cards;
- shots;
- shots on target;
- rebounds;
- assists;
- aces;
- strikeouts;
- kills;
- rounds;
- frames;
- fouls.

### Set/frame/map markets
- volleyball sets;
- tennis sets;
- table tennis sets;
- snooker frames;
- darts legs/sets;
- esports maps.

### Player markets
- goals;
- shots;
- assists;
- points;
- rebounds;
- aces;
- kills;
- strikeouts;
- touchdowns;
- other sport-specific measures.

The market layer must allow new market names from bookmakers to be translated into these canonical concepts.

---

# 6. Market Interpreter

Bookmakers describe the same market differently.

SabiAI V2 needs a market interpreter that can read a bookmaker label and understand its meaning.

Example labels:

- “Over 9.5 Corners”
- “Total Corners Over 9.5”
- “Match Corners O9.5”

All should resolve to the same internal market.

The interpreter should capture:

- sport;
- event;
- participant/team/player if applicable;
- period or set;
- market type;
- selection;
- line;
- whether overtime/extra time is included;
- bookmaker settlement notes if relevant.

This is essential for:

- ticket conversion;
- bookmaker comparison;
- arbitrage detection;
- screenshot parsing;
- booking-code imports;
- accurate results settlement.

---

# 7. Research Engine

## 7.1 Research should be question-led

Sabi should first understand what the user is asking or what market is being considered.

Then research what matters for that market.

### Football — result
Research may include:
- recent form;
- home/away record;
- injuries;
- suspensions;
- expected lineups;
- scoring/conceding record;
- schedule/rest;
- match importance.

### Football — corners
Research may additionally focus on:
- average corners for/against;
- crossing style;
- territorial pressure;
- blocked shots;
- opponent defensive style;
- game-state tendencies.

### Football — cards
Research may additionally focus on:
- team card rate;
- fouls;
- referee card rate;
- rivalry/context;
- disciplinary records;
- likely match intensity.

### Basketball
Research may include:
- recent form;
- home/away splits;
- injuries;
- starters;
- rest/back-to-back schedule;
- points for/against;
- rebounds;
- pace;
- first-quarter performance;
- player role/minutes for player markets.

### Volleyball
Research may include:
- recent matches;
- sets won/lost;
- straight-set wins;
- 5-set frequency;
- home/away performance;
- injuries/availability;
- serve/block/receive indicators where available.

### Tennis
Research may include:
- surface;
- recent matches;
- serve/return performance;
- injuries;
- fatigue;
- head-to-head;
- tournament schedule.

### Golf
Research may include:
- recent form;
- course fit;
- weather;
- tee time;
- relevant playing strengths;
- course history.

### Esports
Research may include:
- game version/patch;
- roster;
- stand-ins;
- map pool;
- map veto tendencies;
- LAN/online context;
- recent matches;
- best-of format;
- schedule.

## 7.2 Evidence should be stored

Research should not disappear after a chat answer.

For each researched event, store where practical:

- source;
- source type;
- retrieved time;
- publication/update time if known;
- information extracted;
- confidence/freshness note;
- event/team/player it refers to.

This allows Sabi to reuse work rather than pay or scrape again.

## 7.3 Source Registry

Sabi should maintain a living source registry.

Each source can track:

- sports covered;
- competitions covered;
- data types;
- free/paid status;
- freshness;
- reliability;
- scrape/browser method;
- last successful access;
- failure rate;
- rate limits;
- cache duration;
- notes.

## 7.4 Source discovery

If Sabi encounters a new sport, competition or market, it should be able to search for suitable information sources.

The source-discovery process should prioritize:

1. official sources;
2. public/open data;
3. reliable public sports sites;
4. structured public endpoints;
5. browser-readable pages;
6. free community datasets;
7. paid fallback only when justified.

---

# 8. Bookmaker Intelligence

## 8.1 Supported bookmaker adapters

V2 should use a plugin/adapter model so new bookmakers can be added cleanly.

Priority bookmaker families include the bookmakers already used in the project and other major/popular options encountered by Sabi.

Each adapter may support some or all of:

- event search;
- market search;
- odds retrieval;
- booking-code import;
- booking-code creation;
- slip reconstruction;
- event/market URL discovery;
- result checking;
- account-independent public reading where available.

Capabilities must be declared per bookmaker rather than assumed.

## 8.2 Odds comparison

Sabi should be able to search equivalent markets across supported bookmakers and state clearly:

- bookmaker;
- selection;
- decimal odds;
- last checked time;
- best current price found.

## 8.3 Arbitrage / price-difference detection

Sabi should identify cases where the best prices across different bookmakers cover all outcomes in a way that creates a positive price difference.

The engine must verify that the markets truly match before treating it as an opportunity.

Verification includes:

- same event;
- same participants;
- same market;
- same line;
- same period;
- same overtime/extra-time treatment;
- same void/retirement rules where relevant;
- fresh prices.

Sabi should be able to calculate how a chosen total amount would need to be split across the outcomes.

The user-facing explanation should stay simple.

## 8.4 Related opportunity types

V2 should leave room for:

- price outliers;
- stale prices;
- middles;
- bookmaker disagreements;
- cross-market inconsistencies;
- exchange/bookmaker combinations where appropriate.

---

# 9. Ticket Workshop

Ticket Workshop is one of the defining V2 capabilities.

It lives primarily through Sabi/OpenClaw conversation, not as a dashboard betting interface.

## 9.1 Accepted ticket inputs

Sabi should accept:

- booking code;
- screenshot/image;
- X/Twitter post link;
- copied text;
- bookmaker share text;
- plain instruction;
- a list of matches;
- a list of selections;
- an existing Sabi ticket.

## 9.2 Ticket extraction

For an imported ticket, Sabi should identify where possible:

- bookmaker;
- event;
- home team;
- away team;
- competition;
- kickoff;
- market;
- selection;
- line;
- decimal odds;
- combined odds;
- booking code;
- source.

Ambiguous items should be resolved through event/bookmaker lookup when possible.

## 9.3 Edit tickets

Sabi must support instructions such as:

- split a large slip into smaller slips;
- split strongest games across multiple slips;
- remove games;
- remove the weakest games;
- replace a game;
- change markets across a ticket;
- make selections more conservative;
- make selections more aggressive;
- trim the ticket toward a requested combined-odds target;
- keep a requested number of games;
- exclude a sport/league/bookmaker;
- preserve specified picks while editing the rest.

## 9.4 Trim to target odds

A user should be able to say:

- “Trim this ticket to around 10 odds.”
- “Bring this 45 odds ticket closer to 20.”
- “Keep at least 6 games but lower the total odds.”

Sabi should explore combinations of:

- removing selections;
- replacing selections;
- changing markets;
- lowering individual selection risk;

and return a clear explanation of what changed.

## 9.5 Convert tickets between bookmakers

Sabi should be able to convert tickets where supported.

Example workflow:

1. import Stake/Bet9ja/SportyBet/etc. ticket;
2. normalize all events and selections;
3. search the target bookmaker for the same events;
4. map equivalent markets;
5. detect unavailable selections;
6. propose equivalent replacements when needed;
7. rebuild the ticket;
8. return the target booking code if the bookmaker supports code creation.

## 9.6 Screenshot to ticket

Sabi should be able to read screenshots using vision, reconstruct the selections, verify the matches/markets, and then:

- research them;
- edit them;
- split them;
- convert them;
- rebuild them;
- generate a supported booking code.

## 9.7 X/Twitter post to ticket

Given an X post link, Sabi should extract sports selections from the post/media where accessible, normalize them, research them and optionally rebuild them on a supported bookmaker.

Sabi should not blindly copy a post when the user asks it to check the selections first.

## 9.8 Instruction to booking code

The ideal experience:

> “Arsenal or Draw, Barcelona Over 1.5 goals, Inter to win. Build it on SportyBet.”

Sabi should:

1. resolve the correct fixtures;
2. verify the markets;
3. optionally research them if context suggests it;
4. build the bookmaker slip;
5. return the booking code where supported;
6. show the final selections and decimal odds clearly.

## 9.9 Ticket history

Tickets that matter to our SabiAI history should be recordable with:

- original ticket;
- edited versions;
- final version;
- bookmaker;
- combined odds;
- selections;
- result;
- ticket-level win/loss;
- individual leg results;
- which leg caused a losing multi-game ticket;
- notes;
- Sabi recommendations made before use.

This data belongs in the dashboard after the fact.

---

# 10. Sabi Conversation Capabilities

Sabi should naturally understand requests around:

## Match research
- “Check this match.”
- “Compare the two teams.”
- “Show me recent form.”
- “Check injuries.”
- “Check H2H.”
- “Check home and away form.”
- “What about corners?”
- “What about cards?”
- “What about shots?”

## Sports discovery
- “Find me volleyball today.”
- “No football.”
- “Look at esports.”
- “Anything interesting in golf?”
- “Check smaller sports too.”

## Bookmakers
- “Which bookmaker has the best odds?”
- “Find this market on Bet9ja.”
- “Convert this ticket.”
- “Can SportyBet book this?”

## Ticket work
- “Split this.”
- “Trim this.”
- “Make this lower odds.”
- “Replace the weakest game.”
- “Keep only the strongest 5.”
- “Build this on SportyBet.”

## Our own history
- “How have we done with volleyball?”
- “What is our current streak?”
- “Which market keeps hurting us?”
- “How are our tickets around 10 odds doing?”
- “How often does one game kill our slips?”

---

# 11. OpenClaw-Native Tool Layer

Sabi should expose clean skills/tools rather than forcing the agent to know database internals.

Suggested capability groups:

## Sports
- discover sports/competitions;
- resolve events;
- fetch fixtures;
- compare teams/players;
- fetch sport-specific stats.

## Research
- search public sources;
- run event research;
- injury/team-news check;
- source discovery;
- source freshness check.

## Markets/bookmakers
- find event at bookmaker;
- list markets;
- fetch odds;
- compare bookmakers;
- detect price differences;
- map bookmaker market labels.

## Tickets
- import booking code;
- parse screenshot;
- parse social post;
- normalize slip;
- split slip;
- trim to odds;
- change markets;
- convert bookmaker;
- rebuild slip;
- create booking code.

## Records
- record pick;
- record ticket;
- settle pick;
- settle ticket;
- query history;
- query streak;
- query performance.

## Blog
- draft daily note;
- write reflection;
- publish blog post;
- tag/categorize article.

## System
- source health;
- job health;
- cache health;
- last successful research/settlement;
- paid-call usage.

---

# 12. Specialist Workers

Sabi remains one identity, but may use temporary specialist workers where useful.

Examples:

- football researcher;
- basketball researcher;
- volleyball researcher;
- esports researcher;
- source scout;
- bookmaker price shopper;
- ticket converter;
- result checker;
- skeptic/reviewer.

Workers are not separate products or personalities. They are temporary helpers coordinated by Sabi.

A skeptic/reviewer worker may be used to challenge an important ticket or research conclusion by looking for missing injuries, stale information, wrong event mapping, unsupported assumptions or conflicting evidence.

---

# 13. Read-Only Dashboard V2

## 13.1 Dashboard mission

The dashboard tells the story of **our SabiAI activity**.

It uses graphs, charts, tables and simple summaries to monitor our data.

It should not turn into a live sports website.

## 13.2 Dashboard information hierarchy

### Overview
Show at-a-glance:

- current bankroll;
- money currently in play where tracked;
- today’s result;
- this week/month result;
- total profit/loss;
- overall win/loss/draw record;
- current streak;
- best streak;
- worst streak;
- pending selections;
- recent tickets;
- recent Sabi blog post;
- simple trend graphs.

### Picks / Games
Our recorded selections only.

Fields may include:

- date;
- sport;
- competition;
- home team;
- away team;
- selection;
- decimal odds;
- bookmaker;
- strategy/channel;
- result;
- notes.

### Tickets
Our ticket history.

Show:

- bookmaker;
- date;
- number of games;
- combined odds;
- result;
- legs won/lost/pending;
- ticket killer where applicable;
- source: user-built / Sabi-built / converted / screenshot / X post;
- parent/child relationship for edited or split tickets.

### Performance
Charts and graphs based on our own data:

- win rate over time;
- profit/loss over time;
- bankroll over time;
- performance by sport;
- performance by market;
- performance by bookmaker;
- performance by strategy;
- performance by odds range;
- singles vs multi-game tickets;
- ticket size vs results;
- combined-odds ranges;
- home/away selection performance where meaningful;
- time-of-day/day-of-week where meaningful;
- streak history;
- confidence bands versus actual outcomes using plain labels.

### Finance
Read-only finance view:

- starting bankroll;
- current bankroll;
- deposits/withdrawals if recorded;
- total staked;
- total returned;
- profit/loss;
- bankroll chart;
- strategy-level money performance;
- bookmaker-level money performance.

### Strategies
Track existing and future Sabi channels such as:

- Kelly picks;
- Compound chain;
- Weekly Long Shot;
- Live selections;
- future named strategies.

For each:

- played;
- won;
- lost;
- pending;
- profit/loss;
- streak;
- historical graph.

### History
Full searchable/filterable archive.

### Blog
Sabi’s written journal/blog.

### System
A small read-only system-health page for maintenance, not a user-facing control panel.

## 13.3 Dashboard must grow with our data

Do not hard-code football-only charts.

If we begin recording volleyball, esports, golf, darts or other sports, the dashboard should automatically show those sports in our own historical breakdowns.

---

# 14. Sabi Blog

The current diary evolves into a real Sabi blog.

## 14.1 Purpose

The blog gives Sabi continuity and a voice.

It should record:

- what Sabi is seeing;
- what Sabi is learning;
- what worked;
- what failed;
- patterns in our own history;
- thoughts on sports/markets;
- interesting bookmaker differences;
- reflections on tickets;
- changes in Sabi’s thinking.

## 14.2 Post types

Suggested categories:

- Daily Briefing
- What I’m Watching
- Sabi’s Thoughts
- What I Learned
- Ticket Review
- Sport Deep Dive
- Week in Review
- Mistakes & Lessons
- Market Watch

## 14.3 Blog tone

Plain English.

Personal, observant and useful.

Not generic AI filler.

The blog should refer back to Sabi’s own prior posts and historical data when appropriate.

Example:

> “Three weeks ago I said I wanted to watch our volleyball set selections more closely. We now have enough recorded games to see that the pattern is holding better than it was in football totals, so I’m keeping it on my radar.”

## 14.4 Blog data model

A post should support:

- title;
- slug;
- body;
- excerpt;
- published time;
- category;
- tags;
- related sports;
- related picks/tickets;
- status/draft if needed;
- optional featured image later.

---

# 15. History and Learning

SabiAI should learn from **our own record** without exposing technical language.

The system should be able to answer:

- Which sports are going well for us?
- Which markets are going badly?
- Are we better at singles or larger tickets?
- What combined-odds range has worked best?
- How often does one game ruin a large ticket?
- Are Sabi-edited tickets doing better than the originals?
- Do converted tickets perform differently?
- Which bookmakers have given us better prices?
- Which types of selections repeatedly cause losses?
- Are we improving over time?

Internally, V2 may use advanced statistical methods, but the dashboard and Sabi should present conclusions in normal language.

---

# 16. Ticket Lineage

V2 should preserve the life of a ticket.

Example:

```text
Imported ticket
  -> Sabi researched
  -> Removed 3 games
  -> Changed 2 markets
  -> Split into Ticket A and Ticket B
  -> Converted Ticket A to SportyBet
  -> Final booking code created
  -> Ticket settled
```

This history enables future questions such as:

- Did the original ticket perform better or worse than Sabi’s edited version?
- Did the game Sabi removed lose?
- Did the replacement improve the ticket?
- Which editing actions are helping most?

---

# 17. Canonical Event and Identity Rules

V2 needs reliable identity mapping so one match is recognized as the same event across websites and bookmakers.

Canonical entities include:

- sport;
- competition;
- season/tournament;
- team;
- player;
- event;
- bookmaker event;
- market;
- selection;
- ticket;
- pick;
- result.

Aliases must be supported because names vary between sources.

Examples:

- Man United / Manchester United;
- Inter / Internazionale;
- Team abbreviations;
- esports organization naming changes.

A wrong event mapping can ruin ticket conversion and bookmaker comparison, so event identity is a foundation feature.

---

# 18. Results and Settlement

Settlement must be reliable and sport-aware.

V2 should support:

- automatic result checks where possible;
- manual settlement fallback;
- ticket-level settlement;
- leg-level settlement;
- void/push/cancelled states where relevant;
- draw as a real event result where applicable;
- sport-specific rules;
- bookmaker-specific rule differences where needed.

The dashboard should clearly use familiar result states such as:

- Won
- Lost
- Draw
- Void
- Pending

---

# 19. Data Quality and Source Health

Sabi should know when its information is stale or incomplete.

The user-facing wording stays simple:

- “Latest team news checked 8 minutes ago.”
- “I could not confirm the starting lineup yet.”
- “This league has thinner public data than usual.”
- “Two sources disagree about this player’s availability.”

Internally, source health should track:

- freshness;
- successful fetches;
- failures;
- rate limiting;
- last update;
- coverage;
- confidence.

---

# 20. API Cost Awareness

V2 should explicitly track paid-resource usage.

For every metered source, maintain:

- provider;
- request count;
- why it was used;
- cache status;
- estimated cost where known;
- whether a free source had already been attempted.

Sabi should prefer reusing research and cache rather than repeating paid calls.

This may be visible only on the System page, not the main dashboard.

---

# 21. Security and Control Boundaries

The public/read-only dashboard should not expose write keys or sensitive bookmaker/session credentials.

Any write/mutation actions belong behind authenticated OpenClaw or trusted internal tools.

Do not place secrets in query strings, browser local storage or public page source.

Different classes of capability should be separated internally:

- read-only research;
- record/history writes;
- ticket reconstruction;
- bookmaker session interactions;
- administrative/system actions.

The dashboard remains read-only.

---

# 22. V2 UX Rules

## 22.1 Sabi responses

Responses should be:

- direct;
- explicit;
- easy to understand;
- decimal-odds based;
- team-name based;
- sport-aware;
- concise unless the user asks for detail.

## 22.2 Explain unfamiliar markets simply

Example:

> **Arsenal +1.5 handicap** means Arsenal can win, draw, or lose by one goal and this selection still wins. If Arsenal lose by two or more goals, it loses.

## 22.3 Do not lecture the user

Sabi should focus on doing the requested work.

Avoid repetitive boilerplate warnings, generic gambling disclaimers, or patronizing explanations.

## 22.4 Show changes clearly when editing tickets

For ticket edits, show:

- what stayed;
- what was removed;
- what changed;
- what was added;
- old combined odds;
- new combined odds;
- final bookmaker/code when available.

---

# 23. Example V2 Workflows

## 23.1 Research a booking code

User:
> “Check this SportyBet code.”

Sabi:
1. loads the ticket;
2. extracts all selections;
3. verifies events;
4. researches each relevant market;
5. checks injuries/team news;
6. identifies weak/uncertain legs;
7. explains findings plainly;
8. optionally proposes a revised ticket;
9. records the ticket if requested/appropriate.

## 23.2 Split a ticket

User:
> “Split this 12-game ticket into 3.”

Sabi:
1. imports ticket;
2. checks each selection;
3. ranks confidence using internal evidence;
4. spreads selections according to instruction;
5. returns 3 clear tickets;
6. builds booking codes where supported.

## 23.3 Convert bookmaker

User:
> “Convert this Bet9ja code to SportyBet.”

Sabi:
1. loads Bet9ja ticket;
2. maps events/selections;
3. finds the same matches on SportyBet;
4. maps equivalent markets;
5. highlights substitutions when exact equivalents do not exist;
6. creates the SportyBet slip;
7. returns final code and decimal odds.

## 23.4 Research outside football

User:
> “Find me interesting volleyball and basketball games tonight. No football.”

Sabi:
1. discovers relevant fixtures;
2. researches public sources;
3. checks bookmaker markets/prices;
4. compares form and availability;
5. returns clear candidates in normal language.

## 23.5 Blog reflection

Scheduled Sabi task:
1. inspect our recent history;
2. identify notable patterns/events;
3. write an original blog post;
4. link related picks/tickets where useful;
5. publish to dashboard blog.

---

# 24. What V2 Is Not

V2 is not:

- a football-only prediction engine;
- a generic sports-news portal;
- a live-score clone;
- a bookmaker front end;
- a technical ML dashboard;
- a dashboard for placing wagers;
- a system dependent on paid APIs for routine research;
- a system where bookmaker odds substitute for independent sports research;
- a collection of isolated scripts with no OpenClaw intelligence layer.

---

# 25. Product North Star

SabiAI V2 should feel like this:

> Sabi knows sports broadly, can go learn unfamiliar competitions, checks the web before spending paid API calls, understands the markets bookmakers use, can read and rebuild slips, can compare bookmakers, can work from booking codes/screenshots/social posts/plain instructions, remembers our history, speaks in normal language, and keeps an honest record of what we actually did through a read-only dashboard and its own continuing blog.

That is the V2 product.
