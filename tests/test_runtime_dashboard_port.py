from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_dashboard_service_uses_configured_loopback_host_and_port():
    unit = (ROOT / "systemd" / "sabi-boy-dashboard.service").read_text(encoding="utf-8")
    assert "Environment=SABIAI_DASHBOARD_HOST=127.0.0.1" in unit
    assert "Environment=SABIAI_DASHBOARD_PORT=8091" in unit
    assert "--host ${SABIAI_DASHBOARD_HOST}" in unit
    assert "--port ${SABIAI_DASHBOARD_PORT}" in unit


def test_release_scripts_do_not_hardcode_the_default_dashboard_url():
    for relative in (
        "scripts/sabi_v2_stage.sh",
        "scripts/sabi_v2_activate_openclaw.sh",
        "scripts/sabi_v2_finalize_cutover.py",
    ):
        text = (ROOT / relative).read_text(encoding="utf-8")
        assert "http://127.0.0.1:8091" not in text
