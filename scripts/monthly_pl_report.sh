#!/usr/bin/env bash
# monthly_pl_report.sh — run accountant.py report and send to WhatsApp. No LLM.
set -euo pipefail
OC=~/.npm-global/bin/openclaw
LAST_MONTH=$(date -d "last month" +%Y-%m)

report=$(python3 ~/.openclaw/workspace/expense-tracker/accountant.py report --month "$LAST_MONTH" 2>/dev/null)
[[ -z "$report" ]] && exit 0

msg="📊 *Monthly P&L — ${LAST_MONTH}*

${report}

Full dashboard: https://picks.hendrix.com.ng"

$OC message send --channel whatsapp --target "+234XXXXXXXXXX" --message "$msg"
