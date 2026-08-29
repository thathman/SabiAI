# Sabi Boy V2.4 — Coverage Engine

Status: integrated candidate on `feature/v2.4-coverage-integration` (Forgejo promotion pending final Dell staging)

## Goal

Make Sabi Boy see far more real games and bookmaker markets without solving coverage by spending more model tokens.

V2.4 separates deterministic discovery from model research:

`Discovery Radar → Source Union → Canonical Event Index → Market Inventory → Deterministic Prefilter → Sharded Research → Decision → SportyBet/Bet9ja Verification`

## What changed

### Discovery breadth

- Standard rolling discovery horizon: 72 hours.
- Golf/motorsport/cycling horizon: up to 7 days.
- MMA/boxing event horizon: up to 14 days.
- Discovery ceiling: 2,000 canonical events per refresh.
- Automatic model research ceiling remains separately bounded at 120 events.
- Proactive sport registry adds American football, horse racing, greyhound racing, rugby league, athletics and winter sports.

### Multi-source union

Sources are additive. The radar no longer assumes that one successful fixture source means the sport is completely covered. Canonical events keep provider-scoped IDs so source identifiers are never mixed.

Frequent discovery uses `coverage_source_bundle()`. Parse-backed sources are omitted from the 30-minute radar unless `SABIAI_DISCOVERY_PARSE_UNION=1` because free-tier Parse credits are finite.

### Market inventory

V2.4 persists market existence separately from price observations. Exact offers can retain:

- market family;
- metric;
- period;
- participant;
- side;
- line;
- selection;
- bookmaker/source;
- decimal odds;
- observed time;
- source market/outcome IDs.

Ordinary team sports attempt winner + handicap/spread + total as the minimum market-family baseline. Deeper families include DNB, BTTS, team totals, corners, cards, player props, sets/maps, combat method/rounds, outrights, placement, make-cut and matchups.

### Broad market sensors

Optional read-only sensors:

- The Odds API event discovery — separated from quota-consuming odds calls.
- The Odds API market pricing — explicit metered gate, OFF by default.
- Betfair Exchange — read-only event/market catalogue and best-back prices; no order mutations.

Sensor prices are never automatically promoted as playable Sabi Boy prices.

The research-cycle action-price enricher makes the action-book side explicit. It issues one
cached Parse SportyBet fixture request per verified sport (football, basketball and ice hockey),
normalizes the complete returned same-day slate, and persists every eligible event and embedded
SportyBet offer into the market inventory. It is model-free, does not run on the 30-minute radar,
and is bounded only by `SABIAI_ACTION_PRICE_MAX_EVENTS_PER_SPORT` (default 1,000). The daily
collector and enricher share request keys, so the enrichment pass reuses the collector response
instead of spending a second Parse credit.

### Action-book boundary

SportyBet and Bet9ja remain the action books.

The deterministic prefilter can use all fresh sensor prices for consensus/disagreement and event priority, but the `odds` field sent into automatic pick research contains only one coherent action-book price set. Sensor-only events remain visible through the radar and `research.action_price.gaps` until an exact fresh SportyBet/Bet9ja offer is verified.

### Research allocation

Every active sport gets a small breadth floor. Remaining model capacity is quality-led and subject to the per-sport maximum. This replaces forced equal shares after coverage has been established.

### Near-start market refresh

Deep/metered market enrichment is tiered while the cheap radar remains frequent:

- T-24h band: up to every 6 hours;
- T-12h band: up to every 3 hours;
- T-6h band: up to every 90 minutes;
- T-90m band: up to every 30 minutes.

Deep-market calls remain OFF unless explicitly enabled.

### Observability

OpenClaw tools:

- `research.discovery.refresh`
- `research.radar`
- `research.market_inventory`
- `research.event.sources`
- `research.coverage.funnel`
- `research.action_price.gaps`

Dashboard System telemetry shows:

- discovered events;
- freshly priced events;
- market catalogue size;
- fresh price observations;
- deterministic prefilter count;
- researched count;
- selected count;
- per-sport sources, market families and missing minimum coverage.

## Runtime defaults

The new environment controls are documented in `config/sabi-boy.env.example`. Important safe defaults:

- `SABIAI_DISCOVERY_PARSE_UNION=0`
- `SABIAI_COVERAGE_METERED_MARKETS=0`
- `SABIAI_COVERAGE_DEEP_MARKETS=0`
- generic paid escalation remains independently controlled.

The no-model radar is installed as `sabi-boy-coverage.service` + `sabi-boy-coverage.timer` and runs every 30 minutes.

## Acceptance requirements

Before V2.4 promotion, Work/Dell must:

1. rebase/transplant the feature branch onto the actual latest Forgejo/local baseline;
2. run the complete pytest suite;
3. run `scripts/sabi_v24_coverage_acceptance.py`;
4. run the deterministic radar without metered sources and confirm no model call is made;
5. compare V2.3 vs V2.4 discovered-event counts for at least football, basketball, tennis, volleyball and two niche sports;
6. confirm future (+24h to +72h) events are visible but are not included in today's automatic pick run;
7. confirm a common event discovered by two sources is canonicalized once with both provider IDs;
8. confirm stale offers do not count as current pricing;
9. confirm winner/handicap/total market-family coverage when the provider exposes those markets;
10. confirm sensor-only prices appear in the action-price-gap queue and cannot become automatic recorded picks;
11. confirm fresh SportyBet/Bet9ja offers resolve an action-price gap;
12. confirm one SportyBet response containing N priced events persists all eligible N events and offers;
13. if a metered sensor is enabled for acceptance, cap the test tightly and record quota before/after;
14. verify the System dashboard funnel on desktop/mobile/PWA;
15. verify the coverage timer, research timer and rollback posture.

## Success criteria

The upgrade is successful when Sabi Boy's discovered/priced/market universe grows materially while:

- automatic model requests stay bounded;
- action-book verification remains strict;
- source/provider IDs remain isolated;
- no additional wager-placement capability exists;
- metered/limited sources remain explicit and measurable;
- broader visibility does not force more recommendations.
