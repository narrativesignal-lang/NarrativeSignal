from __future__ import annotations

from app.core.plan_entitlements import (
    AiAccessLevel,
    PlanCode,
    normalize_ai_access_level,
    normalize_plan_code,
)


def test_plan_code_canonical_values() -> None:
    assert PlanCode.FREE.value == "free"
    assert PlanCode.BASIC_AI.value == "basic_ai"
    assert PlanCode.FULL_AI.value == "full_ai"
    assert PlanCode.ADMIN.value == "admin"


def test_ai_access_level_canonical_values() -> None:
    assert AiAccessLevel.NONE.value == "none"
    assert AiAccessLevel.LIGHT.value == "light"
    assert AiAccessLevel.HEAVY.value == "heavy"


def test_normalize_plan_code() -> None:
    assert normalize_plan_code("FREE") is PlanCode.FREE
    assert normalize_plan_code(" basic_ai ") is PlanCode.BASIC_AI
    assert normalize_plan_code("unknown") is None
    assert normalize_plan_code("") is None


def test_normalize_ai_access_level() -> None:
    assert normalize_ai_access_level("LIGHT") is AiAccessLevel.LIGHT
    assert normalize_ai_access_level("none") is AiAccessLevel.NONE
    assert normalize_ai_access_level("oops") is None
