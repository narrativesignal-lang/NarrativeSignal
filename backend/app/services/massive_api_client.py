"""
Sole authorized HTTP entrypoint for Massive (api.massive.com).

Rules:
- Every request acquires quota via ``massive_quota_try_acquire`` before any HTTP call.
- No retries, no alternate Massive endpoints on failure.
- Do not add httpx calls to Massive elsewhere; extend this module only.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import settings
from app.services.massive_quota import massive_quota_try_acquire

logger = logging.getLogger(__name__)

MASSIVE_API_BASE_URL = "https://api.massive.com"


@dataclass(frozen=True)
class MassiveHttpOutcome:
    """Result of one Massive REST call attempt (after quota gate)."""

    quota_reason: str | None  # massive_quota_per_minute | massive_quota_per_day
    rate_limited: bool
    http_error: bool
    payload: Any  # parsed JSON (dict or list) or None


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {settings.massive_api_key}".strip()}


def massive_http_unified_snapshot(
    *,
    ticker_any_of: str,
    limit: int,
    log_context: str,
) -> MassiveHttpOutcome:
    """
    GET /v3/snapshot — consumes exactly one quota unit when HTTP is attempted.
    """
    qr = massive_quota_try_acquire(count=1, log_context=log_context)
    if qr:
        return MassiveHttpOutcome(quota_reason=qr, rate_limited=False, http_error=False, payload=None)

    url = f"{MASSIVE_API_BASE_URL}/v3/snapshot"
    params = {"ticker.any_of": ticker_any_of, "limit": max(1, min(250, limit))}
    try:
        with httpx.Client(timeout=30) as client:
            r = client.get(url, params=params, headers=_headers())
            if r.status_code == 429:
                logger.warning(
                    "job=massive_api_client %s path=snapshot rate_limited=1 status=429",
                    log_context,
                )
                return MassiveHttpOutcome(quota_reason=None, rate_limited=True, http_error=False, payload=None)
            r.raise_for_status()
            return MassiveHttpOutcome(quota_reason=None, rate_limited=False, http_error=False, payload=r.json())
    except httpx.HTTPError as e:
        logger.warning("job=massive_api_client %s path=snapshot http_error=%s", log_context, str(e)[:200])
        return MassiveHttpOutcome(quota_reason=None, rate_limited=False, http_error=True, payload=None)


def massive_http_aggs_range(
    *,
    massive_ticker: str,
    from_date: str,
    to_date: str,
    timespan: str,
    log_context: str,
) -> MassiveHttpOutcome:
    """
    GET /v2/aggs/ticker/... — one quota unit per call.
    """
    qr = massive_quota_try_acquire(count=1, log_context=log_context)
    if qr:
        return MassiveHttpOutcome(quota_reason=qr, rate_limited=False, http_error=False, payload=None)

    url = (
        f"{MASSIVE_API_BASE_URL}/v2/aggs/ticker/{massive_ticker}/range/1/"
        f"{timespan}/{from_date}/{to_date}"
    )
    params = {"sort": "asc", "limit": 5000, "adjusted": "true"}
    try:
        with httpx.Client(timeout=45) as client:
            r = client.get(url, params=params, headers=_headers())
            if r.status_code == 429:
                logger.warning(
                    "job=massive_api_client %s path=aggs ticker=%s rate_limited=1 status=429",
                    log_context,
                    massive_ticker,
                )
                return MassiveHttpOutcome(quota_reason=None, rate_limited=True, http_error=False, payload=None)
            r.raise_for_status()
            return MassiveHttpOutcome(quota_reason=None, rate_limited=False, http_error=False, payload=r.json())
    except httpx.HTTPError as e:
        logger.warning(
            "job=massive_api_client %s path=aggs ticker=%s http_error=%s",
            log_context,
            massive_ticker,
            str(e)[:200],
        )
        return MassiveHttpOutcome(quota_reason=None, rate_limited=False, http_error=True, payload=None)
