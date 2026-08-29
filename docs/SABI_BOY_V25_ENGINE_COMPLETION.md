# Sabi Boy V2.5 engine completion

This document records the V2.5 intelligence-engine contract on the isolated
`feature/v2.5-non-football-coverage` branch. V2.4 production remains frozen at
`2ead1725b7b0eac4a95f05eef78bbbb5556cfdcd`.

## Scope

V2.5 makes the research path deterministic and inspectable across the complete proactive
sport universe:

```text
discover → identify → profile the sport → inventory the exact market
→ price and remove margin → verify SportyBet/Bet9ja price
→ build sport-specific evidence → apply the evidence gate
→ estimate probability → calculate value → BET / BET IF PRICE / WATCH / PASS
→ record the exact decision context → settle → calibrate
```

The engine has first-class contracts for 31 proactive sports. Unknown sports remain a
discovery case and are not silently treated as a supported team sport. Race, field, and
fight events cannot be promoted from a fixture or price alone.

## Deterministic controls

- Exact offers are addressed by an immutable `offer:<hash>` containing the event, bookmaker,
  market, line, period, participant, selection, price, and observation time.
- Pricing exposes raw implied probability, margin, no-vig consensus, fair odds, expected value,
  and break-even odds. Market lines are part of the identity, so adjacent totals cannot mix.
- Evidence is built free-first and bounded before the decision model. Missing evidence becomes
  an ordered recovery chain rather than a false “no data” conclusion.
- The action-book registry is intentionally limited to SportyBet and Bet9ja. Other sensors may
  improve discovery and consensus, but they cannot become an automatic recorded action price.
- Engine decision context is stored beside `picks_v2` without changing that canonical ledger.
  It preserves the exact offer, probability/value facts, decision state, evidence quality and
  sources used at selection time.
- Calibration is descriptive by probability band, expected-value band, sport, and market.
  Fewer than eight settled examples remain `immature`; no policy is changed automatically from
  a small sample.

## Gateway surface

The following deterministic tools are exposed at the OpenClaw boundary:

| Tool | Purpose |
| --- | --- |
| `engine.completeness` | Separate engine-code completeness from live source coverage |
| `engine.sport_profile` | Inspect one sport’s event, market, evidence, and settlement contract |
| `engine.next_actions` | Return the ordered recovery chain for an event or event list |
| `engine.price.assess` | Calculate value and the decision state for an exact decimal price |
| `engine.evidence.build` | Build a bounded free-first evidence packet |
| `engine.calibration` | Read settled decision calibration views |

The acceptance helper `scripts/sabi_v25_engine_acceptance.py` checks these tools, the 31
profiles, schema migration 18, pricing math, and the recovery planner without calling a model,
bookmaker, or metered source.

## Status boundary

“Engine complete” means the architecture and contracts are present and tested. It does not
claim that every sport has fresh prices on every day. A daily report may therefore truthfully
show `ENGINE COMPLETE — source coverage DEGRADED` while the code remains complete. Expanding
non-football price sensors is a subsequent coverage phase, not a reason to weaken the evidence
or action-book gates.

## Acceptance evidence

Run the deterministic helper with an isolated database:

```text
.venv/bin/python scripts/sabi_v25_engine_acceptance.py --db /tmp/sabi-v25-acceptance.db
```

Then run the complete suite:

```text
.venv/bin/python -m pytest -q
```

The Dell isolated acceptance has now proven the exact branch commit, migration, scheduled
persistence, full pytest suite, live source coverage behavior, settlement/readiness startup,
and dashboard/PWA smoke without changing the V2.4 runtime. In-place activation and public
cutover remain separate authorised gates.

## Approved source expansion

The V2.5 branch now includes a single normalized adapter boundary for the approved source
wave. API-Sports, SportsGameOdds, PandaScore, SportsDataIO and SportMonks are optional
authenticated/metered sensors; they are never queried by the no-model coverage radar unless an
explicit paid-access decision allows the request. SportsGameOdds is a market sensor only and
cannot become an action bookmaker. SportyBet and Bet9ja remain the only action-price boundary.

Jolpica F1 and OpenLigaDB are public structured corroboration sources, NBA LiveData is a
medium-reliability public scoreboard corroborator, and FastF1, Cricsheet and StatsBomb/Hudl
Open Data are local/cache-backed analytical sources. Local datasets are read from runtime paths
and are not committed to the repository. Missing optional credentials or datasets are surfaced
as explicit `not_configured`/disabled source states.

The implementation is `cdfad54` with regression coverage in `c4fecde`. The local full suite at
this point is **360 passed, 1 warning**. Dell live source probes, private credential wiring for
the isolated V2.5 runtime, and final source-funnel acceptance remain controlled release gates;
V2.4 production is unchanged.

## Dell acceptance snapshot

At `19d03cba4426c9fc07b320967d13b958cd3e98d4`:

- 347 tests passed with one known Starlette/httpx deprecation warning.
- The deterministic helper passed all checks and reported schema 18.
- The source collector returned 48 same-day events across six sports; 33 had fresh
  Parse Flashscore/SportyBet prices with no source failures.
- The isolated Alibaba-backed run considered 16 events, produced two recommendations, one
  Sabi Boy precision pick and one Daily 1.30 Chain ticket, and used the configured fallback
  for one sibling slice. Push delivery was disabled for isolation.
- The active production checkout stayed on V2.4 SHA
  `2ead1725b7b0eac4a95f05eef78bbbb5556cfdcd` with its existing timers and route untouched.
