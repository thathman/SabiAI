import os
from pathlib import Path
import subprocess
import sys

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


ROOT = Path(__file__).resolve().parents[1]


def test_push_configuration_generates_private_key_outside_repo_and_is_idempotent(tmp_path):
    env_file = tmp_path / "sabi-boy.env"
    env_file.write_text("SABIAI_VAPID_SUBJECT=https://picks.hendrix.com.ng\n", encoding="utf-8")
    command = [
        sys.executable,
        str(ROOT / "scripts" / "sabi_v2_configure_push.py"),
        "--env-file",
        str(env_file),
    ]
    subprocess.run(command, check=True, capture_output=True, text=True)
    first = env_file.read_text(encoding="utf-8")
    subprocess.run(command, check=True, capture_output=True, text=True)
    second = env_file.read_text(encoding="utf-8")

    values = dict(line.split("=", 1) for line in first.splitlines() if "=" in line)
    key_file = Path(values["SABIAI_VAPID_PRIVATE_KEY_FILE"])
    assert key_file.parent == tmp_path
    assert key_file.stat().st_mode & 0o777 == 0o600
    key = serialization.load_pem_private_key(key_file.read_bytes(), password=None)
    assert isinstance(key, ec.EllipticCurvePrivateKey)
    assert len(values["SABIAI_VAPID_PUBLIC_KEY"]) >= 80
    assert first == second
    assert env_file.stat().st_mode & 0o777 == 0o600


def test_settlement_timer_is_fixed_schedule_and_installed_by_runtime_prepare():
    timer = (ROOT / "systemd" / "sabi-boy-settlement.timer").read_text(encoding="utf-8")
    prepare = (ROOT / "scripts" / "sabi_v2_prepare_runtime.sh").read_text(encoding="utf-8")
    stage = (ROOT / "scripts" / "sabi_v2_stage.sh").read_text(encoding="utf-8")
    assert "OnUnitActiveSec=10m" in timer
    assert "Persistent=true" in timer
    assert "sabi-boy-settlement.service" in prepare
    assert 'enable --now "$SETTLEMENT_TIMER"' in stage
