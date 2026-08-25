#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${ROOT}/.venv"
ENV_FILE="${SABIAI_ENV_FILE:-$HOME/.config/sabi-boy/sabi-boy.env}"
RELEASE_DIR="${ROOT}/data/release"
STAGING_STATE="${RELEASE_DIR}/staging-latest.json"
REPORT="${RELEASE_DIR}/openclaw-activation-latest.json"
OPENCLAW_BIN="${OPENCLAW_BIN:-openclaw}"

cd "$ROOT"

if [[ ! -x "$VENV/bin/python" ]]; then
  echo "V2 virtualenv missing. Run scripts/sabi_v2_prepare_runtime.sh first." >&2
  exit 3
fi
if [[ ! -f "$ENV_FILE" ]]; then
  echo "Sabi Boy runtime environment missing: $ENV_FILE" >&2
  exit 4
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

AGENT_ID="${SABIAI_OPENCLAW_AGENT_ID:-sabi-ai}"
mkdir -p "$RELEASE_DIR"

# OpenClaw activation is intentionally post-staging. Do not attach jobs/identity to a V2
# runtime that has not already passed migration + HTTP acceptance beside V1.
if [[ ! -f "$STAGING_STATE" ]]; then
  echo "Staging state is missing: $STAGING_STATE" >&2
  echo "Run scripts/sabi_v2_stage.sh and pass its acceptance gates first." >&2
  exit 10
fi

"$VENV/bin/python" - "$STAGING_STATE" "$ROOT" <<'PY'
import json, pathlib, subprocess, sys
state_path = pathlib.Path(sys.argv[1])
root = pathlib.Path(sys.argv[2]).resolve()
state = json.loads(state_path.read_text(encoding='utf-8'))
if state.get('product') != 'Sabi Boy' or state.get('branch') != 'v2':
    raise SystemExit('Staging state is not a Sabi Boy V2 state file.')
if state.get('v1_changed') is not False:
    raise SystemExit('Staging state does not prove V1 was left unchanged.')
acceptance_path = pathlib.Path(state.get('acceptance_report') or '')
if not acceptance_path.exists():
    raise SystemExit(f'Acceptance report is missing: {acceptance_path}')
acceptance = json.loads(acceptance_path.read_text(encoding='utf-8'))
if not acceptance.get('ok'):
    raise SystemExit('Latest release acceptance report is not green.')
commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
if state.get('commit') != commit:
    raise SystemExit(
        f'Checkout moved after staging: staged {state.get("commit")}, current {commit}. Re-stage before OpenClaw activation.'
    )
PY

# Confirm the staged V2 dashboard is still the real process we accepted.
"$VENV/bin/python" - <<'PY'
import json, urllib.request
for url in ('http://127.0.0.1:8091/health', 'http://127.0.0.1:8091/api/v2/overview'):
    with urllib.request.urlopen(url, timeout=5) as response:
        payload = json.loads(response.read().decode())
    if response.status != 200 or payload.get('product') != 'Sabi Boy':
        raise SystemExit(f'Unexpected V2 response from {url}: {payload}')
health_url = 'http://127.0.0.1:8091/health'
with urllib.request.urlopen(health_url, timeout=5) as response:
    payload = json.loads(response.read().decode())
if payload.get('read_only') is not True:
    raise SystemExit('Staged Sabi Boy dashboard no longer reports read_only=true.')
PY

if ! command -v "$OPENCLAW_BIN" >/dev/null 2>&1; then
  echo "OpenClaw CLI not found: $OPENCLAW_BIN" >&2
  exit 11
fi

# First prove that the existing technical agent already points at this exact V2 workspace and
# can actually see the current-format Sabi Boy skills/tools. We intentionally do not retarget
# an agent automatically here.
"$VENV/bin/python" "$ROOT/scripts/sabi_v2_openclaw_acceptance.py" \
  --env-file "$ENV_FILE" \
  --report "$RELEASE_DIR/openclaw-pre-activation.json"

# Update only the human-visible identity. The machine id remains `sabi-ai` for compatibility.
identity_json="$($OPENCLAW_BIN agents set-identity --agent "$AGENT_ID" --from-identity --json)"
printf '%s\n' "$identity_json" > "$RELEASE_DIR/openclaw-identity-latest.json"

# Re-run all OpenClaw/V2 acceptance checks and install/update Sabi Boy's scheduled reflection
# jobs only after every gate is green.
"$VENV/bin/python" "$ROOT/scripts/sabi_v2_openclaw_acceptance.py" \
  --env-file "$ENV_FILE" \
  --install-automations \
  --report "$REPORT"

# Record activation in staging state without changing V1 or external routing.
"$VENV/bin/python" - "$STAGING_STATE" "$REPORT" "$AGENT_ID" <<'PY'
from datetime import datetime, timezone
import json, pathlib, sys
state_path = pathlib.Path(sys.argv[1])
report_path = pathlib.Path(sys.argv[2])
agent_id = sys.argv[3]
state = json.loads(state_path.read_text(encoding='utf-8'))
report = json.loads(report_path.read_text(encoding='utf-8'))
if not report.get('ok'):
    raise SystemExit('OpenClaw acceptance report is not green; refusing to record activation.')
state['openclaw'] = {
    'agent_id': agent_id,
    'human_identity': 'Sabi Boy',
    'activated_at': datetime.now(timezone.utc).isoformat(),
    'acceptance_report': str(report_path),
    'skills_verified': True,
    'automations_installed': bool(report.get('automations_installed')),
}
state_path.write_text(json.dumps(state, indent=2) + '\n', encoding='utf-8')
print(json.dumps(state['openclaw'], indent=2))
PY

cat <<EOF

Sabi Boy V2 OpenClaw activation passed.
Agent id:             $AGENT_ID
Human identity:       Sabi Boy
OpenClaw acceptance:  $REPORT
V2 remains staged on: 127.0.0.1:8091
V1/external routing:  unchanged

External cutover is still a separate release step.
EOF
