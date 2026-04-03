"""Plan + ai_access_level gates for non-admin AI features."""

import uuid

import pytest

from app.core.feature_access import FeatureKey, FeatureTier, _non_admin_ai_entitled, can_access_feature, get_feature_tier
from app.core.plan_entitlements import AiAccessLevel, PlanCode
from app.models.user import User


def _user(plan: str, level: str) -> User:
    return User(
        id=uuid.uuid4(),
        email=f"u-{uuid.uuid4().hex[:8]}@t.test",
        username=f"t{uuid.uuid4().hex[:6]}",
        password_hash="x",
        plan_code=plan,
        ai_access_level=level,
    )


def test_get_feature_tier_entity_sentiment_ai_is_light():
    assert get_feature_tier(FeatureKey.ENTITY_SENTIMENT_AI) == FeatureTier.LIGHT_AI


def test_non_admin_basic_ai_light_gets_light_ai():
    u = _user(PlanCode.BASIC_AI.value, AiAccessLevel.LIGHT.value)
    assert _non_admin_ai_entitled(u, FeatureTier.LIGHT_AI) is True
    assert _non_admin_ai_entitled(u, FeatureTier.HEAVY_AI) is False


def test_non_admin_full_ai_light_gets_light_only():
    u = _user(PlanCode.FULL_AI.value, AiAccessLevel.LIGHT.value)
    assert _non_admin_ai_entitled(u, FeatureTier.LIGHT_AI) is True
    assert _non_admin_ai_entitled(u, FeatureTier.HEAVY_AI) is False


def test_non_admin_full_ai_heavy_gets_both():
    u = _user(PlanCode.FULL_AI.value, AiAccessLevel.HEAVY.value)
    assert _non_admin_ai_entitled(u, FeatureTier.LIGHT_AI) is True
    assert _non_admin_ai_entitled(u, FeatureTier.HEAVY_AI) is True


def test_non_admin_free_denied_ai():
    u = _user(PlanCode.FREE.value, AiAccessLevel.NONE.value)
    assert _non_admin_ai_entitled(u, FeatureTier.LIGHT_AI) is False


def test_can_access_feature_light_with_basic_ai():
    u = _user(PlanCode.BASIC_AI.value, AiAccessLevel.LIGHT.value)
    assert can_access_feature(u, FeatureKey.ENTITY_SENTIMENT_AI) is True


def test_can_access_feature_heavy_document_needs_full_heavy():
    u = _user(PlanCode.BASIC_AI.value, AiAccessLevel.LIGHT.value)
    assert can_access_feature(u, FeatureKey.DOCUMENT_LLM_ANALYSIS) is False
    u2 = _user(PlanCode.FULL_AI.value, AiAccessLevel.HEAVY.value)
    assert can_access_feature(u2, FeatureKey.DOCUMENT_LLM_ANALYSIS) is True
