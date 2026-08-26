# Sabi Boy V2 — Bookmaker, Price Search, Conversion & Rebuild Workflows

Use this skill whenever the user asks Sabi Boy to search bookmakers, compare prices, load a booking code, convert a ticket, rebuild a ticket, create a booking code, or verify a rebuilt code.

The authoritative tool inventory is always `system.tools`. Do not claim a capability merely because a bookmaker is known by name.

## User-facing language

- Decimal odds only.
- Explicit participant names: `Arsenal to win`, not `Home ML`.
- Explicit lines: `Arsenal +1.5 handicap`, `Over 2.5 goals`.
- Keep home/away identity clear when it matters.
- Do not expose internal refs/IDs unless troubleshooting is explicitly requested.

## 1. Load an existing booking code

1. Resolve the bookmaker with `bookmaker.resolve`.
2. Call `bookmaker.booking_code.import_plan`.
3. Use the returned browser restoration playbook when direct import is not proven.
4. Restore the slip without stake/payment/wager placement.
5. Extract every visible leg, decimal price, displayed leg count and combined odds.
6. Call `bookmaker.booking_code.restore`.
7. Continue only from the canonical restored ticket/draft.

Never silently accept a partially read code. Leg-count mismatch, missing market, invalid decimal odds or wrong event identity must remain visible.

## 2. Research a whole ticket

Before calling a ticket strong/weak or editing it based on quality:

1. `ticket.research.plan`
2. run the required Scout/browser/source work per leg;
3. `sports.match_snapshot` where supported;
4. `research.evidence.ingest` for gathered findings;
5. use a Skeptic pass when the plan requires it;
6. rank/edit only after evidence exists.

A large ticket is multiple research cases, not one opinion.

## 3. Search several bookmakers

Use `bookmaker.compare.plan` for the exact ticket/selections.

For each ready bookmaker:

- follow its current market-search playbook;
- match both event participants;
- open the exact market;
- match the exact line and period;
- read decimal odds;
- include `observed_at` at the time the price was actually read.

Return all results together to `bookmaker.compare.from_search`.

That tool is the normal answer to: `Which bookmaker has the best price?`

Important: the odds stored on an old source ticket are history/context, not automatically current. They participate in the current best-price comparison only when that bookmaker was freshly searched too.

## 4. Convert one ticket to another bookmaker

1. Start from the restored/normalized source ticket or source draft.
2. Run `bookmaker.search.plan` for the target bookmaker.
3. Search every target leg exactly.
4. Pass browser results with current `observed_at` to `bookmaker.convert.from_search`.
5. Conversion requires fresh prices by default.
6. Every leg must match event + sport + market type + metric + line + period + side/participant.
7. Different line/period is not an equivalent, even if its price is attractive.
8. If every leg matches, preserve the converted draft and its price observations.

Do not use a stale price to present a converted ticket as current. Recheck it.

## 5. Build a booking code

There are two build paths.

### Preferred rich browser builder

Use `bookmaker.browser_build.plan` when its profile is ready.

This is the preferred path for markets beyond the legacy script scope, including totals, handicaps, corners, cards, player props, set/map markets and other visible bookmaker markets.

Current V2 capability truth:

- SportyBet: rich public booking-code browser plan is verified.
- Bet9ja: rich public booking-number browser plan is verified.

Only these two bookmakers are active. Treat any other bookmaker as unsupported; do not
offer restore, search, conversion or build workflows for it.

When using a converted draft, pass `draft_id`; Sabi Boy can infer the recorded target bookmaker and will reject a conflicting target.

Follow the returned per-leg tasks. After every selection is added, visibly confirm:

- exact event;
- exact selection;
- exact line;
- exact period;
- current decimal price.

Use the bookmaker's booking-code/Book Bet action only. Do not enter stake or place/pay for the wager.

### Legacy command builder

Use `bookmaker.build.plan` / `bookmaker.build.execute` only if the adapter explicitly reports the sport/market/period as proven.

The old Bet9ja/SportyBet scripts are compatibility tools, not general rich-market builders. Never feed an unsupported total/handicap/prop into a winner-only legacy path.

## 6. Verify every newly built code

A builder returning a code is not the end of the workflow.

1. Reload the new booking code using the bookmaker restoration playbook.
2. Extract the restored slip again.
3. Call `bookmaker.build.verify` with the converted/expected draft.
4. Return the booking code only after structural verification succeeds.

Verification distinguishes:

- **correct structure + same price** — verified;
- **correct structure + changed price** — structurally verified, show the new price;
- **wrong event/market/line/period/selection** — not verified;
- **unexpected extra leg** — not verified.

A price movement is different from rebuilding the wrong ticket.

## 7. Price freshness

Browser/adapter market-search results should be timestamped at observation.

Default V2 conversion/comparison freshness window: 180 seconds unless a workflow deliberately specifies another value.

If a price is stale, missing a valid timestamp, or appears to be from the future because of a clock problem, re-read it instead of using it for conversion/building.

## 8. Lineage

Preserve the chain whenever possible:

`original code/screenshot/X/instruction → restored draft → researched/edited draft → converted draft → built code → verified-built draft`

Never silently overwrite the original ticket. The dashboard/history should eventually be able to tell the story of what changed and why.
