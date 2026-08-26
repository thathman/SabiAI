from pathlib import Path

from sabiai.config import Settings
from sabiai.openclaw.gateway import SabiToolGateway
from sabiai.research import Evidence, EvidenceStore, ResearchCaseStore
from sabiai.storage import SabiDatabase


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        repo_root=tmp_path,
        data_dir=tmp_path / "data",
        legacy_bets_db=tmp_path / "data" / "bets.db",
        v2_db=tmp_path / "data" / "v2.db",
        timezone="Africa/Lagos",
        paid_sources_enabled=False,
    )


def test_research_case_survives_reopen_and_links_evidence(tmp_path: Path):
    db = SabiDatabase(tmp_path / "v2.db")
    db.initialize()
    cases = ResearchCaseStore(db)
    case = cases.create(
        sport="Football",
        event="Arsenal vs Chelsea",
        market="Over 2.5 goals",
        home="Arsenal",
        away="Chelsea",
        objective="Research this before ticket use",
    )
    evidence_id = EvidenceStore(db).save(
        Evidence(
            evidence_type="recent_form",
            summary="Arsenal recent form checked.",
            source_name="official-test",
            reliability="high",
        )
    )
    cases.attach_evidence(case.id, [evidence_id])

    reopened = ResearchCaseStore(db).get(case.id)
    assert reopened is not None
    assert reopened.event == "Arsenal vs Chelsea"
    assert reopened.market == "Over 2.5 goals"
    assert reopened.evidence_ids == [evidence_id]
    assert cases.evidence(case.id)[0]["summary"] == "Arsenal recent form checked."


def test_gateway_can_assess_persistent_case_without_repeating_event_context(tmp_path: Path):
    gateway = SabiToolGateway(_settings(tmp_path))
    created = gateway.dispatch(
        "research.case.create",
        {
            "sport": "Football",
            "event": "Arsenal vs Chelsea",
            "market": "Over 2.5 goals",
            "home": "Arsenal",
            "away": "Chelsea",
        },
    )
    assert created["ok"] is True
    case_id = created["data"]["id"]

    ingested = gateway.dispatch(
        "research.evidence.ingest",
        {
            "case_id": case_id,
            "items": [
                {
                    "evidence_type": "recent_form",
                    "summary": "Recent form checked.",
                    "source_name": "official-test",
                    "reliability": "high",
                },
                {
                    "evidence_type": "availability",
                    "summary": "Availability checked.",
                    "source_name": "official-test",
                    "reliability": "high",
                },
            ],
        },
    )
    assert ingested["ok"] is True
    assert len(ingested["data"]["persisted_ids"]) == 2

    assessed = gateway.dispatch("research.case.assess", {"case_id": case_id})
    assert assessed["ok"] is True
    assert assessed["data"]["event"] == "Arsenal vs Chelsea"
    assert assessed["data"]["case"]["last_assessed_at"] is not None

    loaded = gateway.dispatch("research.case.get", {"case_id": case_id})
    assert loaded["ok"] is True
    assert loaded["data"]["found"] is True
    assert len(loaded["data"]["evidence"]) == 2


def test_research_case_status_validation_and_listing(tmp_path: Path):
    db = SabiDatabase(tmp_path / "v2.db")
    db.initialize()
    store = ResearchCaseStore(db)
    case = store.create(sport="Volleyball", event="A vs B")
    updated = store.update(case.id, status="watching", append_note="Waiting for lineup.")
    assert updated.status == "watch"
    assert "Waiting for lineup." in updated.notes
    assert store.list(status="watch")[0].id == case.id


def test_gateway_normalizes_plain_text_research_case_notes(tmp_path: Path):
    gateway = SabiToolGateway(_settings(tmp_path))
    created = gateway.dispatch(
        "research.case.create",
        {
            "sport": "Volleyball",
            "event": "Acceptance probe",
            "notes": "Reachability is not match verification.",
        },
    )
    assert created["ok"] is True
    assert created["data"]["notes"] == ["Reachability is not match verification."]

    updated = gateway.dispatch(
        "research.case.update",
        {
            "case_id": created["data"]["id"],
            "notes": "Resume from another session.",
        },
    )
    assert updated["ok"] is True
    assert updated["data"]["notes"] == ["Resume from another session."]
