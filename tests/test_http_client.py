from urllib.parse import parse_qs, urlparse

from sabiai.sources.http import JsonHttpClient


def test_query_boolean_values_use_lowercase_wire_format(monkeypatch):
    seen = {}

    class Response:
        class _Headers:
            @staticmethod
            def get_content_charset():
                return "utf-8"

        headers = _Headers()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b'{"ok": true}'

    def fake_urlopen(request, timeout):
        seen["url"] = request.full_url
        return Response()

    monkeypatch.setattr("sabiai.sources.http.urlopen", fake_urlopen)
    JsonHttpClient().get(
        "https://example.test/events",
        params={"oddsAvailable": True, "live": False, "limit": 2},
    )

    assert parse_qs(urlparse(seen["url"]).query) == {
        "oddsAvailable": ["true"],
        "live": ["false"],
        "limit": ["2"],
    }
