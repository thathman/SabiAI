# Money Skill — Sabi Boy V2 Compatibility Boundary

> This legacy filename previously contained unrelated Airix Media revenue/CRM behavior. That behavior does **not** belong inside the Sabi Boy sports-intelligence agent and must not be loaded as Sabi's money doctrine.

## Sabi Boy's money scope

Within this repository, “money”, “finance” or “bankroll” means **our Sabi Boy records only**:

- recorded bankroll;
- stakes/payouts/refunds/adjustments;
- betting profit/loss;
- bankroll history;
- ticket/pick financial history;
- reconciliation and settlement integrity.

Use the canonical V2 services/tools (`record.*`, `history.*`, `settlement.*`) and the read-only Finance dashboard view.

## Out of scope

Do not use this Sabi Boy skill to:

- chase Airix invoices;
- manage Perfex CRM;
- find business gigs;
- draft Airix proposals;
- modify client/business financial records;
- turn Sabi Boy into a general personal/business finance agent.

Those belong to the separate money/finance agent and its own workspace/skills.

## Cross-agent coordination

When Sabi Boy needs broader finance context, use the established AI Spine/finance-agent coordination path described in `AGENTS.md`. Share only the minimum Sabi bankroll/exposure context required for coordination.

Do not create a second finance database inside this skill.

## Dashboard

Sabi Boy's Finance page remains read-only and visualizes the canonical Sabi Boy ledger/history. It is not an Airix revenue dashboard.
