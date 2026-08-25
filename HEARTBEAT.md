# Sabi Boy V2 Heartbeat

Heartbeat is for **awareness, integrity and useful recovery**, not blind scanning. Exact schedules belong in cron/jobs.

Rotate through a small subset each heartbeat; do not run everything every time.

## Priority checks

1. **AI Spine / active work** — check for Sabi Boy tasks, handoffs or unresolved questions.
2. **System health** — when V2 is active, check `system.health`; notice database/schema/job/source problems.
3. **Data freshness** — flag stale critical sports/odds/research data when an active task depends on it.
4. **Settlement integrity** — notice pending items that should have settled, duplicate settlement risk or reconciliation drift.
5. **Bankroll integrity** — notice ledger/reconciliation problems; never invent a balance.
6. **Ticket watch** — if an active ticket is waiting on lineup, price or a specific event, revisit only when new information exists.
7. **Price watch** — re-check only explicit watched thresholds; do not repeatedly poll every market.
8. **Learning/memory** — save durable lessons, source discoveries and recurring failure modes; skip temporary noise.

## Operating-state behavior

- **READY:** normal research/analysis may continue.
- **DEGRADED:** continue only with explicit limitations and stronger verification.
- **OBSERVE ONLY:** research/watch may continue; do not push action recommendations.
- **ACTION LOCKED:** surface the integrity problem and prioritize recovery/reconciliation.

## Paid-source discipline

A heartbeat must **never spend a paid API call just because it fired**. Reuse cache/memory first and escalate only when a real active task justifies it.

## Notification discipline

Speak only when something materially changed, needs attention, or unlocks an active decision. Do not send routine “all good” chatter unless the runtime requires `HEARTBEAT_OK`.
