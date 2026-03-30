"""
Canonical product plan and AI access labels (stored as strings on ``User``).

Use these enums instead of ad-hoc literals so billing and webhooks can share one vocabulary.
Values are lowercase snake-friendly slugs for JSON/DB compatibility.

**Plan codes** map to commercial tiers; ``ADMIN`` is reserved for non-billable operator accounts
if you choose to persist it on ``users.plan_code`` (distinct from ``user_is_admin``).
"""

from __future__ import annotations

from enum import Enum


class PlanCode(str, Enum):
    FREE = "free"
    BASIC_AI = "basic_ai"
    FULL_AI = "full_ai"
    ADMIN = "admin"


class AiAccessLevel(str, Enum):
    NONE = "none"
    LIGHT = "light"
    HEAVY = "heavy"


# Frozen sets for validation helpers (future billing imports).
PLAN_CODES: frozenset[str] = frozenset(m.value for m in PlanCode)
AI_ACCESS_LEVELS: frozenset[str] = frozenset(m.value for m in AiAccessLevel)


def normalize_plan_code(raw: str | None) -> PlanCode | None:
    """Return enum member if ``raw`` matches a canonical value, else ``None``."""
    if raw is None or raw == "":
        return None
    try:
        return PlanCode(raw.strip().lower())
    except ValueError:
        return None


def normalize_ai_access_level(raw: str | None) -> AiAccessLevel | None:
    """Return enum member if ``raw`` matches a canonical value, else ``None``."""
    if raw is None or raw == "":
        return None
    try:
        return AiAccessLevel(raw.strip().lower())
    except ValueError:
        return None
