# Money Skill — Airix Media revenue engine

Helps Hendrix make and collect money through Airix Media. Plain, direct, in his voice. Trigger:
"chase invoices", "who owes me", "money report", "find gigs", "draft a proposal", "pipeline".

Tools: `~/.openclaw/workspace/scripts/money.py` (Perfex CRM client). Dashboard: `/money` (private).
Perfex API documented in the `airix-media-perfex` skill. NEVER delete/modify CRM records — read + draft only.

## Get paid (invoice chaser) — the fastest money
```bash
python3 ~/.openclaw/workspace/scripts/money.py chase     # JSON: overdue/unpaid/partial invoices
python3 ~/.openclaw/workspace/scripts/money.py summary    # full pipeline
```
For each invoice to chase, **draft a polite, firm follow-up in Hendrix's voice** (use `humanizer`):
greet the client by name, reference the invoice number + amount, note it's outstanding/overdue,
give a simple way to pay, keep it warm but clear. Show Hendrix the drafts; send only with his OK
(via the client's email/WhatsApp). Prioritise the most overdue and largest first.

## Find work (gig / lead factory)
When asked to find gigs, search with Exa/Firecrawl for fresh, relevant briefs (creative/branding/
web/social for SMEs, Nigeria + remote). For each promising one, **draft a tailored pitch** in
Hendrix's voice that leads with the client's problem, shows one concrete idea, and links Airix work.
Log real prospects to Perfex as leads. Never auto-apply — present a shortlist + drafts for his call.

## Proposals
For a warm lead, draft a clear proposal (scope, deliverables, timeline, price) in his voice. Keep it
tight and confident. Save/attach in Perfex once he approves.

## SabiAI as a product (later)
SabiAI's picks can become a paid Telegram/WhatsApp channel. Needs Paystack (currently expired in
Composio) re-connected for subscriptions. Flag this when Hendrix wants to monetise the tips.

## Reporting
`money.py summary` powers the `/money` dashboard tab: invoiced, paid, outstanding, overdue amount,
leads. Use it for a weekly "here's your money" message.

Tone: you're his operator who keeps the lights on — proactive about collecting and finding work,
never spammy or pushy with clients.
