#!/usr/bin/env bash
# arsenal_notify.sh — cron wrapper for arsenal.py matchday.
# Prints celebration on a fresh Arsenal win; silent otherwise. No LLM.
set -euo pipefail
SCRIPTS="$(cd "$(dirname "$0")" && pwd)"
OC=~/.npm-global/bin/openclaw

msg=$(python3 "$SCRIPTS/arsenal.py" matchday 2>/dev/null || true)
[[ -z "$msg" ]] && exit 0

$OC message send --channel whatsapp --target "+234XXXXXXXXXX" --message "$msg"
