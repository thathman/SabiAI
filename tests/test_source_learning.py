from pathlib import Path

from sabiai.config import Settings
from sabiai.openclaw.gateway import SabiToolGateway
from sabiai.sources import SourceLearningService
from sabiai.storage import SabiDatabase


def test_learned_source_candidate_can_be_verified_and_reused(tmp_path: Path):
    db = SabiDatabase(tmp_path / "v2.db")
    db.initialize()
    service = SourceLearningService(db)
    candidate = service.discover(
        name="Example Volleyball Federation",
        url="https://example.test/volleyball",
        kind="federation",
        sports=["Volleyball"],
        capabilities=["fixtures", "availability"],
        notes="Official federation test source.",
    )
    assert candidate.status == "candidate"

    verified = service.verify(candidate.id, reliability="official")
    assert verified.status == "verified"
    assert verified.reliability == "official"

    checked = service.record_check(candidate.id, ok=True)
    assert checked.last_check_ok is True
    assert service.best(sport="volleyball", capability="fixtures")[0].id == candidate.id


def test_source_discovery_openclaw_tools_persist_across_gateway_instances(tmp_path: Path):
    settings = Settings(
        repo_root=tmp_path,
        data_dir=tmp_path / "data",
        legacy_bets_db=tmp_path / "data" / "bets.db",
        v2_db=tmp_path / "data" / "v2.db",
        timezone="Africa/Lagos",
        paid_sources_enabled=False,
    )
    first = SabiToolGateway(settings)
    saved = first.dispatch(
        "source.discovery.save",
        {
            "name": "Example Rugby League",
            "url": "https://example.test/rugby",
            "kind": "league",
            "sport": "Rugby",
            "capability": "results",
        },
    )
    assert saved["ok"] is True
    source_id = saved["data"]["id"]
    verified = first.dispatch(
        "source.discovery.verify",
        {"source_id": source_id, "reliability": "official"},
    )
    assert verified["ok"] is True

    second = SabiToolGateway(settings)
    plan = second.dispatch(
        "source.discovery.plan",
        {"sport": "Rugby", "capability": "results"},
    )
    assert plan["ok"] is True
    assert plan["data"]["needs_discovery"] is False
    assert plan["data"]["verified_sources"][0]["url"] == "https://example.test/rugby"
