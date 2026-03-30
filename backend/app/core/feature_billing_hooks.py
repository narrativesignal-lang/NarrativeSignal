"""
Placeholder hooks for credits and metering. **Not used by ``can_access_feature`` today.**

Wire these after you add a usage ledger and real balance rules. Call order for a billable AI request
should remain:

1. ``can_access_feature`` (entitlement / tier)
2. ``can_consume_feature`` (credits / quota — stub always allows today)
3. Run provider call
4. ``charge_feature_credits`` + append usage row (stubs are no-op today)

See ``docs/feature_access_and_tiers.md`` and ``docs/ai_usage_ledger.md``.
"""

from __future__ import annotations

from typing import Any

from app.models.user import User


def can_consume_feature(
    user: User,
    feature_name: str,
    *,
    estimated_credits: int = 0,
    **_: Any,
) -> bool:  # noqa: ARG001
    """
    Future: return False when ``credits_balance`` (or quota) is insufficient for this call.

    **Stub:** always ``True``. Entitlement is still enforced only by ``can_access_feature``;
    do not use this alone as an access check.
    """
    return True


def estimate_feature_credit_cost(feature_name: str, **kwargs: Any) -> int:  # noqa: ARG001
    """
    Future: map ``feature_name`` (+ payload hints in ``kwargs``) to internal credit units.

    **Stub:** always ``0``.
    """
    return 0


def charge_feature_credits(
    user: User,
    feature_name: str,
    credits: int,
    **kwargs: Any,
) -> None:  # noqa: ARG001
    """
    Future: decrement ``user.credits_balance``, append ledger rows, raise on insufficient funds.

    **Stub:** no-op.
    """
    return None
