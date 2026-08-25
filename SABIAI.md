# SABIAI.md — Compatibility Pointer

The human-facing product/persona is now **Sabi Boy**.

This filename is retained temporarily because older prompts, agents, scripts or memory may still reference `SABIAI.md`.

## Read this instead

For the current V2 product/system definition:

- `SABI_BOY.md` — canonical system reference
- `IDENTITY.md` — canonical identity/naming policy
- `SOUL.md` — behavior, reasoning and product philosophy
- `OPERATING_MANUAL.md` — decision/risk/system discipline
- `AGENTS.md` — workspace, memory and coordination rules
- `skills/sabiai_SKILL.md` — OpenClaw orchestration skill (filename retained for compatibility)
- `docs/SABIAI_V2_TASKS.md` — actual implementation truth

## Legacy V1 reference

The former contents of this file were preserved at:

`docs/SABIAI_V1_REFERENCE.md`

Use that document only for V1 migration, reconciliation, rollback and historical behavior.

## Naming policy

Use **Sabi Boy** in human-facing replies, documentation labels and future dashboard copy.

Keep these technical identifiers unchanged until a deliberate compatibility migration is performed:

- repository name `SabiAI`;
- Python package `sabiai`;
- machine/AI Spine agent ID `sabi-ai`;
- `SABIAI_*` environment variables;
- existing database/service/script names;
- gateway/tool identifiers already depended on by OpenClaw.

Do not perform a blind string-replacement rename across the codebase.
