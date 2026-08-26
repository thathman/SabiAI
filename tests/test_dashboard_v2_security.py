from fastapi.testclient import TestClient

from dashboard.v2_app import app


client = TestClient(app)


def test_dashboard_disables_schema_and_interactive_documentation():
    for path in ("/docs", "/redoc", "/openapi.json"):
        response = client.get(path)
        assert response.status_code == 404


def test_dashboard_sets_browser_security_headers_and_disables_api_caching():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["permissions-policy"].startswith("camera=()")
    assert "script-src 'self'" in response.headers["content-security-policy"]
    assert response.headers["cache-control"] == "no-store"


def test_dashboard_rejects_an_untrusted_host_header():
    response = client.get("/health", headers={"host": "attacker.invalid"})

    assert response.status_code == 400
