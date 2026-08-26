from __future__ import annotations

from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator

from sabiai.config import Settings
from sabiai.notifications import WebPushService
from sabiai.storage import SabiDatabase


class PushKeys(BaseModel):
    p256dh: str = Field(min_length=16, max_length=512)
    auth: str = Field(min_length=8, max_length=256)


class PushSubscriptionInput(BaseModel):
    endpoint: str = Field(min_length=20, max_length=2048)
    keys: PushKeys

    @field_validator("endpoint")
    @classmethod
    def valid_endpoint(cls, value: str) -> str:
        parsed = urlsplit(value)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("Push endpoint must be an HTTPS URL without credentials.")
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

    def service() -> WebPushService:
        return WebPushService(SabiDatabase(settings.v2_db), settings)

    def require_same_origin(request: Request) -> None:
        origin = (request.headers.get("origin") or "").rstrip("/")
        if not origin or origin not in settings.dashboard_allowed_origins:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This push request did not come from an allowed dashboard origin.",
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
