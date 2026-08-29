import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace


SCRIPT = Path(__file__).parents[1] / "scripts" / "sabi_v2_settlement_heartbeat.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("sabi_v2_settlement_heartbeat", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_provider_error_is_reported_without_failing_heartbeat(monkeypatch, capsys):
    heartbeat = _load_script()

    class FakeJobs:
        def __init__(self, *_args, **_kwargs):
            pass

        def register(self, *args, **kwargs):
            pass

        def start(self, *args, **kwargs):
            pass

        def success(self, *args, **kwargs):
            self.succeeded = True

        def failure(self, *args, **kwargs):  # pragma: no cover - failure is the regression
            raise AssertionError("provider errors must not fail the heartbeat")

    report = SimpleNamespace(
        changed=0,
        source_errors=("event-1: RuntimeError: result provider unavailable",),
        picks_settled=0,
        ticket_legs_settled=0,
        as_dict=lambda: {
            "checked_events": 1,
            "source_errors": ["event-1: RuntimeError: result provider unavailable"],
            "changed": 0,
        },
    )

    class FakeService:
        def __init__(self, *args, **kwargs):
            pass

        def run(self):
            return report

    monkeypatch.setattr(heartbeat, "Settings", SimpleNamespace(from_env=lambda: SimpleNamespace(v2_db="unused")))
    class FakeDb:
        def initialize(self):
            pass

    monkeypatch.setattr(heartbeat, "SabiDatabase", lambda _: FakeDb())
    monkeypatch.setattr(heartbeat, "JobService", FakeJobs)
    monkeypatch.setattr(heartbeat, "AutomaticSettlementService", FakeService)

    assert heartbeat.main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["warnings"] == list(report.source_errors)
