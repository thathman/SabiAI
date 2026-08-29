# Sabi Boy V2 — Deployment / Upgrade Runbook

This runbook records the Dell/OpenClaw upgrade from SabiAI V1 to Sabi Boy V2 and remains the rollback/reference procedure for the active V2.5.0 release.

**Current production:** Sabi Boy v2.5.0 at `7acac8810bccb8773c20bb32be3f18bd833d6b3b`, served on `127.0.0.1:8090` and verified through the public health route. The release task board is complete; use the documented rollback path for any reversal.

## Principles

1. V1 data is never modified during preparation.
2. V1 stays available while V2 is staged on a separate local port; after green acceptance, this Dell's approved endpoint removes the active V1 service/checkouts and retains private recovery archives.
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
- `SABIAI_OPENCLAW_AGENT_ID` — defaults to the existing Dell agent id `prediction`
- `SABIAI_THESPORTSDB_KEY`
- `SABIAI_FOOTBALL_DATA_TOKEN` (optional)
- `SABIAI_PAID_SOURCES`
- `SABIAI_DASHBOARD_ALLOWED_ORIGINS`
- `SABIAI_VAPID_PUBLIC_KEY`
- `SABIAI_VAPID_PRIVATE_KEY_FILE` — mode-600 key outside the repository
- `SABIAI_VAPID_SUBJECT`
- `SABIAI_RESEARCH_API_BASE_URL` — direct OpenAI-compatible research endpoint
- `SABIAI_RESEARCH_MODEL` — direct daily research model (default `qwen3.8-max-preview`)
- `SABIAI_RESEARCH_API_KEY` — optional dedicated key; the Dell may use the private `ALIYUN_TOKEN_PLAN_COMPATIBLE_KEY`
- `SABIAI_RESEARCH_SPORTS` — comma-separated daily fixture sports
- `SABIAI_RESEARCH_FALLBACK_API_BASE_URL`, `SABIAI_RESEARCH_FALLBACK_API_KEY`, `SABIAI_RESEARCH_FALLBACK_MODEL` — optional direct fallback; when omitted, V2 uses `qwen3.6-flash` on the same Alibaba token-plan endpoint/key for transient primary-model failures

V2 dashboard service:

- unit: `sabi-boy-dashboard.service`
- local bind: `127.0.0.1:8091`
- app: `dashboard.v2_app:app`
- sports/history dashboard/API: read-only; isolated push subscribe/unsubscribe is the only browser-write boundary

Automatic result settlement:

- service: `sabi-boy-settlement.service`
- timer: `sabi-boy-settlement.timer`
- interval: ten minutes, persistent across downtime
- scope: audited/idempotent score-derived outcomes only; no inferred payouts or unsupported props

Local source/readiness health:

- service: `sabi-boy-health.service`
- timer: `sabi-boy-health.timer`
- interval: thirty minutes, persistent across downtime
- scope: reads V2's local fetch log, readiness report and background-job state; it makes no provider or language-model calls
- material changes send Web Push when a subscription is available

Direct daily research and picks:

- service: `sabi-boy-research.service`
- timer: `sabi-boy-research.timer`
- schedule: 08:00 `Africa/Lagos`, persistent across downtime
- scope: compact direct source collection plus a direct Alibaba-compatible model call; no OpenClaw agent, workspace, memory or tool schemas are loaded
- output: `data/reports/daily-picks-latest.json` and a Web Push notification; recommendations are never written as placed wagers
- context: successful scans are persisted in `daily_research_runs`; Sabi Boy can read them through `system.daily_research`, `research.scan.latest`, `research.scan.history` and `research.scan.context`. `ticket.research.plan` includes the recent scan context, while `history.picks` reads canonical recorded picks for pick-specific questions. System-generated selections and qualifying strategy tickets are internal records; fresh prices and exact settlement rules must still be rechecked before any bookmaker ticket work.

Notification history:

- every system push delivery is recorded in `notification_history` with its title, message, tag, destination path and aggregate delivery counts;
- the read-only `GET /api/v2/notifications` endpoint and dashboard Notifications page show delivery status without exposing browser endpoints, p256dh keys or auth secrets;
- notification history is observability only; it does not change the subscription toggle or send additional messages.

Verified backup schedule:

- service: `sabi-boy-backup.service`
- timer: `sabi-boy-backup.timer`
- backup engine: verified SQLite backup/checksum/integrity tooling
- retention: conservative pruning of recognized Sabi Boy backup sets only

Legacy V1 dashboard is intentionally not reused as the V2 process.

Human-facing identity: **Sabi Boy**. The technical OpenClaw/AI Spine agent id remains `prediction`.

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
- generates/reuses a mode-600 VAPID private key outside the repository;
- initializes the V2 schema;
- registers the source catalog;
- renders the dashboard, verified-backup, automatic-settlement and local-health systemd user units to the actual checkout path;
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
10. enable the automatic result-settlement heartbeat;
11. enable the local source/readiness health timer;
12. enable the direct daily research timer;
13. write commit-pinned staging state.

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
systemctl --user status sabi-boy-settlement.timer --no-pager
systemctl --user status sabi-boy-health.timer --no-pager
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
3. preserves and updates the existing `prediction` agent when it points at this checkout;
4. refuses to substitute a new agent identity for `prediction`;
5. **refuses to silently retarget** an existing same-id agent that points somewhere else;
6. verifies the agent workspace through `openclaw agents list --json`;
7. verifies required Sabi Boy skills through the OpenClaw skills CLI;
8. verifies the final V2 gateway surface, including durable research cases, source learning, verified ticket variants, settlement profiles, bookmaker browser health, advanced history and Blog triggers;
9. applies the human-visible Sabi Boy identity from `IDENTITY.md` while retaining the machine id;
10. installs/updates the daily and weekly Sabi Boy reflection cron jobs;
11. reruns OpenClaw acceptance and records it in staging state.

Reports include:

- `data/release/openclaw-agent-latest.json`
- `data/release/openclaw-pre-activation.json`
- `data/release/openclaw-identity-latest.json`
- `data/release/openclaw-activation-latest.json`

The daily pick/research wake is owned by the local `sabi-boy-research.timer` at 08:00 `Africa/Lagos`. It collects a compact fixture/price packet and calls the configured direct model without loading the `prediction` agent, its workspace, memory or tool schemas. The report is written locally and sent by Web Push; no wager or placed-pick record is created. OpenClaw's persistent cron scheduler is retained only for the quiet daily reflection at 22:30 and weekly reflection Sunday at 20:00, both pinned to `SABIAI_OPENCLAW_AGENT_ID`. Source/readiness monitoring is a separate local `sabi-boy-health.timer` and does not wake the model or consume model tokens. User-facing OpenClaw announcements use the explicit `SABIAI_OPENCLAW_DELIVERY_CHANNEL`, `SABIAI_OPENCLAW_DELIVERY_TO` and `SABIAI_OPENCLAW_DELIVERY_ACCOUNT` route; relying on `last` is unsafe when multiple channels are configured. The systemd `sabi-boy-settlement.timer` remains the ten-minute result heartbeat and sends Web Push only when a settlement changes. Reflection jobs publish only when there is something meaningful to reflect on; routine job execution is not announced to chat.

Manual verification commands:

```bash
openclaw agents list --json
openclaw skills check --agent "${SABIAI_OPENCLAW_AGENT_ID:-prediction}" --json
openclaw skills list --agent "${SABIAI_OPENCLAW_AGENT_ID:-prediction}" --json
openclaw cron list --all --json
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
- PWA installation/offline shell, drawer X/backdrop close behavior and opt-in push on a real HTTPS device;
- automatic result heartbeat, audit idempotence, unsupported-market safety and one real push delivery;
- backup timer and safe restore drill.

Do not mark the release gate complete from mocked/unit behavior alone.

## Step 7 — Inspect the real external routing

This repo intentionally does not assume whether the live endpoint is provided by:

- cloudflared config;
- a Cloudflare tunnel service;
- reverse proxy;
- another OpenClaw-managed route.

On the Dell, identify the current route to V1 and record its configuration before any local service replacement.

For the approved Prediction replacement, the existing Cloudflare route already targets:

```text
http://127.0.0.1:8090
```

Do not edit that route. Stop/disable the legacy dashboard only after the staged V2 checks pass, move `sabi-boy-dashboard.service` to the same `127.0.0.1:8090` target, then verify the routed health response identifies Sabi Boy V2. Do not change unrelated tunnel/routes.

## Step 8 — Verify and finalize external cutover

After the local service replacement, provide the actual routed health URL:

```bash
.venv/bin/python scripts/sabi_v2_finalize_cutover.py \
  --health-url 'https://YOUR-SABI-HOST/health'
```

The finalizer now requires:

- current checkout exactly matches the staged commit;
- green OpenClaw activation recorded in staging state;
- required skills verified;
- Sabi Boy reflection cron jobs installed;
- local V2 health identifies Sabi Boy/read-only;
- external route identifies Sabi Boy/read-only.

When an external route must actually be changed in another environment, only after that verification may the legacy dashboard be stopped:

```bash
.venv/bin/python scripts/sabi_v2_finalize_cutover.py \
  --health-url 'https://YOUR-SABI-HOST/health' \
  --stop-v1
```

For this approved same-port replacement, first verify V2 on the separate staging port, then stop V1, start V2 on port 8090, and immediately verify both local and routed health. The verified private V1 archives are the recovery boundary.

## Rollback

Before legacy cleanup, restore the external route to its recorded V1 target/configuration when it was changed.

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

After the approved active-V1 cleanup, rollback requires restoring the verified private V1 workspace/repository/service archive; there is intentionally no dormant active V1 checkout to restart. OpenClaw identity/cron rollback should be handled from the recorded pre-cutover OpenClaw state when a release actually changes those runtime settings. Do not delete unrelated agents or cron jobs during rollback.

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

V2.5.0 was accepted in production at `7acac8810bccb8773c20bb32be3f18bd833d6b3b`. The corresponding `v2.5.0` tag and GitHub `main` synchronization are performed only from this accepted release state, without force-pushing or changing external routing.

For the installation/testing execution brief, use `docs/SABI_BOY_V2_WORK_HANDOFF.md`.

The final production OpenClaw/cutover instruction has been completed and is recorded in `data/release/staging-latest.json` on the Dell. Keep the V2.4 checkout and verified migration archives private for rollback; do not delete them as part of ordinary operation.
