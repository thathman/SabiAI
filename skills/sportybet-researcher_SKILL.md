# SportyBet Researcher — V2 Compatibility Bridge

> **Status:** legacy filename retained for compatibility. The old football-first SportyBet research workflow is superseded by **Sabi Boy V2**.

Do not run the old standalone research doctrine from this file.

For current work use:

- `skills/sabiai_SKILL.md` — main Sabi Boy operating skill
- `skills/sabi-boy-research-scout_SKILL.md` — focused multi-sport research worker
- `skills/sabi-boy-skeptic_SKILL.md` — reviewer/challenge worker
- `skills/sabi-boy-ticket-engineer_SKILL.md` — ticket import/edit/convert/rebuild worker

## When this compatibility skill is invoked

Treat the request as a normal **Sabi Boy bookmaker + research** request.

### Research

1. Identify the exact sport, event and market.
2. Use `research.plan`, `research.case.next` and the free-first source system.
3. Do not assume football.
4. Research the exact market rather than generic form.
5. Store useful evidence and synthesize it with `research.case.summary`.
6. Trigger `research.review.plan` when the case needs a skeptic pass.

### SportyBet

SportyBet is a bookmaker/price source, not the source of truth about the sport.

Use bookmaker capabilities honestly:

- restore/read a booking code through a proven adapter or controlled OpenClaw browser flow;
- normalize the resulting ticket;
- use exact market/event mapping;
- use the target-bookmaker discovery/conversion path;
- run a builder only when that exact market is within the adapter's proven scope.

Do not silently substitute a different market, handicap, total or period.

## Data doctrine

Use cache/open/official/public sources before paid APIs. Do not bypass authentication, CAPTCHA, access controls or anti-bot protections. If a public source cannot be accessed normally, use another permitted source.

## Language

User-facing output must remain simple:

- explicit team/player names;
- home/away where useful;
- Win / Draw / Lose;
- `Arsenal or Draw — Double Chance`;
- `Arsenal +1.5 handicap`;
- `Over 2.5 goals`;
- decimal odds only;
- no unexplained American betting vocabulary;
- no model/ML jargon unless the user explicitly asks for technical internals.
