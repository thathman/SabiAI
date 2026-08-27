from __future__ import annotations

import json
from typing import Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class JsonHttpClient:
    """Small stdlib JSON client used by free/public adapters.

    Adapters can receive a different callable in tests, so network access is never required
    to validate parsing and source-selection behavior locally.
    """

    def __init__(self, *, user_agent: str = "SabiBoy/2.0", timeout_seconds: int = 15):
        self.user_agent = user_agent
        self.timeout_seconds = int(timeout_seconds)

    def get(
        self,
        url: str,
        *,
        params: Mapping[str, object] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> object:
        query = {
            str(key): str(value)
            for key, value in (params or {}).items()
            if value is not None and str(value) != ""
        }
        if query:
            separator = "&" if "?" in url else "?"
            url = f"{url}{separator}{urlencode(query)}"
        request_headers = {"Accept": "application/json", "User-Agent": self.user_agent}
        request_headers.update(dict(headers or {}))
        request = Request(url, headers=request_headers, method="GET")
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                body = response.read().decode(charset)
        except HTTPError as exc:
            raise RuntimeError(f"HTTP {exc.code} from {url}") from exc
        except URLError as exc:
            raise RuntimeError(f"Could not reach {url}: {exc.reason}") from exc
        try:
            return json.loads(body)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Source returned invalid JSON from {url}") from exc

    def post(
        self,
        url: str,
        *,
        payload: Mapping[str, object] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> object:
        request_headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": self.user_agent,
        }
        request_headers.update(dict(headers or {}))
        body = json.dumps(dict(payload or {}), separators=(",", ":")).encode("utf-8")
        request = Request(url, data=body, headers=request_headers, method="POST")
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                response_body = response.read().decode(charset)
        except HTTPError as exc:
            raise RuntimeError(f"HTTP {exc.code} from {url}") from exc
        except URLError as exc:
            raise RuntimeError(f"Could not reach {url}: {exc.reason}") from exc
        try:
            return json.loads(response_body)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Source returned invalid JSON from {url}") from exc
