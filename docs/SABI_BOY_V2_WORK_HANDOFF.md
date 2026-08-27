# Sabi Boy V2 — ChatGPT Work Installation & Testing Handoff

Use this document as the execution brief when switching to ChatGPT Work.

**Repository:** `thathman/SabiAI`  
**Branch:** `v2`  
**Product:** Sabi Boy  
**OpenClaw agent ID:** `prediction`
**Phase:** Installation + controlled runtime acceptance  
**Do not merge `v2` to `main` during this phase unless every applicable Phase 16 gate is green and the release step is explicitly included.**

## Mission

Install the completed Sabi Boy V2 candidate on the Dell, preserve and verify V1 data while migration is tested, run the full test suite, rehearse and verify the real V1 → V2 migration, activate the existing `prediction` OpenClaw agent as human-facing Sabi Boy, exercise the real multi-sport/Ticket Workshop/bookmaker workflows, verify the read-only dashboard and operational safeguards, fix any defects found on `v2`, and leave a complete evidence-backed acceptance report. The approved endpoint for this Dell is an in-place replacement: no active V1 service or checkout remains after V2 is verified, while private recovery archives are retained.

This is not a redesign task. Treat these as binding:

- `docs/SABIAI_V2_TASKS.md`
- `docs/SABI_BOY_V2_RELEASE_CANDIDATE.md`
- `docs/SABI_BOY_V2_DEPLOYMENT.md`
- `SABI_BOY.md`
- `IDENTITY.md`
- `SOUL.md`
- `OPERATING_MANUAL.md`
- `AGENTS.md`
- `V2.md`
- current-format `skills/sabi-boy-*/SKILL.md`

Do not revive V1 architecture simply because it is already installed.

## Non-negotiable safety / release rules

1. **Preserve V1 data during validation.** Do not modify or delete the V1 DB during preparation/migration rehearsal. After all required replacement checks pass, remove the active V1 service/checkouts but retain verified private recovery archives.
2. **No destructive Git recovery.** Never force-reset or discard unknown local changes. Inspect and preserve them.
3. **No GitHub Actions.** Tests run locally on the Dell.
4. **Forgejo/local-first development discipline.** Any fixes discovered during testing stay on `v2`, are tested locally, and follow the project's local/Forgejo-first workflow before GitHub release promotion.
5. **No external cutover at the beginning.** V2 runs on a separate loopback port first. The approved final replacement moves V2 to V1's existing `127.0.0.1:8090` target without editing Cloudflare routing.
6. **No wager placement or spending.** Booking-code creation/rebuild tests may prepare reusable codes only. Do not press a final wager/place-bet action and do not spend account funds.
7. **No access-control bypass.** Do not evade CAPTCHA, authentication, regional restrictions or anti-bot controls.
8. **Do not fake bookmaker support.** The active V2 runtime supports SportyBet and Bet9ja only; removed bookmaker targets must remain absent from capability, restore, search and build surfaces.
9. **Do not guess bookmaker settlement policy.** Use current rule pages/browser evidence where `market.settlement.profile` says verification is required.
10. **Dashboard remains read-only and about our data only.** Do not add general fixtures/scores/news/sports-site functionality during acceptance.
11. **Do not weaken release gates to make them pass.** A red gate is a defect or environment finding to investigate.
12. **Do not merge to `main` merely because V2 starts.** Phase 16 is the authority.

---

# Stage A — Establish and record the starting state

Connect to the Dell using the user's normal access path and identify the existing SabiAI/OpenClaw checkout. Do not assume the path from documentation is still exact.

Record, without exposing secret values:

```bash
pwd
date -Is
hostname
whoami

git status --short
git branch --show-current
git rev-parse HEAD
git remote -v

systemctl --user is-active sabiai-dashboard.service || true
systemctl --user is-active sabi-boy-dashboard.service || true
systemctl --user is-enabled sabi-boy-backup.timer || true
systemctl --user list-timers --all | grep -Ei 'sabi|backup' || true

openclaw agents list --json || true
openclaw cron list --all --json || true
```

Also identify and record:

- current V1 local port/process;
- V1 DB path;
- current external/Cloudflare route to V1;
- current OpenClaw `prediction` workspace path;
- AI Spine integration path/state;
- environment/config file locations and permissions;
- required environment variable **names** only, not token/secret values.

Save this pre-state in the testing notes/release evidence so rollback is reconstructable.

If the Git working tree contains local changes, stop before pulling and determine what they are. Preserve them in a safe branch/stash/commit as appropriate; do not destroy them.

---

# Stage B — Sync the V2 candidate safely

Ensure the repository is on the development candidate branch:

```bash
git fetch --all --prune
git checkout v2
git pull --ff-only

git status --short
git rev-parse HEAD
```

Record the exact candidate commit SHA. All later staging/acceptance evidence must refer to the same commit unless a tested fix is made during this Work session.

Read the four release documents before running installation commands:

```bash
sed -n '1,260p' docs/SABIAI_V2_TASKS.md
sed -n '1,260p' docs/SABI_BOY_V2_RELEASE_CANDIDATE.md
sed -n '1,360p' docs/SABI_BOY_V2_DEPLOYMENT.md
sed -n '1,360p' docs/SABI_BOY_V2_WORK_HANDOFF.md
```

---

# Stage C — Prepare the runtime, but do not migrate/cut over yet

Run:

```bash
bash scripts/sabi_v2_prepare_runtime.sh
```

This should prepare `.venv`, dependencies, browser runtime, V2 DB/schema, source catalog, environment file, and rendered user-systemd units without stopping V1 or changing external routing.

Immediately inspect:

```bash
ls -la .venv/bin/python
ls -l ~/.config/sabi-boy/sabi-boy.env
ls -l ~/.config/systemd/user/sabi-boy-dashboard.service
ls -l ~/.config/systemd/user/sabi-boy-backup.service
ls -l ~/.config/systemd/user/sabi-boy-backup.timer

systemctl --user cat sabi-boy-dashboard.service
systemctl --user cat sabi-boy-backup.service
systemctl --user cat sabi-boy-backup.timer
```

Requirements:

- env file should be private (`600` or equivalently restrictive);
- secrets must not appear in Git-tracked files;
- dashboard should bind locally to `127.0.0.1:8091`;
- preparation must not stop V1;
- backup timer should be installed but not prematurely treated as production-proven.

Review `~/.config/sabi-boy/sabi-boy.env` for correct **paths/settings**. Do not print secret values into chat/logs.

---

# Stage D — Run the full repository test suite before staging

Run the exact current suite from the prepared V2 environment:

```bash
.venv/bin/python -m pytest -q
```

If pytest is unavailable despite the declared requirements, diagnose the dependency setup; do not skip the full suite.

Also run a compile/import sanity pass:

```bash
.venv/bin/python -m compileall -q sabiai dashboard scripts
.venv/bin/python - <<'PY'
from sabiai.openclaw.gateway import SabiToolGateway
app = SabiToolGateway()
print(app.list_tools({})['count'])
PY
```

### If any test/import fails

Treat it as a development defect, not an acceptance exception:

1. keep the active installation untouched while reproducing the failure;
2. reproduce the failing test narrowly;
3. fix only the underlying issue on `v2`;
4. add or strengthen a regression test;
5. rerun the focused test;
6. rerun the complete suite;
7. record the fix/commit/evidence;
8. follow the local/Forgejo-first repository workflow for the fix.

Do not proceed to migration staging while the full suite is red.

---

# Stage E — Verify backup tooling before touching real history

Confirm the configured V1 and V2 DB paths from the environment without exposing unrelated secrets.

Create a verified snapshot:

```bash
.venv/bin/python scripts/sabi_v2_backup.py create
```

Inspect the returned manifest path and verify it:

```bash
.venv/bin/python scripts/sabi_v2_backup.py verify --manifest 'PATH_FROM_CREATE_OUTPUT'
```

If the CLI uses a slightly different verified subcommand/argument shape in the current checkout, inspect `--help` and use the implemented equivalent rather than inventing a command:

```bash
.venv/bin/python scripts/sabi_v2_backup.py --help
```

Record:

- backup manifest path;
- SHA/checksum evidence;
- SQLite integrity result;
- source DB paths;
- timestamp.

A failed backup/integrity verification blocks migration.

---

# Stage F — Rehearse V2 on a separate port before replacement

Run the guarded staging command:

```bash
bash scripts/sabi_v2_stage.sh
```

Expected behavior:

1. create verified pre-migration DB backups;
2. migrate V1 → V2 deterministically;
3. require reconciliation;
4. run full release acceptance (including the full pytest suite again);
5. exercise backup/restore acceptance;
6. start V2 on the configured separate loopback port while leaving V1 available during rehearsal;
7. verify V2 `/health` and `/api/v2/overview`;
8. enable the V2 verified-backup timer only after acceptance;
9. write commit-pinned staging state.

Inspect all generated evidence:

```bash
cat data/release/migration-latest.json
cat data/release/acceptance-latest.json
cat data/release/staging-latest.json

systemctl --user status sabi-boy-dashboard.service --no-pager
systemctl --user status sabi-boy-backup.timer --no-pager
curl -fsS http://127.0.0.1:8091/health
curl -fsS http://127.0.0.1:8091/api/v2/overview
```

Do not continue if the staged commit differs from the current checkout or any required acceptance section is red.

---

# Stage G — Reconcile real V1 history carefully

Use the migration report plus direct read-only comparisons to verify the actual historical data.

At minimum reconcile:

- total picks/bets;
- won/lost/draw/void/pending totals;
- ticket totals and ticket legs;
- bankroll opening/current balance;
- ledger stake/payout/refund totals;
- strategies including Kelly/Compound/Long Shot/Live and any legacy strategy labels;
- legacy accumulators/continuous-chain data where present;
- diary → Sabi Boy Blog migration;
- records preserved in `legacy_archive` because they had no direct canonical V2 destination.

Open the V2 dashboard locally and compare key numbers to the V1 interface/database.

Any unexplained missing row, duplicated historical row, bankroll difference or incorrect outcome is a release blocker. Fix migration logic on `v2`, add a regression fixture/test for the exact case, restore/recreate the V2 rehearsal DB as appropriate, and rerun migration/acceptance.

Do not edit the migrated database manually just to make counts match.

---

# Stage H — Verify the local read-only dashboard before OpenClaw activation

Check these local routes:

```bash
curl -fsS http://127.0.0.1:8091/health
curl -fsS http://127.0.0.1:8091/api/v2/overview
curl -fsS http://127.0.0.1:8091/api/v2/tickets/version-outcomes
curl -fsS http://127.0.0.1:8091/api/v2/bookmakers/price-history
curl -fsS http://127.0.0.1:8091/api/v2/bookmakers/price-disagreements
```

Confirm `/health` reports Sabi Boy and `read_only: true`.

Verify the browser UI on desktop at the local V2 endpoint/reverse-proxy preview:

- Overview;
- Games / Picks;
- Tickets + ticket details;
- Performance;
- Finance;
- Strategies;
- History;
- Sabi Boy Blog;
- System.

Specifically verify the History page enhancement:

- parent → child ticket-version comparison metrics/table;
- historical bookmaker price movement;
- recorded cross-book price disagreement.

These must describe our stored activity only.

Confirm no dashboard browser flow can mutate records, request a write key, expose the old PIN flow, or place/build tickets.

---

# Stage I — Activate and verify Sabi Boy in OpenClaw

Only after staging/data/dashboard checks are green, run:

```bash
bash scripts/sabi_v2_activate_openclaw.sh
```

Then inspect:

```bash
cat data/release/openclaw-agent-latest.json
cat data/release/openclaw-pre-activation.json
cat data/release/openclaw-identity-latest.json
cat data/release/openclaw-activation-latest.json

openclaw agents list --json
openclaw skills check --agent "${SABIAI_OPENCLAW_AGENT_ID:-prediction}" --json
openclaw skills list --agent "${SABIAI_OPENCLAW_AGENT_ID:-prediction}" --json
openclaw cron list --all --json
```

Run the final OpenClaw verifier directly too:

```bash
.venv/bin/python scripts/sabi_v2_openclaw_acceptance.py \
  --report data/release/openclaw-manual-check.json
```

Acceptance must prove:

- exact existing `prediction` agent is used;
- its workspace is this exact V2 checkout;
- all seven current-format Sabi Boy skills are visible;
- the final V2 tool surface is present, including persistent research cases, learned sources, verified ticket variants, settlement profiles, bookmaker browser health, advanced history and Blog triggers;
- runtime readiness is not ACTION LOCKED.

If the existing `prediction` agent points somewhere else, do not silently repoint it before its current state is recorded and the V2 workspace has passed controlled acceptance.

---

# Stage J — OpenClaw agent/subagent behavior acceptance

From the actual `prediction` agent, verify the human-facing identity is Sabi Boy and the language contract holds:

- decimal odds only;
- explicit named teams/players;
- Win/Lose/Draw and plain market labels;
- no unnecessary model/ML jargon;
- no American moneyline-style user language;
- unfamiliar sports trigger learning/research rather than `unsupported sport`;
- dashboard is described as our read-only record, not as a sports portal.

Exercise the Research Scout, Skeptic and Ticket Engineer worker flows. Confirm results return to the main Sabi Boy agent and do not create competing permanent personalities.

Verify AI Spine/shared-memory/message-bus compatibility after the V2 agent/workspace activation. Preserve the `prediction` machine identity expected by existing integrations.

---

# Stage K — Persistent research-case acceptance

Create a real research case through Sabi Boy or the gateway for a representative event/market.

Expected sequence:

1. `research.case.create`
2. gather/ingest evidence with `case_id`;
3. `research.case.attach` if needed;
4. `research.case.summary`;
5. end the interaction/session;
6. resume later/from another worker/session with `research.case.get` / summary;
7. confirm evidence, unresolved questions and status were preserved.

Use a market-specific example, not only generic team form.

Confirm the Skeptic can review the durable case and sees unresolved/conflicting evidence rather than only the last message.

---

# Stage L — Learned-source acceptance

Use a sport/competition where the built-in direct sources are insufficient.

Expected flow:

1. `source.discovery.plan`
2. OpenClaw Search/Browser discovers an official/public source normally;
3. `source.discovery.save` stores the candidate;
4. inspect it before trust;
5. `source.discovery.verify` marks a valid source verified, or rejected if unsuitable;
6. `source.discovery.check` records a later success/failure;
7. a later research session sees the verified source in the learned source catalog/plan and reuses it before rediscovering from scratch.

Do not mark a source verified merely because a URL loads. Verify that it actually covers the stated sport/capability and is usable under normal access rules.

---

# Stage M — Representative multi-sport research acceptance

Test at least:

- football;
- basketball;
- volleyball;
- tennis or another racquet sport;
- esports;
- golf or another field/race sport;
- one less-common sport/competition that requires source discovery.

For each, verify Sabi Boy adapts the research to the requested market instead of applying one football checklist everywhere.

Examples of checks:

- football goals/corners/cards;
- basketball points/rebounds/quarters;
- volleyball match/set handicap;
- tennis surface/form/retirement context;
- esports roster/map/format context;
- golf outright/Top-N/make-cut plus weather/withdrawal/course context.

Do not require equal source depth across every sport. Require truthful coverage status, source freshness/reliability, and sensible fallback behavior.

---

# Stage N — Settlement-rule live verification

Exercise `market.settlement.profile` for at least:

1. tennis/racquet retirement/withdrawal;
2. golf/field dead-heat/cut treatment;
3. basketball/hockey/baseball or another sport where overtime/extra periods can matter.

When the profile says bookmaker verification is required, use the current accessible bookmaker rule pages/browser evidence to verify the relevant topics before treating prices as equivalent.

Record the rule page/source and date checked.

Do not hard-code an inferred bookmaker policy during testing unless it is verified and the implementation genuinely needs a durable mapping; if code is changed, add a regression test and identify the policy source/date in documentation.

---

# Stage O — Ticket intake and workshop acceptance

Exercise all practical input paths:

- copied/plain text;
- structured instruction;
- existing `draft_id`;
- screenshot through OpenClaw vision;
- X post/link through normal OpenClaw access;
- restored bookmaker booking code where supported.

Verify:

- exact event/selection/odds extraction;
- ambiguous input is not silently guessed;
- split/trim/remove/keep/replace/change-market operations;
- locked-leg protection;
- strongest-N only uses actual supplied research ranking;
- lower-risk suggestions require current target-book alternatives before applying;
- `ticket.candidates.compare` clearly compares candidate versions;
- `ticket.higher_odds.from_verified_offers` refuses stale/unverified replacements and ties every replacement to an exact leg;
- lineage remains intact through every edit.

---

# Stage P — Real bookmaker browser acceptance

Use normal public/access-permitted browser flows. Do not place a wager.

## SportyBet

Verify:

- booking-code restoration;
- exact market search;
- fresh decimal-price capture;
- rich ticket build plan;
- creation of a reusable booking code if the current public flow permits;
- reload that code;
- `bookmaker.build.verify` confirms event/market/line/period structure.

## Bet9ja

Perform the same restore/search/build/reload/verify sequence where available.

After each real browser exercise, check:

```text
bookmaker.browser_health
```

and confirm the tool distinguishes configured capability from recently exercised success/failure.

---

# Stage Q — Fresh multi-book price comparison

For the same exact event/selection, collect fresh observations from multiple accessible books.

Verify:

- observed timestamps are present;
- stale observations are rejected;
- wrong bookmaker rows are rejected;
- wrong market/line/period cannot win the comparison;
- historical source-ticket odds are not treated as fresh merely because they are higher;
- best current compatible decimal price is correctly identified;
- `history.bookmaker_prices` / dashboard History later show the recorded observations as **historical observations**, not as current prices.

---

# Stage R — End-to-end conversion/rebuild acceptance

Complete at least one real end-to-end pair using accessible books, preferably SportyBet ↔ Bet9ja:

```text
source booking code
→ restore
→ canonical draft
→ research/edit if appropriate
→ target exact-market search
→ fresh target prices
→ strict conversion
→ converted draft
→ browser build
→ generated target code
→ reload generated code
→ bookmaker.build.verify
→ verified-built child draft
```

Acceptance requires:

- no silent event substitution;
- no silent line/period substitution;
- current target prices used;
- price changes during build are reported separately from structural mismatches;
- exact lineage retained;
- generated code restores to the intended selections.

Do not place the resulting wager.

---

# Stage S — Settlement / history write acceptance

On controlled test records, verify:

- Won/Lost/Draw/Void/Pending vocabulary;
- duplicate settlement is idempotent;
- duplicate settlement does not create duplicate payout;
- ticket result derives from legs correctly;
- explicit correction requires a reason and creates audit history;
- bankroll remains reconciled after settlement/correction;
- stale settlement/backlog readiness behaves sensibly.

Use test records or isolated/reversible records rather than corrupting historical truth.

---

# Stage T — Job/readiness failure acceptance

Use `system.jobs.*` to verify the durable job lifecycle:

1. register/seed jobs;
2. start a test job;
3. record success;
4. record a controlled failure;
5. verify consecutive-failure/error fields;
6. verify a later success resets/updates state appropriately;
7. verify `system.health` / readiness surfaces meaningful job state where applicable.

Do not intentionally break unrelated production services to create a failure.

---

# Stage U — Sabi Boy Blog acceptance

Verify migrated historical diary/blog content is displayed correctly.

Test:

```text
blog.triggers
blog.reflection.context
```

Create controlled conditions or use existing real recent data to confirm meaningful trigger types without fabricating a post.

Verify the local `sabi-boy-research.timer` is enabled/active and fires at 08:00 `Africa/Lagos`; it must run the direct compact research service without waking the `prediction` agent. Verify the quiet daily and weekly OpenClaw reflection cron jobs still exist for the `prediction` agent and can execute successfully.

A scheduled run with no meaningful trigger may correctly publish nothing.

Confirm Blog remains Sabi Boy's first-person journal about our work/history, not a generic sports-news feed.

---

# Stage V — Desktop/mobile dashboard acceptance

Test the real migrated dashboard on desktop and a real phone/mobile viewport.

Verify:

- responsive navigation;
- Overview figures;
- Picks filters;
- ticket cards/details;
- bankroll chart;
- P/L values;
- sport/market/bookmaker/strategy breakdowns;
- streak display;
- ticket killers;
- advanced History parent→child comparisons;
- advanced History bookmaker price movement/disagreement;
- Blog index/post display;
- System/readiness/source views;
- no mutation controls;
- PWA/manifest behavior where intended.

Every chart/table should tell **our** history. If real data exposes layout/label problems, fix the V2 UI on `v2`, add regression coverage where practical, and rerun visual checks.

---

# Stage W — Backup timer and restore drill

Verify the timer after staging:

```bash
systemctl --user status sabi-boy-backup.timer --no-pager
systemctl --user list-timers --all | grep sabi-boy-backup
```

Run the service manually once for acceptance:

```bash
systemctl --user start sabi-boy-backup.service
systemctl --user status sabi-boy-backup.service --no-pager
```

Confirm:

- backup manifest created;
- SQLite integrity verified;
- checksum present/valid;
- retention pruner only recognizes/deletes valid Sabi Boy backup sets;
- unknown folders/files under backup storage are not deleted.

Perform a restore drill to a safe temporary/test destination using the repository backup tooling. Verify integrity/checksum and data readability after restore.

Do not overwrite the live V1 DB during the drill.

---

# Stage X — Security / secrets / exposure review

Check at minimum:

- no secrets committed to Git;
- env file permissions restrictive;
- V2 dashboard bound locally unless intentionally proxied;
- no old PIN/write-key endpoint in V2;
- no mutation API methods under `/api/v2`;
- browser JS contains no tokens/secrets;
- logs/reports do not dump secret values;
- paid source calls remain disabled unless configured/justified;
- OpenClaw agent/workspace permissions are correct;
- unrelated agents/automations are untouched;
- backup files have appropriate ownership/permissions;
- Cloudflare/external routing remains unchanged during staging; on this Dell it already targets the shared local port that V2 takes over at replacement.

Record findings and fix blockers before release.

---

# Stage Y — Approved same-port replacement

Inspect and record the real external routing mechanism and current V1 target. On this Dell the route already points to:

```text
http://127.0.0.1:8090
```

Do not edit Cloudflare/tunnel/reverse-proxy routes. After all separate-port checks are green, stop/disable the legacy dashboard, start V2 on the existing port 8090, and immediately verify local and external health:

```bash
.venv/bin/python scripts/sabi_v2_finalize_cutover.py \
  --health-url 'https://ACTUAL-SABI-HOST/health'
```

After local/external V2 verification, remove the active V1 service/checkouts while retaining the verified private archives. Do not merge `v2` to `main` as part of this replacement.

---

# Rollback rule

At any point that V2 threatens data integrity, migration correctness, service stability or OpenClaw integrity, prefer rollback over forcing progress.

If external routing has not changed, normally run:

```bash
.venv/bin/python scripts/sabi_v2_rollback.py
```

If the V2 DB itself must be restored to the pre-stage snapshot:

```bash
.venv/bin/python scripts/sabi_v2_rollback.py --restore-v2-database
```

Before active-V1 cleanup, use the rollback helper normally. After cleanup, recovery requires restoring the verified private V1 archive because no dormant V1 checkout/service is retained.

Do not delete unrelated OpenClaw agents/automations as part of rollback.

---

# Evidence and task-board updates

As each Phase 16 item passes, update `docs/SABIAI_V2_TASKS.md` with evidence rather than simply flipping a checkbox blindly.

Recommended evidence locations:

- `data/release/acceptance-latest.json`
- `data/release/migration-latest.json`
- `data/release/staging-latest.json`
- `data/release/openclaw-*.json`
- verified backup manifests;
- a Work acceptance report under `data/release/` or `docs/`;
- screenshots/notes for dashboard/mobile/browser acceptance where appropriate;
- commit SHA(s) for any fixes made during testing.

Do not commit secret-bearing logs or screenshots.

---

# Final Work report required

At the end of the installation/testing session, provide a concise but complete report containing:

- exact `v2` commit tested;
- Dell/runtime identity and paths used (no secret values);
- full pytest result/count;
- migration reconciliation result;
- bankroll reconciliation result;
- V1 service status and V2 service status;
- OpenClaw workspace/skill/final-tool-surface result;
- subagent/AI Spine result;
- representative multi-sport research result;
- persistent research-case result;
- learned-source result;
- SportyBet and Bet9ja capability results, plus evidence that removed bookmakers are absent from the active surface;
- fresh multi-book comparison result;
- end-to-end conversion/rebuild result;
- settlement-profile and settlement-write results;
- dashboard desktop/mobile result;
- Blog trigger/automation result;
- job failure/readiness result;
- backup timer/restore result;
- security review result;
- cutover rehearsal/rollback readiness;
- every defect found and the fix commit/test added;
- remaining blockers, if any;
- explicit recommendation: `NOT READY`, `READY FOR CUTOVER`, or `READY FOR FINAL RELEASE` with evidence.

Do not call the release ready if any required Phase 16 item remains red.

## Success boundary for this Work phase

The ideal endpoint is:

> V2 has replaced the active Prediction V1 installation on the existing local route; the real history reconciles; the full tests are green; the real `prediction` OpenClaw agent is named Sabi Boy and sees the final V2 skills/tools; representative research/ticket/bookmaker/dashboard/Blog/backup/security checks pass; no wager was placed; Cloudflare routing was not edited; active V1 code/services were removed after verified recovery archives were retained; Phase 16 has evidence for every completed gate.

This replacement does not by itself authorize promotion or merge of `v2` to `main`.
