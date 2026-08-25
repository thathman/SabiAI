# Sabi Boy V2 — Onboarding / Bootstrap Compatibility Skill

> Compatibility filename retained for old OpenClaw triggers such as `start sabiai` or `sabiai onboarding`.

## Existing V1 user / upgrade

**Do not run a new-user questionnaire when V1 history exists.**

The V2 upgrade path is:

1. preserve and back up V1;
2. migrate/reconcile V1 history and bankroll;
3. keep existing user preferences where still meaningful;
4. start Sabi Boy V2 in parallel;
5. ask only for genuinely missing runtime preferences.

Use `docs/SABI_BOY_V2_DEPLOYMENT.md` and the release tooling rather than `setup.py` from the old onboarding flow.

## New installation only

Keep onboarding short and conversational. Sabi Boy does not need the user to understand technical betting/statistics terminology.

Collect only what materially affects operation:

### 1. Display / locale

- preferred currency;
- timezone;
- preferred bookmaker(s), if any;
- any bookmaker the user never wants used.

### 2. Record keeping

- starting recorded bankroll if the user wants bankroll tracking;
- whether imported historical tickets should be included in performance charts;
- whether Sabi Boy should record only tickets actually used or also keep research-only drafts separately.

### 3. Ticket preferences

Examples:

- usual number of games per ticket;
- rough combined-odds targets the user commonly asks for;
- whether the user normally prefers singles, smaller tickets, larger accumulators or a mix;
- whether Sabi Boy may automatically prepare alternative versions or should wait to be asked.

These are preferences, not sports-coverage boundaries.

### 4. Sports

Ask about favourite/prioritised sports only if useful for ordering research. Never use the answer as an architectural allow-list.

Sabi Boy remains able to research a broad/open-ended sports universe, including unfamiliar sports discovered later.

### 5. Blog / proactive behavior

Ask whether the user wants:

- daily Sabi Boy thoughts;
- weekly reflection;
- posts only when something interesting happened;
- no automatic blog cadence.

## Language

Do not ask the user to choose technical methods or explain internal model names.

Use plain questions such as:

- “Which bookmakers do you normally use?”
- “Do you want me to track the money you actually put into tickets?”
- “When you ask me to make a ticket stronger, do you normally want fewer games, lower-risk markets, or both?”

## Persistence

V2 preferences must ultimately live in the canonical V2 settings/config path, not a separate hidden JSON file created by this skill.

Until the dedicated preferences service is implemented, preserve answers in OpenClaw memory/config notes and do **not** invent a new permanent store.

## Completion

A migrated user is onboarded when:

- V1 history/bankroll reconcile;
- Sabi Boy runtime/tooling is healthy;
- required environment preferences are known;
- no old questionnaire has overwritten existing history/preferences.

A new user is onboarded when the minimum preferences above are known and V2 storage is initialized.
