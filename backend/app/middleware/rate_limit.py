"""
ASGI middleware: Redis-backed rate limits for /api (V1).

Mounted after CORSMiddleware so 429 responses still pass through CORS wrapping.
Skips OPTIONS (preflight). Does not apply to /healthz, /docs, etc.
"""

from __future__ import annotations

import json
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.rate_limit import client_ip_from_scope, enforce_rate_limits

API_PREFIX = "/api"
RATE_LIMIT_BODY = json.dumps({"detail": "Rate limit exceeded"}).encode("utf-8")


class RateLimitMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path") or ""
        if not path.startswith(API_PREFIX):
            await self.app(scope, receive, send)
            return

        if scope.get("method") == "OPTIONS":
            await self.app(scope, receive, send)
            return

        headers = list(scope.get("headers") or [])
        hdr_map = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in headers}
        client = scope.get("client")
        ip = client_ip_from_scope(headers, client)
        auth = hdr_map.get("authorization")

        if not await enforce_rate_limits(client_ip=ip, authorization_header=auth):
            await send429(send)
            return

        await self.app(scope, receive, send)


async def send429(send: Send) -> None:
    """Minimal 429 JSON response (ASGI)."""
    await send(
        {
            "type": "http.response.start",
            "status": 429,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(RATE_LIMIT_BODY)).encode("ascii")),
            ],
        }
    )
    await send(
        {
            "type": "http.response.body",
            "body": RATE_LIMIT_BODY,
            "more_body": False,
        }
    )
