import json

from scripts import sabi_v2_finalize_cutover as finalizer


class _Response:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return json.dumps(
            {"ok": True, "product": "Sabi Boy", "read_only": True}
        ).encode("utf-8")


def test_cutover_health_fetch_uses_explicit_json_headers(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return _Response()

    monkeypatch.setattr(finalizer.urllib.request, "urlopen", fake_urlopen)

    status, payload = finalizer.fetch_json("https://picks.example.test/health")

    assert status == 200
    assert payload["product"] == "Sabi Boy"
    assert captured["timeout"] == 10
    assert captured["request"].get_header("Accept") == "application/json"
    assert captured["request"].get_header("User-agent") == "Sabi-Boy-V2-Cutover/2.0"


def test_stop_legacy_service_accepts_already_absent_unit(monkeypatch):
    calls = []

    class _Process:
        returncode = 3
        stdout = "inactive\n"

    def fake_run(command, **kwargs):
        calls.append(command)
        return _Process()

    monkeypatch.setattr(finalizer.subprocess, "run", fake_run)

    stopped, detail = finalizer.stop_legacy_service()

    assert stopped is True
    assert "already inactive" in detail
    assert calls == [["systemctl", "--user", "is-active", "sabiai-dashboard.service"]]
