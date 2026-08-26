from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from dashboard.v2_app import app as dashboard_app
from sabiai.config import Settings
from sabiai.dashboard import create_push_router
from sabiai.storage import SabiDatabase


def test_dashboard_exposes_installable_pwa_shell_and_mobile_close_controls():
    client = TestClient(dashboard_app)
    manifest = client.get("/manifest.json")
    assert manifest.status_code == 200
    data = manifest.json()
    assert data["id"] == "/"
    assert data["display"] == "standalone"
    assert {icon["sizes"] for icon in data["icons"]} >= {"192x192", "512x512"}
    assert any(icon.get("purpose") == "maskable" for icon in data["icons"])

    worker = client.get("/sw.js")
    assert worker.status_code == 200
    assert "self.addEventListener('push'" in worker.text
    assert "self.addEventListener('fetch'" in worker.text
    assert worker.headers["service-worker-allowed"] == "/"

    shell = client.get("/")
    assert shell.status_code == 200
    assert 'id="menu-close"' in shell.text
    assert 'id="nav-backdrop"' in shell.text
    assert 'id="notification-button"' in shell.text
    assert 'rel="apple-touch-icon"' in shell.text


def _settings(tmp_path: Path) -> Settings:
    key = tmp_path / "vapid.pem"
    key.write_text("test-only", encoding="utf-8")
    return Settings(
        repo_root=tmp_path,
        data_dir=tmp_path / "data",
        legacy_bets_db=tmp_path / "legacy.db",
        v2_db=tmp_path / "v2.db",
        timezone="Africa/Lagos",
        paid_sources_enabled=False,
        vapid_public_key="public-key",
        vapid_private_key_file=key,
        dashboard_allowed_origins=("http://testserver",),
    )


def test_push_subscription_requires_allowed_origin_and_never_lists_endpoints(tmp_path):
    settings = _settings(tmp_path)
    SabiDatabase(settings.v2_db).initialize()
    app = FastAPI()
    app.include_router(create_push_router(settings))
    client = TestClient(app)
    payload = {
        "endpoint": "https://push.example.test/subscriptions/device-12345",
        "keys": {"p256dh": "p" * 65, "auth": "a" * 24},
    }

    assert client.post("/api/v2/push/subscriptions", json=payload).status_code == 403
    subscribed = client.post(
        "/api/v2/push/subscriptions",
        json=payload,
        headers={"Origin": "http://testserver"},
    )
    assert subscribed.status_code == 204
    assert client.get("/api/v2/push/subscriptions").status_code == 405
    with SabiDatabase(settings.v2_db).connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM push_subscriptions").fetchone()[0] == 1

    removed = client.request(
        "DELETE",
        "/api/v2/push/subscriptions",
        json={"endpoint": payload["endpoint"]},
        headers={"Origin": "http://testserver"},
    )
    assert removed.status_code == 204
    with SabiDatabase(settings.v2_db).connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM push_subscriptions").fetchone()[0] == 0


def test_push_endpoint_rejects_non_https_subscription_url(tmp_path):
    settings = _settings(tmp_path)
    SabiDatabase(settings.v2_db).initialize()
    app = FastAPI()
    app.include_router(create_push_router(settings))
    client = TestClient(app)
    response = client.post(
        "/api/v2/push/subscriptions",
        json={
            "endpoint": "http://push.example.test/subscriptions/device-12345",
            "keys": {"p256dh": "p" * 65, "auth": "a" * 24},
        },
        headers={"Origin": "http://testserver"},
    )
    assert response.status_code == 422
