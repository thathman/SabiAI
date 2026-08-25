# Sabi Boy V2 — Deployment / Upgrade Runbook

This runbook is for the eventual Dell/OpenClaw upgrade from SabiAI V1 to Sabi Boy V2.

**Do not use it to promote V2 before the release task board is complete.**

## Principles

1. V1 data is never modified during preparation.
2. V1 stays available while V2 is staged on a separate local port.
3. Every deployment starts with verified SQLite snapshots.
4. V1 → V2 migration is deterministic and repeatable.
5. Migration must reconcile before V2 starts.
6. Full acceptance must pass before external routing changes.
7. The repository does not guess Cloudflare/OpenClaw routing.
8. External cutover is verified against the actual routed `/health` URL.
9. Rollback state is recorded before cutover.

## Runtime layout

Default/historical paths are configurable through `~/.config/sabi-boy/sabi-boy.env`.

Important variables:

- `SABIAI_REPO_ROOT`
- `SABIAI_DATA_DIR`
- `SABIAI_LEGACY_DB`
- `SABIAI_V2_DB`
- `SABIAI_TIMEZONE`
- `SABIAI_THESPORTSDB_KEY`
- `SABIAI_FOOTBALL_DATA_TOKEN` (optional)
- `SABIAI_PAID_SOURCES`

V2 dashboard service:

- unit: `sabi-boy-dashboard.service`
- local bind: `127.0.0.1:8091`
- app: `dashboard.v2_app:app`
- dashboard/API: read-only

Legacy V1 dashboard is intentionally not reused as the V2 process.

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
- renders the systemd user unit to the actual checkout path;
- reloads user systemd.

It does **not**:

- migrate V1 history;
- stop V1;
- start V2;
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
5. backup/restore drill;
6. start/restart `sabi-boy-dashboard.service`;
7. verify `http://127.0.0.1:8091/health`;
8. verify `/api/v2/overview`;
9. write staging state.

State/report locations:

- `data/release/staging-latest.json`
- `data/release/migration-latest.json`
- `data/release/acceptance-latest.json`
- `data/backups/sabi-boy/<timestamp>/manifest.json`

If a required gate fails, V2 is not started (or is stopped if the process check failed) and V1 is left unchanged.

## Step 4 — Inspect V2 locally

Before touching external routing:

```bash
systemctl --user status sabi-boy-dashboard.service --no-pager
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
- migrated diary/blog posts;
- system/source state.

Compare key values to V1. Do not proceed when history or bankroll differs unexpectedly.

## Step 5 — Validate OpenClaw

From the actual OpenClaw workspace/runtime, verify the V2 bridge:

```bash
printf '%s\n' '{"tool":"system.tools","args":{}}' | .venv/bin/python scripts/sabiai_v2_tool.py
printf '%s\n' '{"tool":"system.readiness","args":{}}' | .venv/bin/python scripts/sabiai_v2_tool.py
```

Required checks include:

- Sabi Boy identity/instructions are loaded;
- plain-language output;
- decimal odds only;
- sports registry and unknown-sport discovery;
- research/source tools;
- ticket normalization/editing;
- history/settlement/blog tools;
- bookmaker capability truth;
- no dashboard mutation surface.

Bookmaker browser builders need their own controlled-runtime acceptance before they are considered release-ready.

## Step 6 — Inspect the real external routing

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

## Step 7 — Verify and finalize external cutover

After changing routing, provide the actual routed health URL:

```bash
.venv/bin/python scripts/sabi_v2_finalize_cutover.py \
  --health-url 'https://YOUR-SABI-HOST/health'
```

The finalizer requires both local and external responses to identify:

- product: `Sabi Boy`
- dashboard: `v2`
- read-only: `true`
- health: OK

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
- restarts `sabiai-dashboard.service` if it had been active before staging;
- records rollback state.

Normally V1 DB restoration is unnecessary because V1 is opened read-only during migration and not modified by staging.

If the V2 DB itself must be returned to its pre-staging snapshot:

```bash
.venv/bin/python scripts/sabi_v2_rollback.py --restore-v2-database
```

The backup manifest is checksum/integrity verified before restore.

## Acceptance runner

The release gate runner can also be called directly:

```bash
.venv/bin/python scripts/sabi_v2_acceptance.py --migrate-v1
```

It checks:

- branch/commit;
- V2 DB initialization/integrity;
- V1 migration/reconciliation;
- full pytest suite;
- OpenClaw gateway and readiness;
- V2 dashboard HTTP behavior;
- absence of mutation routes under `/api/v2`;
- backup/restore drill.

Any failed gate produces a non-zero exit status.

## Promotion to `main`

Do not merge/promote `v2` merely because the service is running.

Promotion requires Phase 16 release gates in `docs/SABIAI_V2_TASKS.md`, including real Dell/OpenClaw acceptance and bookmaker/multi-sport checks.

Once V2 is accepted in production, `v2` can be promoted/merged to `main` according to the project's Forgejo-first release workflow.
