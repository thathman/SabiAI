from pathlib import Path

from sabiai import __version__


ROOT = Path(__file__).resolve().parents[1]


def test_v24_pwa_includes_coverage_funnel_asset():
    index = (ROOT / "dashboard" / "v2" / "index.html").read_text(encoding="utf-8")
    worker = (ROOT / "dashboard" / "v2" / "sw.js").read_text(encoding="utf-8")
    assert __version__ == "2.4.0.0"
    assert "coverage_funnel.js?v=2.4.0.0" in index
    assert "/assets/coverage_funnel.js?v=2.4.0.0" in worker


def test_coverage_systemd_unit_runs_no_model_radar_script():
    service = (ROOT / "systemd" / "sabi-boy-coverage.service").read_text(encoding="utf-8")
    timer = (ROOT / "systemd" / "sabi-boy-coverage.timer").read_text(encoding="utf-8")
    runner = ROOT / "scripts" / "sabi_v2_discovery_radar.py"
    assert runner.is_file()
    assert "sabi_v2_discovery_radar.py" in service
    assert "sabi_v2_research_heartbeat.py" not in service
    assert "OnUnitActiveSec=30min" in timer


def test_prepare_stage_and_rollback_own_coverage_lifecycle():
    prepare = (ROOT / "scripts" / "sabi_v2_prepare_runtime.sh").read_text(encoding="utf-8")
    stage = (ROOT / "scripts" / "sabi_v2_stage.sh").read_text(encoding="utf-8")
    rollback = (ROOT / "scripts" / "sabi_v2_rollback.py").read_text(encoding="utf-8")
    assert "sabi-boy-coverage.service" in prepare
    assert "sabi-boy-coverage.timer" in prepare
    assert "sabi_v24_coverage_acceptance.py" in stage
    assert stage.index("sabi-boy-coverage.service") < stage.index('enable --now "$RESEARCH_TIMER"')
    assert "sabi-boy-coverage.timer" in rollback
