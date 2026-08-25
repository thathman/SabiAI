import json
from pathlib import Path
import subprocess

from scripts import sabi_v2_openclaw_acceptance as acceptance


def test_find_agent_supports_list_and_envelope_shapes():
    direct = [
        {"id": "main", "workspace": "/tmp/main"},
        {"id": "sabi-ai", "workspace": "/tmp/sabi"},
    ]
    wrapped = {"agents": direct}

    assert acceptance._find_agent(direct, "sabi-ai")["workspace"] == "/tmp/sabi"
    assert acceptance._find_agent(wrapped, "sabi-ai")["workspace"] == "/tmp/sabi"
    assert acceptance._find_agent(wrapped, "missing") is None


def test_workspace_parser_supports_direct_and_nested_openclaw_shapes():
    assert acceptance._workspace_from_agent({"workspace": "/tmp/sabi"}) == "/tmp/sabi"
    assert acceptance._workspace_from_agent({"config": {"workspaceDir": "/tmp/sabi2"}}) == "/tmp/sabi2"
    assert acceptance._workspace_from_agent({"paths": {"workspace_path": "/tmp/sabi3"}}) == "/tmp/sabi3"


def test_skill_name_parser_handles_common_json_envelopes():
    payload = {
        "ready": [
            {"name": "sabi-boy-core"},
            {"slug": "sabi-boy-bookmaker-workflows"},
        ],
        "data": {
            "skills": [
                {"skillName": "sabi-boy-research-scout"},
                {"skill_name": "sabi-boy-skeptic"},
            ]
        },
    }
    names = acceptance._skill_names(payload)
    assert {
        "sabi-boy-core",
        "sabi-boy-bookmaker-workflows",
        "sabi-boy-research-scout",
        "sabi-boy-skeptic",
    } <= names


def test_json_parser_prefers_stdout_and_accepts_json_only_stderr_fallback():
    command = ["openclaw", "skills", "list", "--json"]
    stdout_proc = subprocess.CompletedProcess(command, 0, stdout='{"skills": []}\n', stderr="warning")
    assert acceptance._json_from_process(stdout_proc, command) == {"skills": []}

    stderr_proc = subprocess.CompletedProcess(command, 0, stdout="", stderr='{"skills": [{"name":"sabi-boy-core"}]}\n')
    assert acceptance._json_from_process(stderr_proc, command)["skills"][0]["name"] == "sabi-boy-core"


def test_json_parser_rejects_non_json_stderr_even_on_zero_exit():
    command = ["openclaw", "skills", "list", "--json"]
    proc = subprocess.CompletedProcess(command, 0, stdout="", stderr="warning: no json here")
    try:
        acceptance._json_from_process(proc, command)
    except acceptance.AcceptanceError as exc:
        assert "valid JSON" in str(exc)
    else:
        raise AssertionError("Non-JSON stderr must not be accepted as a successful JSON response.")


def test_every_required_current_format_skill_exists_with_frontmatter():
    repo = Path(__file__).resolve().parents[1]
    for name in acceptance.REQUIRED_SKILLS:
        path = repo / "skills" / name / "SKILL.md"
        assert path.exists(), name
        text = path.read_text(encoding="utf-8")
        assert text.startswith("---\n"), name
        frontmatter = text.split("---", 2)[1]
        assert f"name: {name}" in frontmatter, name
        assert "description:" in frontmatter, name


def test_required_tool_gate_covers_final_v2_workflows():
    required = set(acceptance.REQUIRED_TOOLS)
    expected = {
        "system.tools",
        "system.readiness",
        "system.jobs.failure",
        "source.discovery.plan",
        "source.discovery.verify",
        "sports.match_snapshot",
        "research.evidence.ingest",
        "research.case.create",
        "research.case.attach",
        "research.case.summary",
        "ticket.research.plan",
        "ticket.draft.lineage",
        "ticket.higher_odds.from_verified_offers",
        "ticket.candidates.compare",
        "market.settlement.profile",
        "bookmaker.compare.plan",
        "bookmaker.compare.from_search",
        "bookmaker.convert.from_search",
        "bookmaker.browser_build.plan",
        "bookmaker.build.verify",
        "bookmaker.browser_health",
        "history.ticket_versions",
        "history.bookmaker_prices",
        "history.price_disagreements",
        "blog.reflection.context",
        "blog.triggers",
    }
    assert expected <= required


def test_release_handoff_documents_exist():
    repo = Path(__file__).resolve().parents[1]
    for name in (
        "SABI_BOY_V2_DEPLOYMENT.md",
        "SABI_BOY_V2_RELEASE_CANDIDATE.md",
        "SABI_BOY_V2_WORK_HANDOFF.md",
        "SABIAI_V2_TASKS.md",
    ):
        assert (repo / "docs" / name).exists(), name
