"""
Unified merge rules: never replace a successful value with null/empty on failed refresh.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, TypeVar

T = TypeVar("T")


def merge_optional(prev: T | None, new: T | None) -> T | None:
    """If new is None, keep prev."""
    if new is None:
        return prev
    return new


def merge_quote_row(
    prev_price: float | None,
    prev_change: float | None,
    new_price: float | None,
    new_change: float | None,
) -> tuple[float | None, float | None]:
    """Never downgrade to null when we had a value."""
    return (merge_optional(prev_price, new_price), merge_optional(prev_change, new_change))


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
