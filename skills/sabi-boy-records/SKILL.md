---
name: sabi-boy-records
description: Maintain Sabi Boy V2 bankroll, pick/ticket history, settlement, corrections, streaks, and performance records safely.
---

# Sabi Boy Records & Settlement

Use for our own recorded activity only. The dashboard/history is about **our** games, tickets, streaks, bankroll and performance; it is not a generic sports-stat source.

## Vocabulary

Use the canonical outcome vocabulary:

- Won
- Lost
- Draw
- Void
- Pending

Keep user-facing language simple.

## Writes

Use V2 `record.*` and `settlement.*` tools. Do not edit SQLite tables directly from a skill.

Settlement must be idempotent: repeating the same confirmed settlement should not create another payout or duplicate history.

An already-settled result may only change through an explicit correction with a reason and settlement audit trail.

## Tickets

Ticket result is derived from its legs according to the relevant settlement rules. Preserve ticket/leg identity and bookmaker context.

Use `market.settlement.profile` when the sport/market can depend on overtime, retirement, dead heat, forfeits or event format. If the profile requires bookmaker verification, do not assume two books settle it the same way.

## Bankroll

Use the ledger. Distinguish:

- deposits/withdrawals;
- stakes;
- payouts/refunds;
- adjustments;
- actual betting P/L.

Do not call a deposit profit.

If the ledger does not reconcile, respect `system.readiness`; action-oriented ticket building may be locked.

## History/learning

Useful breakdowns include:

- specific recorded picks and their event, market, price, rationale, confidence, bookmaker and outcome (`history.picks`);
- overall W/L/D/void/pending;
- bankroll and betting P/L over time;
- current/best/worst streaks;
- sport;
- competition;
- market;
- bookmaker;
- strategy;
- decimal-odds band;
- ticket size;
- combined-odds band;
- ticket source;
- ticket killers;
- original vs edited/conversion lineage.

Use the advanced read models when useful:

- `history.ticket_versions` — parent/child result comparison and odds changes;
- `history.bookmaker_prices` — recorded price movement by bookmaker/event/market;
- `history.price_disagreements` — latest recorded cross-book price gaps.

Historical price tools describe what Sabi Boy observed; they do not replace a fresh bookmaker search before building/converting a ticket.

These are records of what actually happened. Never backfill a result from memory when settlement evidence is uncertain.
