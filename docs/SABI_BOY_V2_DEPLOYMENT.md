# Sabi Boy V2 — Deployment / Upgrade Runbook

This runbook is for the eventual Dell/OpenClaw upgrade from SabiAI V1 to Sabi Boy V2.

**Do not use it to promote V2 before the release task board is complete.**

## Principles

1. V1 data is never modified during preparation.
2. V1 stays available while V2 is staged on a separate local port.
3. Every deployment starts with verified SQLite snapshots.
4. V1 → V2 migration is deterministic and repeatable.
5. Migration must reconcile before V2 starts.
6. Full application acceptance must pass before OpenClaw activation.
7. OpenClaw must prove it is using this exact V2 workspace and current-format Sabi Boy skills before external cutover.
8. The repository does not guess Cloudflare/external routing.
9. External cutover is verified against the actual routed `/health` URL.
10. Rollback state is recorded before cutover.

## Runtime layout

Default/historical paths are configurable through `~/.config/sabi-boy/sabi-boy.env`.

Important variables:

- `SABIAI_REPO_ROOT`
- `SABIAI_DATA_DIR`
- `SABIAI_LEGACY_DB`
- `SABIAI_V2_DB`
- `SABIAI_TIMEZONE`
- `SABIAI_OPENCLAW_AGENT_ID` — defaults to compatibility id `sabi-ai`
- `SABIAI_THESPORTSDB_KEY`
- `SABIAI_FOOTBALL_DATA_TOKEN` (optional)
- `SABIAI_PAID_SOURCES`

V2 dashboard service:

- unit: `sabi-boy-dashboard.service`
- local bind: `127.0.0.1:8091`
- app: `dashboard.v2_app:app`
- dashboard/API: read-only

Verified backup schedule:

- service: `sabi-boy-backup.service`
- timer: `sabi-boy-backup.timer`
- backup engine: verified SQLite backup/checksum/integrity tooling
- retention: conservative pruning of recognized Sabi Boy backup sets only

Legacy V1 dashboard is intentionally not reused as the V2 process.

Human-facing identity: **Sabi Boy**. The technical OpenClaw/AI Spine agent id remains `sabi-ai` unless a later deliberate compatibility migration changes it.

## Step 1 — Get the correct branch

The working tree must be clean before upgrade work begins.

```bash
git fetch --all --prune
git checkout v2
git pull --ff-only
```

Record:

```bash
git status --short
git rev-parse HEAD
git remote -v
```

Do not force-reset an unknown working tree. Preserve/report local changes first.

## Step 2 — Prepare the V2 runtime

```bash
bash scripts/sabi_v2_prepare_runtime.sh
```

This:

- requires branch `v2`;
- creates/updates `.venv`;
- installs `requirements-v2.txt`;
- installs the Playwright Chromium runtime unless `--no-browser` is supplied;
- creates the secret-free environment template if needed;
- initializes the V2 schema;
- registers the source catalog;
- renders the dashboard and verified-backup systemd user units to the actual checkout path;
- reloads user systemd.

It does **not**:

- migrate V1 history;
- stop V1;
- start V2;
- treat the backup timer as runtime-accepted merely because the unit is installed;
- change the OpenClaw agent;
- install OpenClaw scheduled jobs;
- change Cloudflare routing.

Review `~/.config/sabi-boy/sabi-boy.env` after first creation. Secrets/tokens stay outside Git.

## Step 3 — Stage V2

```bash
bash scripts/sabi_v2_stage.sh
```

The stage command performs the release-critical order:

1. verified backup of V1 and current V2 DB;
2. V1 → V2 deterministic migration;
3. migration reconciliation;
4. full release acceptance;
5. backup/restore acceptance;
6. start/restart `sabi-boy-dashboard.service`;
7. verify `http://127.0.0.1:8091/health`;
8. verify `/api/v2/overview`;
9. enable the V2 backup timer only after the required V2 acceptance gates succeed;
10. write commit-pinned staging state.

State/report locations:

- `data/release/staging-latest.json`
- `data/release/migration-latest.json`
- `data/release/acceptance-latest.json`
- `data/backups/sabi-boy/<timestamp>/manifest.json`

If a required gate fails, V2 is not started (or is stopped if the process check failed) and V1 is left unchanged.

## Step 4 — Inspect V2 locally

Before touching OpenClaw identity/jobs or external routing:

```bash
systemctl --user status sabi-boy-dashboard.service --no-pager
systemctl --user status sabi-boy-backup.timer --no-pager
curl -fsS http://127.0.0.1:8091/health
curl -fsS http://127.0.0.1:8091/api/v2/overview
```

Also inspect:

- Overview totals;
- Games/Picks history;
- Tickets and legs;
- bankroll;
- streaks;
- performance breakdowns;
- advanced ticket parent→child history;
- recorded bookmaker price movement/disagreement;
- migrated diary/blog posts;
- system/source/job state.

Compare key values to V1. Do not proceed when history or bankroll differs unexpectedly.

## Step 5 — Activate and verify OpenClaw

Current OpenClaw discovers workspace skills from directories containing `SKILL.md` with frontmatter. Sabi Boy V2 includes current-format packages such as:

- `skills/sabi-boy-core/SKILL.md`
- `skills/sabi-boy-bookmaker-workflows/SKILL.md`
- `skills/sabi-boy-research-scout/SKILL.md`
- `skills/sabi-boy-skeptic/SKILL.md`
- `skills/sabi-boy-ticket-engineer/SKILL.md`
- `skills/sabi-boy-records/SKILL.md`
- `skills/sabi-boy-blog/SKILL.md`

The historical flat `*_SKILL.md` files remain compatibility/reference material and are not the only runtime skill source.

Run:

```bash
bash scripts/sabi_v2_activate_openclaw.sh
```

The guarded activation command:

1. requires a green commit-pinned V2 staging state;
2. rechecks the live local V2 dashboard;
3. preserves the existing `sabi-ai` agent if it already points at this checkout;
4. creates the `sabi-ai` agent at this checkout if it is genuinely missing;
5. **refuses to silently retarget** an existing same-id agent that points somewhere else;
6. verifies the agent workspace through `openclaw agents list --json`;
7. verifies required Sabi Boy skills through the OpenClaw skills CLI;
8. verifies the final V2 gateway surface, including durable research cases, source learning, verified ticket variants, settlement profiles, bookmaker browser health, advanced history and Blog triggers;
9. applies the human-visible Sabi Boy identity from `IDENTITY.md` while retaining the machine id;
10. installs/updates the daily and weekly Sabi Boy reflection automations;
11. reruns OpenClaw acceptance and records it in staging state.

Reports include:

- `data/release/openclaw-agent-latest.json`
- `data/release/openclaw-pre-activation.json`
- `data/release/openclaw-identity-latest.json`
- `data/release/openclaw-activation-latest.json`

The reflection jobs are installed with OpenClaw's persistent automation scheduler and are pinned to `SABIAI_OPENCLAW_AGENT_ID`. They publish only when there is something meaningful to reflect on; routine job execution is not announced to chat.

Manual verification commands:

```bash
openclaw agents list --json
openclaw skills check --agent "${SABIAI_OPENCLAW_AGENT_ID:-sabi-ai}" --json
openclaw skills list --agent "${SABIAI_OPENCLAW_AGENT_ID:-sabi-ai}" --json
openclaw automations list --agent "${SABIAI_OPENCLAW_AGENT_ID:-sabi-ai}" --all --json
printf '%s\n' '{"tool":"system.tools","args":{}}' | .venv/bin/python scripts/sabiai_v2_tool.py
printf '%s\n' '{"tool":"system.readiness","args":{}}' | .venv/bin/python scripts/sabiai_v2_tool.py
```

Do not proceed to external cutover if OpenClaw activation is not green.

## Step 6 — Controlled functional acceptance

Before external routing changes, exercise the real Sabi Boy workflows from the OpenClaw agent, including representative multi-sport research and bookmaker/ticket work required by Phase 16.

At minimum validate:

- plain-language and decimal-odds output;
- unknown-sport discovery behavior;
- persistent research case create/attach/resume/summary;
- durable learned-source discover/verify/reuse behavior;
- form/H2H/injury/match snapshot research;
- Research Scout + Skeptic + Ticket Engineer worker flows;
- market settlement profiles for retirement/dead-heat/overtime-style cases;
- booking-code restoration where supported;
- fresh multi-book price comparison;
- verified ticket candidate/higher-odds variants;
- strict conversion with no line/period substitutions;
- SportyBet/Bet9ja rich booking-code browser plan in the controlled environment;
- reload and `bookmaker.build.verify` on at least one end-to-end rebuilt code;
- bookmaker browser-health observations after real tests;
- settlement duplicate/correction behavior;
- job success/failure/readiness behavior;
- `blog.triggers` plus reflection automation behavior;
- Blog create/publish/display path;
- dashboard desktop/mobile display against migrated data, including advanced History panels;
- backup timer and safe restore drill.

Do not mark the release gate complete from mocked/unit behavior alone.

## Step 7 — Inspect the real external routing

This repo intentionally does not assume whether the live endpoint is provided by:

- cloudflared config;
- a Cloudflare tunnel service;
- reverse proxy;
- another OpenClaw-managed route.

On the Dell, identify the current route to V1 and record its configuration before editing it.

Change only the Sabi dashboard target from V1's local endpoint to:

```text
http://127.0.0.1:8091
```

Do not change unrelated tunnel/routes.

Keep a copy/diff of the previous routing configuration for rollback.

## Step 8 — Verify and finalize external cutover

After changing routing, provide the actual routed health URL:

```bash
.venv/bin/python scripts/sabi_v2_finalize_cutover.py \
  --health-url 'https://YOUR-SABI-HOST/health'
```

The finalizer now requires:

- current checkout exactly matches the staged commit;
- green OpenClaw activation recorded in staging state;
- required skills verified;
- Sabi Boy reflection automations installed;
- local V2 health identifies Sabi Boy/read-only;
- external route identifies Sabi Boy/read-only.

Only after that verification may the legacy dashboard be stopped:

```bash
.venv/bin/python scripts/sabi_v2_finalize_cutover.py \
  --health-url 'https://YOUR-SABI-HOST/health' \
  --stop-v1
```

Do not stop V1 before external V2 verification.

## Rollback

First restore the external route to its recorded V1 target/configuration.

Then:

```bash
.venv/bin/python scripts/sabi_v2_rollback.py
```

This:

- stops `sabi-boy-dashboard.service`;
- restores the pre-stage V2 backup-timer posture;
- restarts `sabiai-dashboard.service` if it had been active before staging;
- records rollback state.

Normally V1 DB restoration is unnecessary because V1 is opened read-only during migration and not modified by staging.

If the V2 DB itself must be returned to its pre-staging snapshot:

```bash
.venv/bin/python scripts/sabi_v2_rollback.py --restore-v2-database
```

The backup manifest is checksum/integrity verified before restore.

OpenClaw identity/automation rollback should be handled from the recorded pre-cutover OpenClaw state when a release actually changes those runtime settings. Do not delete unrelated agents or automations during rollback.

## Acceptance runners

Application/repository acceptance:

```bash
.venv/bin/python scripts/sabi_v2_acceptance.py --migrate-v1
```

OpenClaw acceptance only:

```bash
.venv/bin/python scripts/sabi_v2_openclaw_acceptance.py \
  --report data/release/openclaw-manual-check.json
```

Application acceptance checks include:

- branch/commit;
- V2 DB initialization/integrity;
- V1 migration/reconciliation;
- full pytest suite;
- V2 gateway and readiness;
- V2 dashboard HTTP behavior;
- absence of mutation routes under `/api/v2`;
- backup/restore drill.

OpenClaw acceptance checks include:

- exact repo root and agent workspace;
- required current-format skill packages;
- required skill visibility to the selected agent;
- final required V2 tool surface;
- runtime readiness;
- optionally automation installation after all checks pass.

Any failed required gate produces a non-zero exit status.

## Promotion to `main`

Do not merge/promote `v2` merely because the service is running.

Promotion requires Phase 16 release gates in `docs/SABIAI_V2_TASKS.md`, including real Dell/OpenClaw acceptance, multi-sport checks and at least one real verified bookmaker conversion/rebuild.

Once V2 is accepted in production, `v2` can be promoted/merged to `main` according to the project's Forgejo-first release workflow.

For the installation/testing execution brief, use `docs/SABI_BOY_V2_WORK_HANDOFF.md`.

Only after the V2 acceptance/promotion state is genuinely ready should the final production OpenClaw/cutover instruction be issued.
