#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${ROOT}/.venv"
CONFIG_DIR="${HOME}/.config/sabi-boy"
ENV_FILE="${CONFIG_DIR}/sabi-boy.env"
UNIT_DIR="${HOME}/.config/systemd/user"
INSTALL_BROWSER=1

for arg in "$@"; do
  case "$arg" in
    --no-browser) INSTALL_BROWSER=0 ;;
    *) echo "Unknown option: $arg" >&2; exit 2 ;;
  esac
done

cd "$ROOT"
branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
if [[ "$branch" != "v2" ]]; then
  echo "Refusing runtime preparation from branch '$branch'. Check out v2 first." >&2
  exit 3
fi

python3 -m venv "$VENV"
"$VENV/bin/python" -m pip install --upgrade pip wheel
"$VENV/bin/python" -m pip install -r "$ROOT/requirements-v2.txt"

if [[ "$INSTALL_BROWSER" -eq 1 ]]; then
  "$VENV/bin/python" -m playwright install chromium
fi

mkdir -p "$CONFIG_DIR" "$UNIT_DIR" "$ROOT/data"
if [[ ! -f "$ENV_FILE" ]]; then
  ROOT_ESCAPED="${ROOT//&/\\&}"
  sed \
    -e "s#/home/hendrix#${HOME//&/\\&}#g" \
    -e "s#${HOME//&/\\&}/.openclaw/workspace#${ROOT_ESCAPED}#g" \
    "$ROOT/config/sabi-boy.env.example" > "$ENV_FILE"
  chmod 600 "$ENV_FILE"
  echo "Created $ENV_FILE"
else
  echo "Keeping existing $ENV_FILE"
fi
"$VENV/bin/python" "$ROOT/scripts/sabi_v2_configure_push.py" --env-file "$ENV_FILE" >/dev/null

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a
: "${SABIAI_DASHBOARD_HOST:=127.0.0.1}"
: "${SABIAI_DASHBOARD_PORT:=8091}"

"$VENV/bin/python" "$ROOT/scripts/sabiai_v2_tool.py" --init-db --request '{"tool":"system.health"}' >/dev/null
printf '%s\n' '{"tool":"source.catalog","args":{}}' | "$VENV/bin/python" "$ROOT/scripts/sabiai_v2_tool.py" >/dev/null

# Render user-systemd units to the actual checkout so V2 works even when the
# repository is not located at the historical ~/.openclaw/workspace path.
ROOT_ESCAPED="${ROOT//&/\\&}"
for unit in sabi-boy-dashboard.service sabi-boy-backup.service sabi-boy-settlement.service sabi-boy-health.service sabi-boy-research.service; do
  sed "s#%h/.openclaw/workspace#${ROOT_ESCAPED}#g" \
    "$ROOT/systemd/$unit" > "$UNIT_DIR/$unit"
done
cp "$ROOT/systemd/sabi-boy-backup.timer" "$UNIT_DIR/sabi-boy-backup.timer"
cp "$ROOT/systemd/sabi-boy-settlement.timer" "$UNIT_DIR/sabi-boy-settlement.timer"
cp "$ROOT/systemd/sabi-boy-health.timer" "$UNIT_DIR/sabi-boy-health.timer"
cp "$ROOT/systemd/sabi-boy-research.timer" "$UNIT_DIR/sabi-boy-research.timer"
systemctl --user daemon-reload

cat <<EOF
Sabi Boy V2 runtime prepared.

Repository:    $ROOT
Branch:        $branch
Virtualenv:    $VENV
Environment:   $ENV_FILE
V2 dashboard:  sabi-boy-dashboard.service (${SABIAI_DASHBOARD_HOST}:${SABIAI_DASHBOARD_PORT}, installed, not started)
Backup service:sabi-boy-backup.service (installed, not started)
Backup timer:  sabi-boy-backup.timer (installed, not enabled)
Result heartbeat:sabi-boy-settlement.timer (installed, not enabled)
Health check:   sabi-boy-health.timer (installed, not enabled; local/no model tokens)
Daily research: sabi-boy-research.timer (installed, not enabled; direct model call, no OpenClaw agent)
Web Push:      configured with a private key outside the repository

No V1 service was stopped and no V1 data was migrated by this preparation step.
EOF
