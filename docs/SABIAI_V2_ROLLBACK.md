# SabiAI V2 — Preservation and Rollback Runbook

This runbook exists to make the V2 migration reversible.

## Non-negotiable rule

Never use the original V1 SQLite database as a migration scratchpad.

V2 development writes to the separate V2 database. Migration rehearsal uses copies created from a verified preservation snapshot.

## Create a preservation snapshot

On the machine that owns the real databases:

```bash
python3 scripts/v2_preserve.py --label before-v2-migration
```

Default sources are:

- `~/.openclaw/workspace/data/bets.db`
- `~/.openclaw/workspace/data/sabiai_v2.db`

A missing optional source is recorded as missing rather than fabricated.

The script:

1. opens each existing source in SQLite read-only mode;
2. requires `PRAGMA quick_check` to return `ok`;
3. copies it with SQLite's backup API;
4. checks the backup too;
5. stores SHA-256 hashes;
6. writes a timestamped `manifest.json`;
7. refuses to overwrite an existing snapshot or the source DB.

## Verify a snapshot

```bash
python3 scripts/v2_preserve.py --verify /path/to/snapshot/manifest.json
```

Do this before a migration rehearsal and again before any rollback restore.

## Migration rehearsal

1. Stop only the V2 writer/jobs involved in the rehearsal.
2. Create and verify a fresh V1 preservation snapshot.
3. Copy the preserved DB into a disposable rehearsal location.
4. Run migration against the disposable copy/new V2 DB.
5. Compare row counts, historical totals, bankroll, strategies and ticket history.
6. Delete only the disposable rehearsal data when finished; keep the preservation snapshot.

## Production rollback principle

A rollback must restore a known-good V1 data state and V1 service configuration. Do not attempt an in-place partial undo of many V2 writes.

Before restore:

1. stop every writer that can touch the database being restored;
2. preserve the failed/current state separately for forensic comparison;
3. verify the chosen preservation manifest/hash;
4. verify SQLite quick_check;
5. restore to a temporary filename first;
6. verify that temporary DB;
7. atomically swap files only after verification;
8. restart the known V1 services;
9. verify dashboard totals, bankroll and pending items.

## Do not automate the destructive restore yet

`v2_preserve.py` intentionally creates/verifies snapshots only. It does not contain a one-command overwrite/restore operation. Restoration remains an explicit operator action until V2 migration/release testing proves the workflow.

## Release gate

V2 cannot replace V1 until at least one full migration rehearsal and one restore rehearsal have been completed successfully on the controlled environment.
