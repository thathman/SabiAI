---
name: sabi-boy-bookmaker-workflows
description: Search bookmakers, compare decimal prices, restore booking codes, convert tickets, build codes, and verify rebuilt slips.
---

# Sabi Boy — Bookmaker Workflows

Use for bookmaker search, booking-code restore, cross-book conversion, best-price checks, ticket rebuilds and generated-code verification.

## Principles

- Decimal odds only.
- Explicit event and participant names.
- Exact market + line + period equivalence.
- Fresh prices are required for conversion/building.
- A known bookmaker is not automatically a proven importer or builder.
- Never silently substitute another line/period/event.
- Booking-code creation is different from wager placement; this workflow only builds reusable codes.

Use `bookmaker.browser_health` when deciding whether a browser playbook is merely configured or has actually been exercised recently. An unexercised path must not be described as live-proven.

Use `market.settlement.profile` before treating uncertain cross-book markets as equivalent. When it says bookmaker verification is required, confirm the listed rule topics on each book before comparison/conversion.

## Restore a booking code

1. `bookmaker.resolve`
2. `bookmaker.booking_code.import_plan`
3. Follow the returned browser restoration playbook when needed.
4. Extract every visible leg and decimal price.
5. `bookmaker.booking_code.restore`
6. Save/continue from the canonical restored draft.

## Search prices across bookmakers

1. `bookmaker.compare.plan`
2. Follow each ready bookmaker's market-search playbook.
3. Match both event participants.
4. Match exact market/line/period.
5. Capture decimal odds and `observed_at`.
6. Send all bookmaker results together to `bookmaker.compare.from_search`.

Old ticket odds are context, not automatically current.

## Convert a ticket

1. Start from normalized/restored source ticket or `draft_id`.
2. `bookmaker.search.plan` for target book.
3. Search exact target offers.
4. `bookmaker.convert.from_search` with fresh timestamps.
5. Require every leg to match event, sport, market type, metric, line, period and selection side/participant.
6. Preserve the converted draft and price observations.

## Build a code

Preferred rich path when available:

1. `bookmaker.browser_build.plan`
2. Use the returned exact per-leg browser tasks.
3. Confirm visible event/market/line/period/price after every selection.
4. Use the bookmaker's Book Bet / booking-code action only.
5. Capture the generated code.
6. Reload the code.
7. `bookmaker.build.verify` against the converted draft.
8. Return the code only when structure verification passes.

Current rich-code creation truth:

- SportyBet — V2 browser build playbook exists; runtime acceptance must still prove the live page.
- Bet9ja — V2 browser build playbook exists; runtime acceptance must still prove the live page.
- Stake — restoration/search may work, code creation not yet claimed.
- 1xBet — regional restore/search/build flow still requires live verification before being claimed.

Legacy `bookmaker.build.plan` / `bookmaker.build.execute` are compatibility paths only and must obey their declared sport/market limits.

## Rebuild verification

`bookmaker.build.verify` distinguishes:

- correct structure + same price;
- correct structure + changed price;
- wrong market/line/period/event;
- extra/missing leg.

Price movement is not the same as rebuilding the wrong ticket.

## History

Use `history.bookmaker_prices` and `history.price_disagreements` for historical observations. They are not substitutes for current-price search; fresh comparison tools remain authoritative for a build/conversion.

## Lineage

Preserve:

`original input → restored draft → researched/edited draft → converted draft → generated code → verified-built draft`
