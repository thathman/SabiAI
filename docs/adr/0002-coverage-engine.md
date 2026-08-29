# ADR 0002 — Separate discovery coverage from model research

Status: Accepted for V2.4
Date: 2026-08-28

## Context

Sabi Boy V2.3 had strong sharded research but its upstream event universe was still too small. The scheduled collector was day-scoped, globally event-limited, and often treated sources as fallbacks. The market interpreter understood more markets than the fixture payloads exposed. Increasing model effort would not solve games or markets that were never ingested.

## Decision

V2.4 separates the pipeline into four increasingly expensive universes:

1. **Discovery universe** — large deterministic/no-model upcoming event radar.
2. **Priced/market universe** — persistent exact market catalogue and observed prices.
3. **Research universe** — bounded deterministic shortlist with sport breadth.
4. **Action universe** — researched selections with an exact fresh SportyBet/Bet9ja price and normal decision/risk gates.

The canonical flow is:

`DISCOVERY RADAR → SOURCE UNION → CANONICAL EVENT INDEX → MARKET INVENTORY → DETERMINISTIC PREFILTER → SHARDED RESEARCH → DECISION → TARGET-BOOK VERIFY`

## Source union

Fixture sources are additive. A successful response from one source does not suppress extra events available from another. Canonical events retain provider-scoped IDs so provider identifiers are never treated as globally interchangeable.

Frequent discovery defaults to genuinely cheap/public fetchers. Parse-backed adapters remain available elsewhere but are omitted from the frequent union unless explicitly enabled because free-tier Parse credits are still finite.

## Discovery horizons

- standard sports: rolling 72 hours;
- golf, motorsport, cycling: up to 7 days;
- MMA and boxing: up to 14 days.

Today's automatic pick run remains day-scoped even though the radar sees further ahead.

## Market inventory

The inventory stores market family, metric, line, period, participant, side, selection, bookmaker/source, decimal price and observed time. Market existence and price observations are separate concepts.

Ordinary team sports should attempt at least winner, handicap/spread and total coverage. Sport-specific extensions may include team totals, DNB, BTTS, corners, cards, player props, set/map markets, combat method/rounds, outrights, placements, make-cut and matchups.

## Sensor versus action price

Broad odds providers and exchanges are market sensors. Their prices can contribute to consensus, disagreement and deterministic prioritization, but they do not automatically become recorded/actionable picks.

Automatic recommendation odds are restricted to fresh exact SportyBet or Bet9ja offers. Sensor-only events stay visible for WATCH/WAIT/on-demand research until an action-book price is verified.

## Cost controls

The no-model radar refreshes independently from model research. The default architecture may retain thousands of events/markets while sending only a bounded subset to the model.

The Odds API discovery surface is separate from quota-consuming odds calls. Metered market calls require the explicit `SABIAI_COVERAGE_METERED_MARKETS` gate. Deep-market enrichment is separately gated. Betfair integration is read-only; no exchange order mutation is implemented.

## Allocation

Multi-sport breadth is protected with a small per-active-sport floor. Remaining model capacity is quality-led rather than forced into equal sport shares. Per-sport caps still prevent one large sport from monopolizing the research universe.

## Observability

The read-only System dashboard/OpenClaw expose:

`discovered → priced → market catalogue → price observations → prefiltered → researched → selected`

plus per-sport sources, market families and missing minimum market coverage.

## Consequences

- A missing recommendation can now be diagnosed as discovery, pricing, market-coverage, prefilter, research or decision failure.
- Broadening sports coverage does not linearly increase model cost.
- Market sensors can improve price intelligence without becoming supported ticket-building bookmakers.
- More events seen must not be interpreted as a requirement to make more picks; rejection remains a core outcome.
