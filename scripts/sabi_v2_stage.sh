#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${ROOT}/.venv"
ENV_FILE="${HOME}/.config/sabi-boy/sabi-boy.env"
SERVICE="sabi-boy-dashboard.service"
BACKUP_TIMER="sabi-boy-backup.timer"
SETTLEMENT_TIMER="sabi-boy-settlement.timer"
HEALTH_TIMER="sabi-boy-health.timer"
RELEASE_DIR="${ROOT}/data/release"
BACKUP_DIR="${ROOT}/data/backups/sabi-boy"
STATE_FILE="${RELEASE_DIR}/staging-latest.json"

cd "$ROOT"
branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
if [[ "$branch" != "v2" ]]; then
  echo "Refusing staging from branch '$branch'. Expected v2." >&2
  exit 3
fi
if [[ ! -x "$VENV/bin/python" ]]; then
  echo "V2 virtualenv missing. Run scripts/sabi_v2_prepare_runtime.sh first." >&2
  exit 4
fi
if [[ ! -f "$ENV_FILE" ]]; then
  echo "Runtime environment missing: $ENV_FILE" >&2
  exit 5
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a
DASHBOARD_HOST="${SABIAI_DASHBOARD_HOST:-127.0.0.1}"
DASHBOARD_PORT="${SABIAI_DASHBOARD_PORT:-8091}"
export SABIAI_DASHBOARD_BASE_URL="http://${DASHBOARD_HOST}:${DASHBOARD_PORT}"
mkdir -p "$RELEASE_DIR" "$BACKUP_DIR"

commit="$(git rev-parse HEAD)"
v1_was_active=false
if systemctl --user is-active --quiet sabiai-dashboard.service 2>/dev/null; then
  v1_was_active=true
fi
backup_timer_was_enabled=false
if systemctl --user is-enabled --quiet "$BACKUP_TIMER" 2>/dev/null; then
  backup_timer_was_enabled=true
fi

# 1) Snapshot both databases before migration. V2 may already exist from preparation.
backup_json="$($VENV/bin/python "$ROOT/scripts/sabi_v2_backup.py" create --destination "$BACKUP_DIR")"
manifest="$(printf '%s' "$backup_json" | "$VENV/bin/python" -c 'import json,sys; print(json.load(sys.stdin)["manifest_path"])')"

# 2) Run deterministic migration and require reconciliation.
"$VENV/bin/python" "$ROOT/scripts/sabi_v2_migrate.py" --require-ready > "$RELEASE_DIR/migration-latest.json"

# 3) Run every release acceptance gate, including an idempotent migration recheck.
if ! "$VENV/bin/python" "$ROOT/scripts/sabi_v2_acceptance.py" \
  --migrate-v1 \
  --report "$RELEASE_DIR/acceptance-latest.json"; then
  echo "Acceptance failed. V2 service will not be started. V1 was not changed." >&2
  exit 20
fi

# 4) Start V2 in parallel with V1.
systemctl --user daemon-reload
systemctl --user restart "$SERVICE"

# 5) Verify the real process over HTTP. Do not trust systemctl active alone.
if ! "$VENV/bin/python" - <<'PY'
import json, os, time, urllib.request
url=os.environ['SABIAI_DASHBOARD_BASE_URL'] + '/health'
last=None
for _ in range(30):
    try:
        with urllib.request.urlopen(url, timeout=2) as r:
            data=json.loads(r.read().decode())
        if r.status == 200 and data.get('ok') and data.get('product') == 'Sabi Boy' and data.get('read_only') is True:
            print(json.dumps(data))
            raise SystemExit(0)
        last=f'unexpected response: {data}'
    except Exception as exc:
        last=str(exc)
    time.sleep(1)
print(last or 'health check failed')
raise SystemExit(1)
PY
then
  systemctl --user stop "$SERVICE" || true
  echo "V2 HTTP health check failed. V2 stopped; V1 left unchanged." >&2
  exit 21
fi

# Verify the main read model too.
if ! "$VENV/bin/python" - <<'PY'
import json, os, urllib.request
with urllib.request.urlopen(os.environ['SABIAI_DASHBOARD_BASE_URL'] + '/api/v2/overview', timeout=5) as r:
    data=json.loads(r.read().decode())
if r.status != 200 or data.get('product') != 'Sabi Boy':
    raise SystemExit(1)
print(json.dumps({'overview_ok': True, 'readiness': (data.get('readiness') or {}).get('state')}))
PY
then
  systemctl --user stop "$SERVICE" || true
  echo "V2 overview check failed. V2 stopped; V1 left unchanged." >&2
  exit 22
fi

# 6) Now that migration/application acceptance passed, enable deterministic verified backups.
if ! systemctl --user enable --now "$BACKUP_TIMER"; then
  systemctl --user stop "$SERVICE" || true
  echo "Could not enable Sabi Boy backup timer. V2 stopped; V1 left unchanged." >&2
  exit 23
fi
backup_timer_enabled=true

if ! systemctl --user enable --now "$SETTLEMENT_TIMER"; then
  systemctl --user stop "$SERVICE" || true
  echo "Could not enable the Sabi Boy settlement heartbeat. V2 stopped." >&2
  exit 24
fi

if ! systemctl --user enable --now "$HEALTH_TIMER"; then
  systemctl --user stop "$SERVICE" || true
  echo "Could not enable the Sabi Boy local health timer. V2 stopped." >&2
  exit 25
fi

"$VENV/bin/python" - "$STATE_FILE" "$manifest" "$commit" "$DASHBOARD_HOST" "$DASHBOARD_PORT" "$v1_was_active" "$backup_timer_was_enabled" "$backup_timer_enabled" <<'PY'
from datetime import datetime, timezone
import json, pathlib, sys
path, manifest, commit, dashboard_host, dashboard_port, v1_active, backup_was_enabled, backup_enabled = sys.argv[1:]
data = {
    'product': 'Sabi Boy',
    'branch': 'v2',
    'commit': commit,
    'staged_at': datetime.now(timezone.utc).isoformat(),
    'backup_manifest': manifest,
    'acceptance_report': str(pathlib.Path(path).with_name('acceptance-latest.json')),
    'migration_report': str(pathlib.Path(path).with_name('migration-latest.json')),
    'v2_service': 'sabi-boy-dashboard.service',
    'v2_host': dashboard_host,
    'v2_port': int(dashboard_port),
    'v1_service_was_active': v1_active.lower() == 'true',
    'backup_timer_was_enabled': backup_was_enabled.lower() == 'true',
    'backup_timer_enabled': backup_enabled.lower() == 'true',
    'settlement_timer_enabled': True,
    'health_timer_enabled': True,
    'v1_changed': False,
    'external_cutover_performed': False,
}
pathlib.Path(path).write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')
print(json.dumps(data, indent=2))
PY

cat <<EOF

Sabi Boy V2 is staged and running on ${DASHBOARD_HOST}:${DASHBOARD_PORT}.
V1 has not been stopped or modified.
Verified daily backups are enabled through $BACKUP_TIMER.
Automatic result settlement is enabled through $SETTLEMENT_TIMER.
Local source/readiness health checks are enabled through $HEALTH_TIMER (no model wake/token use).
Backup manifest: $manifest
Acceptance:     $RELEASE_DIR/acceptance-latest.json
Staging state:  $STATE_FILE

External/Cloudflare cutover is intentionally NOT guessed by this script.
Inspect the live routing on the Dell, point it to ${DASHBOARD_PORT} only after verification,
then record that cutover in the deployment report.
EOF
