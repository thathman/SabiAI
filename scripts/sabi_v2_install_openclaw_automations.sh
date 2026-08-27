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
AGENT_ID="${SABIAI_OPENCLAW_AGENT_ID:-prediction}"
TZ_NAME="${SABIAI_TIMEZONE:-Africa/Lagos}"
GATEWAY_ENV_FILE="${OPENCLAW_GATEWAY_ENV_FILE:-$HOME/.openclaw/env/openclaw.env}"
# Use an explicit delivery route for user-facing alerts.  OpenClaw cannot safely
# resolve "last" when several channels are configured, so fail closed to the
# configured Matrix room unless the operator deliberately overrides it.
DELIVERY_CHANNEL="${SABIAI_OPENCLAW_DELIVERY_CHANNEL:-matrix}"
DELIVERY_TO="${SABIAI_OPENCLAW_DELIVERY_TO:-!lkXVdwqsWDeBqhharF:chat.hendrix.com.ng}"
DELIVERY_ACCOUNT="${SABIAI_OPENCLAW_DELIVERY_ACCOUNT:-sabiai}"
# Daily research is systemd-owned now. These values remain readable by older local
# wrappers, but no daily research prompt is sent through an OpenClaw agent.
RESEARCH_MODEL="${SABIAI_OPENCLAW_RESEARCH_MODEL:-aliyun-token-plan/qwen3.8-max-preview}"
RESEARCH_FALLBACKS="${SABIAI_OPENCLAW_RESEARCH_FALLBACKS:-opencode-go/qwen3.7-max}"

# OpenClaw's cron command needs the resolved gateway credential in a non-interactive shell.
# Import only that one value from the gateway's private environment file; do not source the
# complete file or expose unrelated provider/channel secrets to this installer.
if [[ -z "${OPENCLAW_GATEWAY_TOKEN:-}" && -r "$GATEWAY_ENV_FILE" ]]; then
  OPENCLAW_GATEWAY_TOKEN="$(python3 - "$GATEWAY_ENV_FILE" <<'PY'
from pathlib import Path
import sys

for raw in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines():
    if not raw.startswith("OPENCLAW_GATEWAY_TOKEN="):
        continue
    value = raw.split("=", 1)[1].strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
    print(value, end="")
    break
PY
)"
  export OPENCLAW_GATEWAY_TOKEN
fi

if ! command -v "$OPENCLAW_BIN" >/dev/null 2>&1; then
  echo "openclaw CLI was not found: $OPENCLAW_BIN" >&2
  exit 2
fi

jobs_json() {
  "$OPENCLAW_BIN" cron list --all --json
}

job_id_by_name() {
  local wanted="$1"
  local payload
  payload="$(jobs_json)"
  python3 -c '
import json, sys
wanted = sys.argv[1]
try:
    data = json.load(sys.stdin)
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
' "$wanted" <<<"$payload"
}

upsert_agent_job() {
  local name="$1"
  local cron_expr="$2"
  local prompt="$3"
  local delivery="${4:-quiet}"
  local model="${5:-}"
  local fallbacks="${6:-}"
  local existing
  existing="$(job_id_by_name "$name" || true)"

  local delivery_args=(--no-deliver)
  if [[ "$delivery" == "announce" ]]; then
    delivery_args=(
      --announce
      --best-effort-deliver
      --channel "$DELIVERY_CHANNEL"
      --to "$DELIVERY_TO"
      --account "$DELIVERY_ACCOUNT"
    )
  fi

  if [[ -n "$model" ]]; then
    delivery_args+=(--model "$model")
  fi
  if [[ -n "$fallbacks" ]]; then
    delivery_args+=(--fallbacks "$fallbacks")
  fi

  if [[ -n "$existing" ]]; then
    echo "Updating OpenClaw automation: $name ($existing)"
    "$OPENCLAW_BIN" cron edit "$existing" \
      --cron "$cron_expr" \
      --tz "$TZ_NAME" \
      --session isolated \
      --agent "$AGENT_ID" \
      --message "$prompt" \
      "${delivery_args[@]}" >/dev/null
  else
    echo "Creating OpenClaw automation: $name"
    # Current OpenClaw create/add syntax takes the schedule and agent prompt as positional
    # arguments. Keep flags for identity/session/delivery only.
    "$OPENCLAW_BIN" cron add \
      "$cron_expr" \
      "$prompt" \
      --name "$name" \
      --tz "$TZ_NAME" \
      --session isolated \
      --agent "$AGENT_ID" \
      "${delivery_args[@]}" >/dev/null
  fi
}

disable_agent_job() {
  local name="$1"
  local existing
  existing="$(job_id_by_name "$name" || true)"
  if [[ -n "$existing" ]]; then
    echo "Disabling retired OpenClaw automation: $name ($existing)"
    "$OPENCLAW_BIN" cron edit "$existing" --disable >/dev/null
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

DAILY_PICKS_PROMPT=$(cat <<'EOF'
Run Sabi Boy's daily multi-sport research and picks workflow. Start by querying system.tools and system.readiness. If the system is ACTION LOCKED, explain the blocker and stop. Discover today's events across the broad sports universe, then use the configured free-first sources: TheSportsDB, ESPN Public Data, football-data.org, Parse ESPN, Parse Flashscore, Parse LiveScore and Parse SportyBet when available. If configured, Sports Betting AI Analyzer is an additional read-only opinion that must be independently verified; it is never authoritative. Use OpenClaw Search/Browser for gaps. Never call or recommend Stake or 1xBet. For each serious candidate, establish the exact market and settlement meaning, create or resume a durable research case, gather attributable evidence, run the Skeptic review when required, and use fresh SportyBet/Bet9ja prices only when available. Return only clear recommendations with sport, event, pick, decimal odds, confidence percentage and a one-line reason; say when evidence or price freshness is insufficient. Do not place wagers, submit booking codes, or claim a pick was placed. Do not write an actual settled/placed record unless Hendrix explicitly confirms it was used. Send the concise result to the configured user channel; if no qualifying pick survives the checks, say so plainly. Do not publish a Blog post from this routine.
EOF
)

# Keep the retired source-health prompt defined for compatibility with older local
# installer wrappers; it is deliberately never scheduled below.
SOURCE_HEALTH_PROMPT=$(cat <<'EOF'
Run Sabi Boy's source and readiness monitor. Query system.readiness, system.sources and system.api_economy, and use system.jobs.list to inspect recent heartbeat failures. Do not spend money, place wagers, call Stake or 1xBet, or perform any state-changing bookmaker action. If all monitored components are healthy or merely not used yet, finish without a user-facing message. If a source, job, database, bankroll reconciliation or settlement backlog is degraded or failing, send a short actionable alert naming the component, observed state and safe next check. Do not invent an outage from an uncalled source.
EOF
)

# Daily research is owned by sabi-boy-research.timer and never wakes the full agent.
# Retire any old OpenClaw daily-picks job while preserving it as a disabled history row.
disable_agent_job "sabi-boy-daily-picks"
# Retire the previous token-consuming monitor. The local systemd timer is authoritative.
disable_agent_job "sabi-boy-source-health"
upsert_agent_job "sabi-boy-daily-reflection" "30 22 * * *" "$DAILY_PROMPT"
upsert_agent_job "sabi-boy-weekly-reflection" "0 20 * * 0" "$WEEKLY_PROMPT"

echo "Sabi Boy OpenClaw automations installed/updated for agent '$AGENT_ID' in timezone '$TZ_NAME'."
"$OPENCLAW_BIN" cron list --all
