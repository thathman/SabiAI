from pathlib import Path
from types import SimpleNamespace
from dataclasses import replace

from sabiai.config import Settings
from sabiai.openclaw import SabiToolGateway
from sabiai.research.engine_control import EngineCompletenessService, EngineDecisionStore, EngineGapPlanner
from sabiai.storage import PickRecordService, SabiDatabase
from sabiai.system.research_heartbeat import _record_strategy_picks


def _settings(tmp_path: Path):
    return SimpleNamespace(
        v2_db=tmp_path / "v2.db",
        repo_root=Path(__file__).resolve().parents[1],
        timezone="Africa/Lagos",
        discovery_horizon_hours=72,
    )


def test_gap_planner_returns_ordered_recovery_chain():
    result = EngineGapPlanner().plan(
        {
            "sport": "horse_racing",
            "event": "Example Stakes",
            "odds": [],
            "evidence_packet": {"ready_for_decision": False, "missing_topics": ["form"]},
        }
    )
    codes = [item["code"] for item in result["actions"]]
    assert codes[:2] == ["event_not_canonical", "missing_market_inventory"]
    assert "evidence_incomplete" in codes
    assert "settlement_uncertain" in codes
    assert result["next_action"]["code"] == "event_not_canonical"


def test_completeness_distinguishes_complete_engine_from_live_coverage(tmp_path: Path):
    settings = _settings(tmp_path)
    database = SabiDatabase(settings.v2_db)
    database.initialize()
    report = EngineCompletenessService(settings, database).inspect()
    assert report["engine_code_complete"] is True
    assert report["label"] == "ENGINE COMPLETE — source coverage DEGRADED"
    assert report["contracts"]["sport_profiles"] == 31
    assert report["live_coverage"]["events_discovered"] == 0


def test_decision_context_persists_and_calibrates_settled_results(tmp_path: Path):
    settings = _settings(tmp_path)
    database = SabiDatabase(settings.v2_db)
    database.initialize()
    pick = PickRecordService(database).record(
        {
            "sport": "football",
            "event": "Arsenal vs Chelsea",
            "market": "winner",
            "pick": "Arsenal",
            "decimal_odds": 2.0,
            "confidence_pct": 60,
            "stake": 0,
            "selected": True,
        }
    )
    store = EngineDecisionStore(database)
    saved = store.save(
        pick["id"],
        {
            "offer_ref": "offer:abc",
            "bookmaker": "SportyBet",
            "observed_at": "2026-08-29T10:00:00+00:00",
            "estimated_probability_pct": 60,
            "consensus_probability_pct": 51,
            "fair_odds": 1.961,
            "expected_value_pct": 20,
            "decision_state": "BET",
            "evidence_quality": "strong",
            "evidence_ready": True,
            "evidence_sources": ["ESPN Public Data"],
            "missing_evidence": [],
        },
    )
    assert saved["offer_ref"] == "offer:abc"
    with database.transaction() as conn:
        conn.execute("UPDATE picks_v2 SET outcome='won', settled_at='2026-08-30T10:00:00+00:00' WHERE id=?", (pick["id"],))
    calibration = store.calibration()
    assert calibration["overall"]["settled"] == 1
    assert calibration["overall"]["win_percentage"] == 100.0
    assert calibration["overall"]["maturity"] == "immature"
    assert store.get(pick["id"])["decision_state"] == "BET"


def test_engine_tools_are_exposed_at_gateway_boundary(tmp_path: Path):
    gateway = SabiToolGateway(replace(Settings.from_env(), v2_db=tmp_path / "v2.db", repo_root=Path(__file__).resolve().parents[1]))
    tools = gateway.dispatch("system.tools")["data"]["tools"]
    for name in (
        "engine.completeness",
        "engine.sport_profile",
        "engine.next_actions",
        "engine.price.assess",
        "engine.evidence.build",
        "engine.calibration",
    ):
        assert name in tools
    assessed = gateway.dispatch(
        "engine.price.assess",
        {"estimated_probability_pct": 60, "decimal_odds": 2.0, "confidence_pct": 60},
    )
    assert assessed["ok"] is True
    assert assessed["data"]["expected_value_pct"] == 20.0


def test_precision_promotion_persists_exact_engine_context(tmp_path: Path):
    database = SabiDatabase(tmp_path / "v2.db")
    database.initialize()
    plans = [{
        "strategy_code": "precision_picks",
        "name": "Precision Picks",
        "status": "ready",
        "suggested_stake": "0.00",
        "candidates": [{
            "sport": "football",
            "competition": "Premier League",
            "event": "Home vs Away",
            "market": "winner",
            "pick": "Home",
            "decimal_odds": "2.00",
            "confidence_pct": 60,
            "reason": "Exact price and evidence packet.",
            "source": "SportyBet",
            "bookmaker": "SportyBet",
            "offer_ref": "offer:exact-test",
            "observed_at": "2026-08-29T10:00:00+00:00",
            "estimated_probability_pct": 60,
            "consensus_probability_pct": 51,
            "consensus_fair_odds": 1.961,
            "expected_value_pct": 20,
            "evidence_quality": "strong",
            "evidence_ready_for_decision": True,
            "evidence_sources": ["ESPN Public Data"],
            "missing_evidence_topics": [],
        }],
    }]
    rows = _record_strategy_picks(database, plans, model="qwen3.8-max-preview", source_run_id="run-1")
    assert rows[0]["engine_context_saved"] is True
    assert EngineDecisionStore(database).get(rows[0]["id"])["offer_ref"] == "offer:exact-test"
