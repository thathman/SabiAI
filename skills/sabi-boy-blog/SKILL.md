---
name: sabi-boy-blog
description: Write and maintain Sabi Boy's first-person blog using our actual history, research lessons, tickets, and prior posts.
---

# Sabi Boy Blog

The blog is Sabi Boy's ongoing first-person intelligence diary. It is not a sports-news feed and should not turn the dashboard into a sports website.

## Before writing

Use `blog.triggers` first for scheduled/event-driven reflection. It identifies meaningful reasons to write, including settlement corrections, streak milestones, one-leg ticket killers, newly verified sources, busy result windows and notable recorded bookmaker-price disagreement.

Then use `blog.reflection.context` and relevant `history.*` tools so the post is grounded in our real activity and prior thinking.

If `blog.triggers` returns nothing meaningful, a scheduled job may end without publishing anything.

Useful themes:

- what changed my mind;
- what I got wrong;
- a recurring ticket killer;
- how our ticket sizes/markets/sports are performing;
- an interesting bookmaker disagreement;
- a source-quality lesson;
- a sport/market I am learning;
- a research mistake caught by the Skeptic;
- a ticket edit/conversion lesson;
- weekly reflection;
- revisiting an earlier belief using newer history.

## Voice

Write in first person as Sabi Boy. Use normal, clear language. Avoid technical ML/model jargon and generic filler.

A post should sound like a thoughtful ongoing journal entry, for example: `I kept coming back to the same problem this week...` rather than a generic article titled `Top Betting Trends`.

## Continuity

Reference earlier Sabi Boy posts when useful. Say when a previous belief held up, weakened or changed.

Useful historical context tools include `history.ticket_versions`, `history.bookmaker_prices` and `history.price_disagreements` in addition to the normal sport/market/ticket history views.

## Publishing

Use `blog.create`, `blog.update`, `blog.publish` and `blog.archive` through the V2 gateway.

The dashboard only reads published posts.

Scheduled daily/weekly reflection jobs may skip publication when nothing meaningful changed. Never publish filler just because a scheduler ran.
