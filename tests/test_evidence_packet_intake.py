from pathlib import Path

from sabiai.research import EvidencePacketService, EvidenceStore
from sabiai.storage import SabiDatabase


def test_packet_normalizes_multiple_external_findings_without_persistence():
    result = EvidencePacketService().ingest(
        [
            {
                "evidence_type": "form",
                "summary": "Arsenal have won four of their last five home matches.",
                "source_name": "League site",
                "reliability": "high",
            },
            {
                "type": "availability",
                "finding": "Chelsea list Player A as unavailable.",
                "source_name": "Chelsea",
                "reliability": "official",
                "raw": {"player": "Player A", "available": False},
            },
        ],
        persist=False,
    )
    assert result.usable is True
    assert len(result.items) == 2
    assert result.items[0].id.startswith("evidence_external_")
    assert result.items[1].evidence_type == "availability"


def test_packet_rejects_missing_attribution_without_losing_good_items():
    result = EvidencePacketService().ingest(
        [
            {
                "evidence_type": "form",
                "summary": "Useful finding",
                "source_name": "Official source",
            },
            {
                "evidence_type": "injury",
                "summary": "Unattributed finding",
            },
        ]
    )
    assert result.usable is False
    assert len(result.items) == 1
    assert len(result.rejected) == 1
    assert "source_name" in result.rejected[0]["error"]


def test_packet_uses_defaults_and_stable_ids():
    service = EvidencePacketService()
    kwargs = dict(
        items=[{"type": "context", "finding": "The match decides qualification."}],
        default_source_name="Competition site",
        default_source_url="https://example.test/match",
        default_reliability="official",
    )
    first = service.ingest(**kwargs)
    second = service.ingest(**kwargs)
    assert first.items[0].id == second.items[0].id
    assert first.items[0].source_name == "Competition site"
    assert first.items[0].reliability == "official"


def test_persisted_packet_requires_canonical_event_id(tmp_path: Path):
    db = SabiDatabase(tmp_path / "v2.db")
    db.initialize()
    service = EvidencePacketService(EvidenceStore(db))
    try:
        service.ingest(
            [{"type": "form", "finding": "A", "source_name": "Source"}],
            persist=True,
        )
    except ValueError as exc:
        assert "canonical event_id" in str(exc)
    else:
        raise AssertionError("Expected canonical event_id requirement.")


def test_case_scoped_packet_can_persist_before_canonical_event_resolution(tmp_path: Path):
    db = SabiDatabase(tmp_path / "v2.db")
    db.initialize()
    service = EvidencePacketService(EvidenceStore(db))
    result = service.ingest(
        [
            {
                "type": "form",
                "finding": "Arsenal's recent form was checked.",
                "source_name": "Official source",
            }
        ],
        persist=True,
        case_scoped=True,
    )
    assert result.usable is True
    assert len(result.persisted_ids) == 1
