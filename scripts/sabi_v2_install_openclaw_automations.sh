#!/usr/bin/env bash
set -euo pipefail

# Install/update Sabi Boy V2's persistent OpenClaw automation jobs.
# This script is idempotent by stable job name. It does not delete unrelated jobs.

ENV_FILE="${SABIAI_ENV_FILE:-$HOME/.config/sabi-boy/sabi-boy.env}"
if [[ -f "$ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  set -a
  source "$ENV_FILE"
  set +a
fi

OPENCLAW_BIN="${OPENCLAW_BIN:-openclaw}"
AGENT_ID="${SABIAI_OPENCLAW_AGENT_ID:-sabi-ai}"
TZ_NAME="${SABIAI_TIMEZONE:-Africa/Lagos}"

if ! command -v "$OPENCLAW_BIN" >/dev/null 2>&1; then
  echo "openclaw CLI was not found: $OPENCLAW_BIN" >&2
  exit 2
fi

jobs_json() {
  "$OPENCLAW_BIN" automations list --all --json
}

job_id_by_name() {
  local wanted="$1"
  local payload
  payload="$(jobs_json)"
  JOBS_PAYLOAD="$payload" python3 - "$wanted" <<'PY'
import json, os, sys
wanted = sys.argv[1]
try:
    data = json.loads(os.environ.get("JOBS_PAYLOAD", ""))
except Exception:
    sys.exit(0)
if isinstance(data, dict):
    rows = data.get("jobs") or data.get("items") or data.get("automations") or []
elif isinstance(data, list):
    rows = data
else:
    rows = []
for row in rows:
    if not isinstance(row, dict):
        continue
    name = str(row.get("name") or "")
    if name == wanted:
        value = row.get("id") or row.get("jobId") or row.get("job_id")
        if value:
            print(value)
        break
PY
}

upsert_agent_job() {
  local name="$1"
  local cron_expr="$2"
  local prompt="$3"
  local existing
  existing="$(job_id_by_name "$name" || true)"

  if [[ -n "$existing" ]]; then
    echo "Updating OpenClaw automation: $name ($existing)"
    "$OPENCLAW_BIN" automations edit "$existing" \
      --cron "$cron_expr" \
      --tz "$TZ_NAME" \
      --session isolated \
      --agent "$AGENT_ID" \
      --message "$prompt" \
      --no-deliver >/dev/null
  else
    echo "Creating OpenClaw automation: $name"
    "$OPENCLAW_BIN" automations add \
      --name "$name" \
      --cron "$cron_expr" \
      --tz "$TZ_NAME" \
      --session isolated \
      --agent "$AGENT_ID" \
      --message "$prompt" \
      --no-deliver >/dev/null
  fi
}

DAILY_PROMPT=$(cat <<'EOF'
Run Sabi Boy's daily reflection workflow. First query system.tools and system.readiness; do not invent unavailable capabilities. Use blog.reflection.context plus our actual recent picks, tickets, results, streaks, settlement changes, research lessons, source discoveries and meaningful bookmaker/ticket work from today. Decide whether there is something genuinely worth writing. If nothing meaningful changed, do not publish a filler post. If there is, write a concise first-person Sabi Boy post in clear everyday language. It may discuss what I watched, what changed my mind, what I got wrong, a ticket lesson, a sport/market I learned more about, source quality, or a pattern in our own history. It is not generic sports news and should not sound like a technical model report. Create and publish it through blog.create/blog.publish with category Daily Reflection and useful tags. Do not send a routine chat notification merely because this scheduled job ran.
EOF
)

WEEKLY_PROMPT=$(cat <<'EOF'
Run Sabi Boy's weekly reflection workflow. Query system.tools and system.readiness first. Use blog.reflection.context, our actual weekly history, bankroll/P&L, streaks, sport/market/bookmaker/strategy breakdowns, ticket killers, conversion/edit lineage, settlement corrections and the week's recent Sabi Boy posts. Revisit earlier beliefs where the new record supports or challenges them. Write in first person using clear everyday language, not technical ML/statistics jargon. Focus on what I learned, what worked, what failed, what I am watching next and where I changed my mind. Do not write generic sports news. Create and publish one Week in Review post through blog.create/blog.publish. If there is truly no meaningful activity to reflect on, skip publication rather than writing filler. Do not send a routine chat notification.
EOF
)

# Daily near the end of Sabi Boy's configured local day; weekly on Sunday evening.
upsert_agent_job "sabi-boy-daily-reflection" "30 22 * * *" "$DAILY_PROMPT"
upsert_agent_job "sabi-boy-weekly-reflection" "0 20 * * 0" "$WEEKLY_PROMPT"

echo "Sabi Boy OpenClaw automations installed/updated for agent '$AGENT_ID' in timezone '$TZ_NAME'."
"$OPENCLAW_BIN" automations list --all
