import base64
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from dashboard.v2_app import app as dashboard_app
from sabiai.config import Settings
from sabiai.dashboard import create_push_router
from sabiai.dashboard.branding import make_v1_icon_png, v1_icon_svg
from sabiai.notifications import NotificationHistory, WebPushService
from sabiai.storage import SabiDatabase


def test_dashboard_exposes_installable_pwa_shell_and_backdrop_only_mobile_close():
    client = TestClient(dashboard_app)
    manifest = client.get("/manifest.json")
    assert manifest.status_code == 200
    data = manifest.json()
    assert data["id"] == "/"
    assert data["name"] == "Sabi Boy"
    assert data["short_name"] == "Sabi Boy"
    assert data["display"] == "standalone"
    assert {icon["sizes"] for icon in data["icons"]} >= {"192x192", "512x512"}
    assert any(icon.get("purpose") == "maskable" for icon in data["icons"])
    assert all("?v=2.1.0.8" in icon["src"] for icon in data["icons"])

    worker = client.get("/sw.js")
    assert worker.status_code == 200
    assert "self.addEventListener('push'" in worker.text
    assert "self.addEventListener('fetch'" in worker.text
    assert worker.headers["service-worker-allowed"] == "/"

    shell = client.get("/")
    assert shell.status_code == 200
    assert 'id="menu-close"' not in shell.text
    assert 'id="nav-backdrop"' in shell.text
    assert 'id="notification-button"' in shell.text
    assert 'id="eyebrow"' not in shell.text
    assert 'data-notification-state="off"' in shell.text
    assert 'aria-pressed="false"' in shell.text
    assert 'class="notification-icon"' in shell.text
    assert 'rel="apple-touch-icon"' in shell.text
    assert 'name="apple-mobile-web-app-capable"' in shell.text
    assert '/assets/app.js?v=2.1.0.8' in shell.text
    assert '/assets/app.css?v=2.1.0.8' in shell.text
    assert '<strong>Sabi Boy</strong>' in shell.text
    assert '<title>Sabi Boy knows ball</title>' in shell.text
    assert '<span>Picks</span>' in shell.text
    assert '<span>Notifications</span>' in shell.text
    css = client.get('/assets/app.css').text
    assert 'padding-top: calc(24px + env(safe-area-inset-top))' in css
    assert 'Our record</span>' not in shell.text
    sidebar = shell.text.split('<aside class="sidebar"', 1)[1].split('</aside>', 1)[0]
    topbar = shell.text.split('<header class="topbar">', 1)[1].split('</header>', 1)[0]
    assert 'id="readiness-chip"' in sidebar
    assert '> Online<' not in sidebar
    assert 'id="readiness-chip"' not in topbar
    assert '<div class="brand-mark">SB</div>' not in shell.text
    assert '<img class="brand-mark" src="/assets/icon-192.png?v=2.1.0.8" alt="">' in shell.text
    assert '<span>Sabi\'s Blog</span>' in shell.text
    assert '🔔' not in shell.text
    assert '<span class="nav-icon" aria-hidden="true"><svg viewBox="0 0 24 24">' in shell.text

    favicon = client.get("/favicon.ico")
    icon = client.get("/icon.svg")
    icon_source = client.get("/assets/icon-source.svg")
    maskable_source = client.get("/assets/icon-maskable-source.svg")
    assert favicon.status_code == 200
    assert icon.status_code == 200
    assert favicon.headers["content-type"].startswith("image/png")
    assert favicon.content == make_v1_icon_png(32)
    assert icon.headers["content-type"].startswith("image/svg+xml")
    assert icon.text == v1_icon_svg()
    assert "shape-rendering='crispEdges'" in icon_source.text
    assert "x='48' y='12' width='96' height='24'" in icon_source.text
    assert "x='48' y='84' width='96' height='24'" in icon_source.text
    assert maskable_source.text == icon_source.text
    assert client.get("/assets/icon-192.png").content == make_v1_icon_png(192)
    assert client.get("/assets/icon-maskable-512.png").content == make_v1_icon_png(512)

    app_script = client.get("/assets/app.js")
    assert app_script.status_code == 200
    assert "Add to Home Screen" in app_script.text
    assert "navigator.standalone" in app_script.text
    assert "pushManager.subscribe" in app_script.text
    assert "Notification.requestPermission" not in app_script.text
    assert "r.state === 'not_used_yet' ? 'Not used yet' : r.state" in app_script.text
    assert "'/notifications': ['notifications', 'Notifications']" in app_script.text
    assert "api('/notifications?limit=100')" in app_script.text


def test_push_delivery_is_recorded_without_retaining_endpoint_material(tmp_path):
    settings = Settings(
        repo_root=tmp_path,
        data_dir=tmp_path / "data",
        legacy_bets_db=tmp_path / "legacy.db",
        v2_db=tmp_path / "v2.db",
        timezone="Africa/Lagos",
        paid_sources_enabled=False,
    )
    database = SabiDatabase(settings.v2_db)
    database.initialize()

    report = WebPushService(database, settings).send(
        {
            "title": "Sabi Boy picks",
            "body": "Liverpool to win @ 1.58",
            "tag": "sabi-boy-daily-picks",
            "url": "/picks",
            "endpoint": "https://web.push.apple.com/should-never-be-stored",
        }
    )

    assert report.enabled is False
    rows = NotificationHistory(database).list()
    assert rows[0]["title"] == "Sabi Boy picks"
    assert rows[0]["body"] == "Liverpool to win @ 1.58"
    assert rows[0]["attempted"] == 0
    assert "endpoint" not in rows[0]
    with database.connect() as conn:
        raw = conn.execute("SELECT payload_json FROM notification_history").fetchone()[0]
    assert "should-never-be-stored" not in raw


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


def _push_payload(endpoint: str = "https://web.push.apple.com/subscriptions/device-12345") -> dict:
    p256dh = base64.urlsafe_b64encode(b"\x04" + (b"p" * 64)).decode().rstrip("=")
    auth = base64.urlsafe_b64encode(b"a" * 16).decode().rstrip("=")
    return {"endpoint": endpoint, "keys": {"p256dh": p256dh, "auth": auth}}


def test_push_subscription_requires_allowed_origin_and_never_lists_endpoints(tmp_path):
    settings = _settings(tmp_path)
    SabiDatabase(settings.v2_db).initialize()
    app = FastAPI()
    app.include_router(create_push_router(settings))
    client = TestClient(app)
    payload = _push_payload()

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
    payload = _push_payload("http://web.push.apple.com/subscriptions/device-12345")
    response = client.post(
        "/api/v2/push/subscriptions",
        json=payload,
        headers={"Origin": "http://testserver"},
    )
    assert response.status_code == 422


def test_push_endpoint_rejects_non_push_hosts_and_cross_site_fetches(tmp_path):
    settings = _settings(tmp_path)
    SabiDatabase(settings.v2_db).initialize()
    app = FastAPI()
    app.include_router(create_push_router(settings))
    client = TestClient(app)

    arbitrary = client.post(
        "/api/v2/push/subscriptions",
        json=_push_payload("https://attacker.example/subscriptions/device-12345"),
        headers={"Origin": "http://testserver"},
    )
    cross_site = client.post(
        "/api/v2/push/subscriptions",
        json=_push_payload(),
        headers={"Origin": "http://testserver", "Sec-Fetch-Site": "cross-site"},
    )

    assert arbitrary.status_code == 422
    assert cross_site.status_code == 403


def test_push_endpoint_rejects_malformed_web_push_keys(tmp_path):
    settings = _settings(tmp_path)
    SabiDatabase(settings.v2_db).initialize()
    app = FastAPI()
    app.include_router(create_push_router(settings))
    client = TestClient(app)
    payload = _push_payload()
    payload["keys"]["p256dh"] = "not-a-valid-key"

    response = client.post(
        "/api/v2/push/subscriptions",
        json=payload,
        headers={"Origin": "http://testserver"},
    )

    assert response.status_code == 422
