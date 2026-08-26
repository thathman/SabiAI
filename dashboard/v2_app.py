#!/usr/bin/env python3
from __future__ import annotations

import os
from pathlib import Path
import sys

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, Response
from starlette.middleware.trustedhost import TrustedHostMiddleware

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sabiai.dashboard import create_push_router, create_v2_dashboard_router

ASSET_DIR = Path(__file__).with_name("v2")

app = FastAPI(
    title="Sabi Boy",
    description="Read-only dashboard for our Sabi Boy history, performance and journal.",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)
allowed_hosts = [
    host.strip()
    for host in os.environ.get(
        "SABIAI_DASHBOARD_ALLOWED_HOSTS",
        "127.0.0.1,localhost,picks.hendrix.com.ng,testserver",
    ).split(",")
    if host.strip()
]
app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)
app.include_router(create_v2_dashboard_router())
app.include_router(create_push_router())


@app.middleware("http")
async def dashboard_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault(
        "Permissions-Policy",
        "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
    )
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; "
        "frame-ancestors 'none'; form-action 'none'",
    )
    if request.url.path.startswith("/api/v2") or request.url.path in {"/health", "/sw.js"}:
        response.headers.setdefault("Cache-Control", "no-store")
    return response


@app.get("/health")
def health():
    return {"ok": True, "product": "Sabi Boy", "dashboard": "v2", "read_only": True}


@app.get("/manifest.json")
def manifest():
    return {
        "id": "/",
        "name": "Sabi Boy",
        "short_name": "Sabi Boy",
        "description": "Our sports intelligence history, performance and journal.",
        "start_url": "/?source=pwa",
        "scope": "/",
        "display": "standalone",
        "display_override": ["window-controls-overlay", "standalone", "minimal-ui"],
        "orientation": "portrait-primary",
        "background_color": "#0b0b0d",
        "theme_color": "#111216",
        "categories": ["sports", "finance"],
        "icons": [
            {"src": "/assets/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
            {"src": "/assets/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any"},
            {"src": "/assets/icon-maskable-192.png", "sizes": "192x192", "type": "image/png", "purpose": "maskable"},
            {"src": "/assets/icon-maskable-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
        ],
        "shortcuts": [
            {"name": "Games and picks", "short_name": "Picks", "url": "/picks", "icons": [{"src": "/assets/icon-192.png", "sizes": "192x192"}]},
            {"name": "Tickets", "short_name": "Tickets", "url": "/tickets", "icons": [{"src": "/assets/icon-192.png", "sizes": "192x192"}]},
            {"name": "System health", "short_name": "System", "url": "/system", "icons": [{"src": "/assets/icon-192.png", "sizes": "192x192"}]},
        ],
    }


@app.get("/icon.svg")
def icon():
    svg = """<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 192 192'>
<rect width='192' height='192' rx='42' fill='#111216'/>
<circle cx='96' cy='96' r='61' fill='none' stroke='#e6b252' stroke-width='7'/>
<text x='96' y='121' font-family='Georgia,serif' font-size='72' font-weight='700' fill='#f5f0e8' text-anchor='middle'>SB</text>
</svg>"""
    return Response(svg, media_type="image/svg+xml")


@app.get("/sw.js")
def service_worker():
    path = ASSET_DIR / "sw.js"
    if not path.is_file():
        return Response(status_code=404)
    return FileResponse(
        path,
        media_type="text/javascript; charset=utf-8",
        headers={"Service-Worker-Allowed": "/", "Cache-Control": "no-cache"},
    )


@app.get("/assets/{name}")
def asset(name: str):
    safe = Path(name).name
    path = ASSET_DIR / safe
    if not path.is_file():
        return Response(status_code=404)
    media = {
        ".css": "text/css; charset=utf-8",
        ".js": "text/javascript; charset=utf-8",
        ".svg": "image/svg+xml",
        ".png": "image/png",
    }.get(path.suffix.lower(), "application/octet-stream")
    return FileResponse(path, media_type=media)


@app.get("/")
@app.get("/{page:path}")
def shell(page: str = ""):
    # API/static/health routes match before this catch-all. All UI routes share one shell.
    if page in {"docs", "redoc", "openapi.json"}:
        return Response(status_code=404)
    index = ASSET_DIR / "index.html"
    if not index.is_file():
        return HTMLResponse("<h1>Sabi Boy V2</h1><p>Dashboard assets are missing.</p>", status_code=503)
    return FileResponse(index, media_type="text/html; charset=utf-8")
