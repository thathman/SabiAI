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


def test_openclaw_scripts_use_current_cron_cli_and_explicit_human_identity():
    installer = (ROOT / "scripts" / "sabi_v2_install_openclaw_automations.sh").read_text(
        encoding="utf-8"
    )
    activation = (ROOT / "scripts" / "sabi_v2_activate_openclaw.sh").read_text(
        encoding="utf-8"
    )

    assert '"$OPENCLAW_BIN" cron list --all --json' in installer
    assert '"$OPENCLAW_BIN" cron add' in installer
    assert '"$OPENCLAW_BIN" cron edit' in installer
    assert '"$OPENCLAW_BIN" automations' not in installer
    assert "OPENCLAW_GATEWAY_ENV_FILE" in installer
    assert 'raw.startswith("OPENCLAW_GATEWAY_TOKEN=")' in installer
    assert 'source "$GATEWAY_ENV_FILE"' not in installer
    assert "JOBS_PAYLOAD" not in installer
    assert 'json.load(sys.stdin)' in installer
    assert 'aliyun-token-plan/qwen3.8-max-preview' in installer
    assert 'opencode-go/qwen3.7-max' in installer
    assert 'disable_agent_job "sabi-boy-source-health"' in installer
    assert 'config set "agents.list[$agent_index].name"' in activation
    assert '--name "Sabi Boy"' in activation
    assert '--emoji "🧠⚽"' in activation
    assert "--from-identity" not in activation


def test_openclaw_bootstrap_targets_prediction_v2_runtime():
    tools = (ROOT / "TOOLS.md").read_text(encoding="utf-8")
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    identity = (ROOT / "IDENTITY.md").read_text(encoding="utf-8")

    assert "~/.openclaw/workspace-prediction/" in tools
    assert ".venv/bin/python scripts/sabiai_v2_tool.py --request" in tools
    assert "~/.openclaw/workspace/scripts/sabiai_v2_tool.py" not in tools
    assert "~/.openclaw/workspace/data/sabiai_v2_core.db" not in tools
    assert "AI_AGENT=prediction" in tools
    assert "AI_AGENT=prediction" in agents
    assert "machine agent ID:** `prediction`" in identity


def test_runtime_defaults_target_existing_prediction_agent_and_workspace():
    environment = (ROOT / "config" / "sabi-boy.env.example").read_text(encoding="utf-8")
    activation = (ROOT / "scripts" / "sabi_v2_activate_openclaw.sh").read_text(
        encoding="utf-8"
    )
    installer = (ROOT / "scripts" / "sabi_v2_install_openclaw_automations.sh").read_text(
        encoding="utf-8"
    )

    assert "SABIAI_REPO_ROOT=/home/hendrix/.openclaw/workspace-prediction" in environment
    assert "SABIAI_DATA_DIR=/home/hendrix/.openclaw/workspace-prediction/data" in environment
    assert "SABIAI_OPENCLAW_AGENT_ID=prediction" in environment
    assert 'SABIAI_OPENCLAW_AGENT_ID:-prediction' in activation
    assert 'SABIAI_OPENCLAW_AGENT_ID:-prediction' in installer
