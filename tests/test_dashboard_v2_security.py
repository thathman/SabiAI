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
    assert "worker-src 'self'" in response.headers["content-security-policy"]
    assert "unsafe-eval" not in response.headers["content-security-policy"]
    assert response.headers["strict-transport-security"] == "max-age=31536000"
    assert response.headers["cross-origin-opener-policy"] == "same-origin"
    assert response.headers["cross-origin-resource-policy"] == "same-origin"
    assert response.headers["x-permitted-cross-domain-policies"] == "none"
    assert response.headers["cache-control"] == "no-store"


def test_dashboard_rejects_an_untrusted_host_header():
    response = client.get("/health", headers={"host": "attacker.invalid"})

    assert response.status_code == 400


def test_dashboard_rejects_oversized_mutating_requests_before_parsing():
    response = client.post(
        "/api/v2/push/subscriptions",
        content=b"x" * 20_000,
        headers={"content-type": "application/json", "origin": "http://testserver"},
    )

    assert response.status_code == 413
