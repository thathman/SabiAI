#!/usr/bin/env bash
# backup_bets_db.sh — daily SQLite backup of bets.db with 7-day rotation.
# Cron: 30 5 * * * ~.openclaw/workspace/scripts/backup_bets_db.sh
set -euo pipefail

DB=~.openclaw/workspace/data/bets.db
BACKUP_DIR=~.openclaw/workspace/data/backups
mkdir -p "$BACKUP_DIR"

STAMP=$(date +%Y%m%d)
OUT="$BACKUP_DIR/bets_$STAMP.db"

# .backup is transactionally safe even mid-write (unlike cp)
sqlite3 "$DB" ".backup '$OUT'"
gzip -f "$OUT"

# Keep last 7 days
find "$BACKUP_DIR" -name "bets_*.db.gz" -mtime +7 -delete

echo "$(date -Iseconds) backed up to $OUT.gz ($(du -h "$OUT.gz" | cut -f1))"
