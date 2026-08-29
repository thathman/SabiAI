---
name: sabi-boy-coverage-engine
description: Use when Sabi Boy needs to discover more upcoming games, inspect broad multi-sport coverage, understand available bookmaker markets, compare sensor coverage with SportyBet/Bet9ja availability, or diagnose why an event/market was not researched.
---

# Sabi Boy V2.4 Coverage Engine

The coverage engine separates **seeing the sports market** from **spending model attention**.

Never treat `not researched` as `the game does not exist`.

## Canonical pipeline

1. **Discovery Radar** — large deterministic event universe, no model.
2. **Multi-source union** — sources contribute together; one successful provider never suppresses another provider's extra competitions.
3. **Canonical Event Index** — one event can retain several provider-scoped IDs.
4. **Market Inventory** — persist exact market family, line, period, participant, bookmaker/source and observed decimal price.
5. **Deterministic prefilter** — use coverage, price freshness, cross-book consensus/disagreement and action-book availability to decide what deserves expensive research.
6. **Bounded sharded research** — only a much smaller sport-balanced universe reaches the model.
7. **Decision / ticket work** — exact SportyBet or Bet9ja price must still be verified before action-oriented ticket work.

## Tool surface

Use:

- `research.radar` — broad upcoming event universe. Standard horizon is 72 hours; long-horizon sports can extend further.
- `research.market_inventory` — exact known market catalogue and fresh price observations for one canonical event.
- `research.event.sources` — provider IDs/source history for one canonical event.
- `research.coverage.funnel` — discovered → priced → prefiltered → researched → selected telemetry.
- `research.discovery.refresh` — explicit deterministic refresh. This does not wake the research model.

The dashboard System view is read-only coverage telemetry; it is not a generic sports-fixtures page.

## Sensor books versus action books

Broad bookmaker/odds/exchange sources are **market sensors**. They may tell Sabi Boy:

- that an event exists;
- which market families exist;
- broad market consensus;
- whether a price looks unusually high/low;
- which niche markets deserve attention.

They do **not** automatically become playable prices.

Automatic recommendation odds are restricted to the configured action books:

- SportyBet
- Bet9ja

A sensor-only event remains visible and can become WATCH / WAIT / research material. Before automatic pick/ticket promotion, obtain a fresh exact SportyBet or Bet9ja offer for the same event, market, line, participant and period.

Never substitute a nearby line because it has a better price.

## Market breadth

For ordinary team sports, attempt at least:

- Winner
- Handicap / spread
- Total

Then preserve sport-specific deeper markets when they exist, including team totals, Draw No Bet, BTTS, corners, cards, player props, set/map markets, combat method/round markets, outrights, placements, make-the-cut and matchups.

For golf/motorsport/cycling expect outright + placement + matchup style coverage. For MMA/boxing expect winner + method + total-round style coverage. Unknown/new sports should learn their real bookmaker market taxonomy rather than being rejected.

## Horizons

Default discovery posture:

- normal sports: rolling 72 hours;
- golf, motorsport and cycling: up to 7 days;
- MMA and boxing event discovery: up to 14 days.

Today's automatic research remains today's research. A game visible tomorrow should not become today's pick merely because the radar saw it.

## Cost discipline

Frequent radar refreshes must remain deterministic/no-model.

Do not enable metered market calls merely because an API key exists. `SABIAI_COVERAGE_METERED_MARKETS` is a separate explicit gate.

Parse-backed sources consume limited credits and are excluded from the frequent union by default. `SABIAI_DISCOVERY_PARSE_UNION` must be explicitly enabled to change that.

The Odds API event discovery and its metered odds calls are separate adapters. Betfair integration is read-only market/event/price sensing; Sabi Boy has no exchange order mutation path.

## Coverage diagnosis

When coverage looks weak, diagnose in this order:

1. Was the sport scanned?
2. Was the event discovered?
3. How many independent sources saw it?
4. Was any market catalogue discovered?
5. Were fresh prices observed?
6. Were minimum market families missing?
7. Was a SportyBet/Bet9ja action price available?
8. Did deterministic prefiltering exclude it?
9. Did model research reject it?
10. Did the Decision Pass reject it?

Do not answer a coverage problem by simply increasing model tokens.
