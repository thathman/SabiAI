from pathlib import Path

from sabiai.config import Settings
from sabiai.notifications import PushDeliveryReport
from sabiai.storage import DailyResearchLog, SabiDatabase
from sabiai.openclaw.gateway import SabiToolGateway
from sabiai.system import research_heartbeat as heartbeat


def settings(tmp_path: Path, **overrides) -> Settings:
    values = {
        "repo_root": tmp_path,
        "data_dir": tmp_path / "data",
        "legacy_bets_db": tmp_path / "legacy.db",
        "v2_db": tmp_path / "data" / "v2.db",
        "timezone": "Africa/Lagos",
        "paid_sources_enabled": False,
        "research_api_key": "test-key",
        "research_sports": ("football",),
    }
    values.update(overrides)
    return Settings(**values)


def test_validation_rejects_model_invented_event_or_price(tmp_path):
    events = [
        {
            "sport": "football",
            "event": "Home vs Away",
            "source": "SportyBet",
            "odds": [{"label": "Home", "decimal_odds": 2.2}],
        }
    ]
    result = {
        "recommendations": [
            {
                "sport": "football",
                "event": "Home vs Away",
                "pick": "Home",
                "market": "match winner",
                "decimal_odds": 9.9,
                "confidence_pct": 80,
            },
            {
                "sport": "football",
                "event": "Invented vs Match",
                "pick": "Invented",
                "decimal_odds": 2.2,
                "confidence_pct": 80,
            },
        ]
    }
    assert heartbeat._validated_recommendations(result, events) == []


def test_validation_accepts_only_supplied_decimal_price(tmp_path):
    events = [
        {
            "sport": "football",
            "event": "Home vs Away",
            "source": "SportyBet",
            "odds": [{"label": "Home", "decimal_odds": 2.2}],
        }
    ]
    result = {
        "recommendations": [
            {
                "sport": "football",
                "event": "home-vs-away",
                "pick": "Home",
                "market": "match winner",
                "decimal_odds": 2.2,
                "confidence_pct": 67,
                "reason": "Fresh source price.",
            }
        ]
    }
    rows = heartbeat._validated_recommendations(result, events)
    assert len(rows) == 1
    assert rows[0]["decimal_odds"] == 2.2
    assert rows[0]["source"] == "SportyBet"


def test_parse_sportybet_fixture_data_is_normalized_with_prices():
    payload = {
        "raw": {
            "data": {
                "events": [
                    {
                        "eventId": "sr:match:1",
                        "tournament": "Premier League",
                        "homeTeamName": "Home",
                        "awayTeamName": "Away",
                        "kickoffTime": 1787943600000,
                        "homeOdds": "2.20",
                        "drawOdds": "3.40",
                        "awayOdds": "3.10",
                    }
                ]
            }
        }
    }
    rows = list(heartbeat._normalize_events(payload, sport="football", source="Parse · SportyBet"))
    assert rows[0]["event"] == "Home vs Away"
    assert rows[0]["event_id"] == "sr:match:1"
    assert len(rows[0]["odds"]) == 3


def test_direct_model_result_and_usage_are_read_without_agent(monkeypatch, tmp_path):
    captured = {}

    def fake_post(base_url, api_key, body):
        captured.update({"base_url": base_url, "model": body["model"], "api_key": api_key})
        return {
            "model": "qwen3.8-max",
            "choices": [{"message": {"content": '{"recommendations": [], "notes": []}'}}],
            "usage": {"prompt_tokens": 68, "total_tokens": 103},
        }

    monkeypatch.setattr(heartbeat, "_post_chat", fake_post)
    result, model, usage = heartbeat.call_research_model(
        settings(tmp_path), day="2026-08-28", events=[]
    )
    assert result == {"recommendations": [], "notes": []}
    assert model == "qwen3.8-max"
    assert usage["prompt_tokens"] == 68
    assert captured["model"] == "qwen3.8-max-preview"
    assert captured["api_key"] == "test-key"


def test_primary_model_timeout_uses_configured_fallback(monkeypatch, tmp_path):
    calls = []

    def fake_post(base_url, api_key, body):
        calls.append((base_url, api_key, body["model"], body["max_tokens"]))
        if body["model"] == "qwen3.8-max-preview":
            raise RuntimeError("read operation timed out")
        return {
            "model": "qwen3.6-flash",
            "choices": [{"message": {"content": '{"recommendations": [], "notes": ["fallback"]}'}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 14},
        }

    monkeypatch.setattr(heartbeat, "_post_chat", fake_post)
    config = settings(
        tmp_path,
        research_fallback_model="qwen3.6-flash",
        research_fallback_api_key="fallback-key",
        research_fallback_api_base_url="https://fallback.example/v1",
    )
    result, model, usage = heartbeat.call_research_model(config, day="2026-08-28", events=[])
    assert result["notes"] == ["fallback"]
    assert model == "qwen3.6-flash"
    assert usage["total_tokens"] == 14
    assert calls == [
        (
            config.research_api_base_url,
            "test-key",
            "qwen3.8-max-preview",
            2200,
        ),
        ("https://fallback.example/v1", "fallback-key", "qwen3.6-flash", 1600),
    ]


def test_failed_scheduled_run_records_failure_and_notifies(monkeypatch, tmp_path):
    config = settings(tmp_path)
    pushed = []

    monkeypatch.setattr(
        heartbeat,
        "collect_fixtures",
        lambda *_args, **_kwargs: ("2026-08-28", [], []),
    )
    monkeypatch.setattr(
        heartbeat,
        "call_research_model",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("provider timeout")),
    )

    class FakePush:
        def __init__(self, *_args, **_kwargs):
            pass

        def send(self, payload):
            pushed.append(payload)

    monkeypatch.setattr(heartbeat, "WebPushService", FakePush)
    try:
        heartbeat.run_research_heartbeat(config)
    except RuntimeError as exc:
        assert str(exc) == "provider timeout"
    else:
        raise AssertionError("expected the scheduled run to fail")

    assert pushed == [
        {
            "title": "Sabi Boy research issue",
            "body": "Daily research did not complete. The system will retry automatically.",
            "tag": "sabi-boy-daily-picks-error",
            "url": "/system",
            "renotify": True,
            "error": "provider timeout",
        }
    ]


def test_scan_log_is_available_to_gateway_context(tmp_path):
    config = settings(tmp_path)
    db = SabiDatabase(config.v2_db)
    db.initialize()
    DailyResearchLog(db).save(
        {
            "run_id": "2026-08-28T08:00:00+00:00",
            "date": "2026-08-28",
            "generated_at": "2026-08-28T08:00:00+00:00",
            "model": "qwen3.8-max",
            "events_considered": 2,
            "source_failures": [],
            "recommendations": [
                {
                    "sport": "football",
                    "event": "Home vs Away",
                    "pick": "Home",
                    "decimal_odds": 1.8,
                    "confidence_pct": 64,
                }
            ],
            "notes": [],
            "usage": {"prompt_tokens": 10},
            "push": {"delivered": 1},
        }
    )
    gateway = SabiToolGateway(config)
    latest = gateway.dispatch("research.scan.latest")
    context = gateway.dispatch("system.daily_research")
    assert latest["ok"] is True
    assert latest["data"]["scan"]["recommendations"][0]["pick"] == "Home"
    assert context["data"]["latest"]["model"] == "qwen3.8-max"


def test_system_timer_owns_daily_research_and_agent_cron_is_disabled():
    root = Path(__file__).resolve().parents[1]
    service = (root / "systemd" / "sabi-boy-research.service").read_text(encoding="utf-8")
    timer = (root / "systemd" / "sabi-boy-research.timer").read_text(encoding="utf-8")
    installer = (root / "scripts" / "sabi_v2_install_openclaw_automations.sh").read_text(encoding="utf-8")
    prepare = (root / "scripts" / "sabi_v2_prepare_runtime.sh").read_text(encoding="utf-8")
    assert "sabi_v2_research_heartbeat.py" in service
    assert "EnvironmentFile=-%h/.openclaw/env/openclaw.env" in service
    assert "Restart=on-failure" in service
    assert "RestartSec=2min" in service
    assert "OnCalendar=*-*-* 08:00:00" in timer
    assert 'disable_agent_job "sabi-boy-daily-picks"' in installer
    assert "sabi-boy-research.service" in prepare


def test_daily_heartbeat_persists_strategy_plans_and_records_precision_pick(monkeypatch, tmp_path):
    config = settings(tmp_path)
    database = SabiDatabase(config.v2_db)
    database.initialize()
    from sabiai.storage import BankrollLedger

    BankrollLedger(database).record("opening_balance", "1000")
    monkeypatch.setattr(
        heartbeat,
        "collect_fixtures",
        lambda settings, now=None: (
            "2026-08-28",
            [{
                "sport": "football",
                "event": "Home vs Away",
                "competition": "Premier League",
                "starts_at": "2099-08-28T18:00:00+00:00",
                "event_id": "sr:match:1",
                "source": "Parse · SportyBet",
                "odds": [{"label": "Home", "decimal_odds": 1.80}],
            }],
            [],
        ),
    )
    monkeypatch.setattr(
        heartbeat,
        "call_research_model",
        lambda settings, day, events: (
            {"recommendations": [{
                "sport": "football",
                "event": "Home vs Away",
                "market": "Home to win",
                "pick": "Home",
                "decimal_odds": 1.80,
                "confidence_pct": 67,
                "reason": "Fresh source price.",
            }], "notes": []},
            "qwen3.8-max-preview",
            {"prompt_tokens": 10, "completion_tokens": 5},
        ),
    )
    monkeypatch.setattr(
        heartbeat.WebPushService,
        "send",
        lambda self, payload: PushDeliveryReport(False, 0, 0, 0, 0),
    )

    report = heartbeat.run_research_heartbeat(config)
    assert report["strategy_plans"]
    assert report["recorded_picks"][0]["owner"] == "sabi_boy"
    assert DailyResearchLog(database).latest()["strategy_plans"]
    with database.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM picks_v2 WHERE owner='sabi_boy' AND record_kind='pick'").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM picks_v2 WHERE owner='sabi_boy' AND record_kind='tip'").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM tickets WHERE strategy_code='daily_chain_1_30'").fetchone()[0] == 1
