#!/usr/bin/env bash
# value_bet_daily.sh — SabiAI daily pipeline.
# Kelly picks are the daily output.
# Chain stays manual from the qualifying Kelly list.
# Long-shot runs automatically on Mondays from the qualifying Kelly list.
# Live bets stay on their separate cron (live_bets.py).
# Lagos = UTC+1. Cron: 0 7 * * * = 08:00 Lagos.
set -uo pipefail

SCRIPTS="$(cd "$(dirname "$0")" && pwd)"
PYTHON="python3"
LOG_DIR="${HOME}/.openclaw/workspace/memory/daily"
LOG="${LOG_DIR}/$(date +%Y-%m-%d)-pipeline.log"
OUTPUT="/tmp/sabiai_scan_$(date +%Y%m%d).txt"
COMBO_OUTPUT="/tmp/sabiai_combos_$(date +%Y%m%d).txt"
TG_GROUP="-1003892428943"
TG_TOPIC="188"

mkdir -p "$LOG_DIR"
source /home/hendrix/.openclaw/workspace/skills/agentmail/scripts/load_env.sh 2>/dev/null || true

log() { echo "[$(date -Iseconds)] $*" >> "$LOG"; }
log "=== Pipeline start ==="

# 0. Daily DB backup (transactionally safe, 7-day rotation)
"$SCRIPTS/backup_bets_db.sh" >> "$LOG" 2>&1 && log "Backup: done" || log "Backup: FAILED"

# 1. Auto-settle yesterday's picks
SETTLE=$($PYTHON "$SCRIPTS/value_bet_finder.py" --auto-settle 2>&1 | grep "^Auto-settle:" | head -1 || true)
log "Settle: ${SETTLE:-skipped}"

# 1b. Learning loop: analyze settled bets → write learned_adjustments for the scanner
$PYTHON "$SCRIPTS/sabiai_analyze.py" --days 30 --quiet 2>>"$LOG" && log "Learn: adjustments updated" || log "Learn: skipped"

# 1c. CLV refresh — capture closing odds on pending picks (was standalone 16:30 UTC cron)
$PYTHON "$SCRIPTS/value_bet_finder.py" --refresh-clv 2>>"$LOG" && log "CLV: refreshed" || log "CLV: failed"

# 2. Record
RECORD=$($PYTHON "$SCRIPTS/record.py" 2>/dev/null || echo "📈 Fresh start")

# 3. Scan: confidence 55%+, band 1.30-2.50, EV 3%+
$PYTHON "$SCRIPTS/value_bet_finder.py" \
    --format simple --band 1.30-2.50 --min-ev 0.03 \
    > "$OUTPUT" 2>>"$LOG" || {
    log "Scanner failed"
    ~/.npm-global/bin/openclaw message send \
        --channel telegram --target "$TG_GROUP" --thread-id "$TG_TOPIC" \
        --message "⚠️ SabiAI scan failed" 2>>/dev/null || true
    exit 1
}

# Filter: keep 🟢/🟡 picks plus safe accumulator legs for chain mode
FILTERED=$($PYTHON "$SCRIPTS/filter_high_conf.py" "$OUTPUT" --chain-mode 2>/dev/null)
# grep -c returns 0 with exit code 1 when no matches — don't use || to avoid doubling the count
HIGH_CONF=$(echo "$FILTERED" | grep -cE '^(🟢|🟡)' 2>/dev/null) || HIGH_CONF=0
HIGH_CONF="${HIGH_CONF//[^0-9]/}"   # strip any extra whitespace/newlines
HIGH_CONF=${HIGH_CONF:-0}

# Chain combo recipes
$PYTHON "$SCRIPTS/combo_recipes.py" --date "$(date +%Y-%m-%d)" > "$COMBO_OUTPUT" 2>>"$LOG" \
    && log "Combos: generated" || log "Combos: failed"
COMBOS="$(cat "$COMBO_OUTPUT" 2>/dev/null || true)"
COMBO_SECTION=""
if [[ -n "$COMBOS" ]]; then
    COMBO_SECTION="

${COMBOS}"
fi

# 4a. WhatsApp — Kelly picks
TODAY=$(date +'%a %d %b %Y')
if [[ -z "$FILTERED" || "$HIGH_CONF" -lt 1 ]]; then
    MSG="🟢 *SabiAI — ${TODAY}*

No high-confidence picks today.
${COMBO_SECTION}
${RECORD}"
else
    MSG="🟢 *SabiAI Picks — ${TODAY}*

${FILTERED}
${COMBO_SECTION}

${RECORD}"
fi

~/.npm-global/bin/openclaw message send \
    --channel telegram --target "$TG_GROUP" --thread-id "$TG_TOPIC" \
    --message "$MSG" 2>>"$LOG" && log "Telegram Kelly: ${HIGH_CONF} picks sent" || log "Telegram Kelly failed"

# 4b. WhatsApp — Long shot (Mondays only)
if [[ "$(date +%u)" == "1" ]]; then
    log "Monday — firing long shot"
    $PYTHON "$SCRIPTS/weekly_long_shot.py" >> "$LOG" 2>&1 || log "Long shot failed"
    log "Long shot done"
fi

# 5. Diary fallback — write yesterday's entry if the OpenClaw agent didn't
$PYTHON "$SCRIPTS/diary_auto.py" "$(date -d yesterday +%F)" >> "$LOG" 2>&1 || log "diary_auto failed"

log "=== Pipeline complete ==="
