from __future__ import annotations

import base64
from collections import deque
import ipaddress
from threading import Lock
import time
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator

from sabiai.config import Settings
from sabiai.notifications import WebPushService
from sabiai.storage import SabiDatabase


class PushKeys(BaseModel):
    p256dh: str = Field(min_length=16, max_length=512)
    auth: str = Field(min_length=8, max_length=256)

    @field_validator("p256dh")
    @classmethod
    def valid_p256dh(cls, value: str) -> str:
        decoded = _decode_base64url(value)
        if len(decoded) != 65 or decoded[0] != 4:
            raise ValueError("Push p256dh must be an uncompressed P-256 public key.")
        return value

    @field_validator("auth")
    @classmethod
    def valid_auth(cls, value: str) -> str:
        if len(_decode_base64url(value)) != 16:
            raise ValueError("Push auth secret must be 16 bytes.")
        return value


class PushSubscriptionInput(BaseModel):
    endpoint: str = Field(min_length=20, max_length=2048)
    keys: PushKeys

    @field_validator("endpoint")
    @classmethod
    def valid_endpoint(cls, value: str) -> str:
        if not _valid_push_endpoint(value):
            raise ValueError("Push endpoint must be a supported HTTPS Web Push URL without credentials.")
        return value


class PushUnsubscribeInput(BaseModel):
    endpoint: str = Field(min_length=20, max_length=2048)

    @field_validator("endpoint")
    @classmethod
    def valid_endpoint(cls, value: str) -> str:
        return PushSubscriptionInput.valid_endpoint(value)


def create_push_router(settings: Settings | None = None) -> APIRouter:
    settings = settings or Settings.from_env()
    router = APIRouter(prefix="/api/v2/push", tags=["Sabi Boy PWA Push"])
    limiter = _MutationRateLimiter()

    def service() -> WebPushService:
        return WebPushService(SabiDatabase(settings.v2_db), settings)

    def require_same_origin(request: Request) -> None:
        origin = (request.headers.get("origin") or "").rstrip("/")
        if not origin or origin not in settings.dashboard_allowed_origins:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This push request did not come from an allowed dashboard origin.",
            )
        fetch_site = (request.headers.get("sec-fetch-site") or "").casefold()
        if fetch_site and fetch_site != "same-origin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cross-site push requests are not accepted.",
            )
        if not limiter.allow(_client_key(request)):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many push subscription changes. Try again shortly.",
                headers={"Retry-After": "60"},
            )

    @router.get("/config")
    def config():
        push = service()
        return {
            "available": push.enabled,
            "public_key": settings.vapid_public_key if push.enabled else None,
        }

    @router.post("/subscriptions", status_code=status.HTTP_204_NO_CONTENT)
    def subscribe(payload: PushSubscriptionInput, request: Request):
        require_same_origin(request)
        push = service()
        if not push.enabled:
            raise HTTPException(status_code=503, detail="Push notifications are not configured.")
        try:
            push.subscribe(
                endpoint=payload.endpoint,
                p256dh=payload.keys.p256dh,
                auth=payload.keys.auth,
                user_agent=request.headers.get("user-agent"),
            )
        except ValueError as exc:
            raise HTTPException(status_code=429, detail=str(exc)) from exc

    @router.delete("/subscriptions", status_code=status.HTTP_204_NO_CONTENT)
    def unsubscribe(payload: PushUnsubscribeInput, request: Request):
        require_same_origin(request)
        service().unsubscribe(payload.endpoint)

    return router


PUSH_HOSTS = {
    "fcm.googleapis.com",
    "updates.push.services.mozilla.com",
}
PUSH_HOST_SUFFIXES = (".push.apple.com", ".notify.windows.com")


def _decode_base64url(value: str) -> bytes:
    try:
        return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (ValueError, TypeError) as exc:
        raise ValueError("Push key must be base64url encoded.") from exc


def _valid_push_endpoint(value: str) -> bool:
    parsed = urlsplit(value)
    try:
        port = parsed.port
    except ValueError:
        return False
    host = (parsed.hostname or "").casefold().rstrip(".")
    return (
        parsed.scheme == "https"
        and parsed.username is None
        and parsed.password is None
        and port in {None, 443}
        and bool(parsed.path)
        and (host in PUSH_HOSTS or any(host.endswith(suffix) for suffix in PUSH_HOST_SUFFIXES))
    )


class _MutationRateLimiter:
    def __init__(self, *, max_attempts: int = 30, window_seconds: int = 60):
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._lock = Lock()
        self._attempts: dict[str, deque[float]] = {}

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            attempts = self._attempts.setdefault(key, deque())
            while attempts and now - attempts[0] >= self.window_seconds:
                attempts.popleft()
            if len(attempts) >= self.max_attempts:
                return False
            attempts.append(now)
            if len(self._attempts) > 1000:
                self._attempts = {
                    name: values
                    for name, values in self._attempts.items()
                    if values and now - values[-1] < self.window_seconds
                }
            return True


def _client_key(request: Request) -> str:
    direct = request.client.host if request.client else "unknown"
    forwarded = request.headers.get("cf-connecting-ip")
    if direct in {"127.0.0.1", "::1"} and forwarded:
        try:
            return str(ipaddress.ip_address(forwarded.strip()))
        except ValueError:
            pass
    return direct
