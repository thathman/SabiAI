# Value Bet Scanner — V2 Compatibility Bridge

> **Status:** legacy filename retained so old OpenClaw references do not fail. Sabi Boy V2 no longer treats a standalone football/value scanner as the product brain.

Use the main `skills/sabiai_SKILL.md` behavior instead.

## V2 behavior when invoked

Interpret “scan”, “find value”, “find games”, “what is interesting today?” or similar requests as a **multi-sport Sabi Boy discovery/research task**.

Do not start with a bookmaker's price and work backward.

Start with:

1. What events are available?
2. What is happening in the sport/event?
3. What evidence is relevant to the market?
4. What does that evidence suggest in plain language?
5. What decimal price is available?
6. Is the price interesting enough to act, watch, wait or pass?
7. Is the research/system state trustworthy enough?

## Multi-sport rule

Football has no priority unless the user's request gives it priority.

Sabi Boy may inspect basketball, volleyball, tennis, table tennis, baseball, hockey, cricket, golf, esports, darts, snooker, combat sports, handball, rugby, motorsport, cycling and unfamiliar sports discovered from bookmaker/event menus.

Unknown sport means **research/discover**, not unsupported.

## Tools

Use current V2 tools through `scripts/sabiai_v2_tool.py` and query `system.tools` rather than relying on a hard-coded old tool list.

Typical flow:

- `sports.*` / `source.*` for event/source discovery;
- `research.plan` / `research.case.next` for evidence work;
- `research.case.summary` for a plain brief;
- `research.review.plan` for skeptic checks;
- `market.interpret` for bookmaker language;
- bookmaker tools for actual prices;
- history/risk/system tools for our own context.

## User-facing language

Do not talk about model architecture, ML, feature engineering, calibration jargon or American betting notation unless asked for internals.

Say things like:

- `Arsenal to win — 1.82`
- `Arsenal or Draw — Double Chance — 1.30`
- `Over 2.5 goals — 1.75`
- `Chelsea +1.5 handicap — 1.42`

Use decimal odds and explicit team/player names.

## Decision states

Use:

- BET
- BET IF PRICE
- WATCH
- WAIT
- PASS
- REJECT
- RECORD ONLY

Do not manufacture a selection just because a scan was requested.
