"""
ASGI middleware: Redis-backed rate limits for /api (V1).

Mounted after CORSMiddleware so 429 responses still pass through CORS wrapping.
Skips OPTIONS (preflight). Does not apply to /healthz, /docs, etc.

For POST /api/auth/register and /api/auth/login, buffers the body once so JSON email
can be logged on rate-limit reject without consuming the stream for downstream handlers.
"""

from __future__ import annotations

import json
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.rate_limit import client_ip_from_scope, enforce_rate_limits

API_PREFIX = "/api"
RATE_LIMIT_BODY = json.dumps({"detail": "rate limit exceeded"}).encode("utf-8")

_AUTH_BODY_PATHS = frozenset({"/api/auth/register", "/api/auth/login"})


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

        email_hint: str | None = None
        receive_ = receive

        if scope.get("method") == "POST" and path in _AUTH_BODY_PATHS:
            body_chunks: list[bytes] = []
            more = True
            while more:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                body_chunks.append(message.get("body", b""))
                more = bool(message.get("more_body", False))
            body_bytes = b"".join(body_chunks)
            if body_bytes:
                try:
                    parsed = json.loads(body_bytes.decode("utf-8"))
                    if isinstance(parsed, dict):
                        em = parsed.get("email")
                        if em and isinstance(em, str):
                            email_hint = em.strip()[:160]
                except Exception:
                    pass

            async def receive_replay() -> dict:
                return {"type": "http.request", "body": body_bytes, "more_body": False}

            receive_ = receive_replay

        if not await enforce_rate_limits(
            client_ip=ip,
            authorization_header=auth,
            path=path,
            email_hint=email_hint,
        ):
            await send429(send)
            return

        await self.app(scope, receive_, send)


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
