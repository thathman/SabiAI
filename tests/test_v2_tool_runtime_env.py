from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def test_direct_openclaw_bridge_loads_installed_runtime_environment(tmp_path):
    data_dir = tmp_path / "installed-data"
    expected_db = data_dir / "canonical-v2.db"
    env_file = tmp_path / "sabi-boy.env"
    env_file.write_text(
        "\n".join(
            (
                f"SABIAI_REPO_ROOT={ROOT}",
                f"SABIAI_DATA_DIR={data_dir}",
                f"SABIAI_LEGACY_BETS_DB={tmp_path / 'legacy.db'}",
                f"SABIAI_V2_DB={expected_db}",
                "SABIAI_PAID_SOURCES_ENABLED=0",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    env = {key: value for key, value in os.environ.items() if not key.startswith("SABIAI_")}
    env["SABIAI_ENV_FILE"] = str(env_file)
    env["HOME"] = str(tmp_path / "unrelated-home")

    proc = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "sabiai_v2_tool.py"),
            "--init-db",
            "--request",
            json.dumps({"tool": "system.health", "args": {}}),
        ],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert json.loads(proc.stdout)["ok"] is True
    assert expected_db.is_file()
    assert not (tmp_path / "unrelated-home" / ".openclaw" / "workspace" / "data").exists()
