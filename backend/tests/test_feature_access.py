from __future__ import annotations

import uuid

import pytest

from app.core.feature_access import (
    AI_SCHEDULE_TYPES,
    FEATURE_TIER_MAP,
    FeatureKey,
    FeatureTier,
    can_access_feature,
    feature_key_for_schedule_type,
    get_feature_tier,
)
from app.core.ai_access import AI_FEATURES_FORBIDDEN_DETAIL
from app.models.monitoring import SCHEDULE_TYPES
from app.core.plan_entitlements import AiAccessLevel, PlanCode
from app.models.user import User


def _user(*, is_admin: bool) -> User:
    return User(
        id=uuid.uuid4(),
        username=f"u_{uuid.uuid4().hex[:8]}",
        email=f"{uuid.uuid4().hex[:8]}@t.example",
        password_hash="x",
        credits_balance=10_000,
        plan_code=PlanCode.FREE.value,
        ai_access_level=AiAccessLevel.NONE.value,
        paid_access=True,
        is_admin=is_admin,
        token_version=0,
        profile_name="",
    )


def test_get_feature_tier_light_and_heavy() -> None:
    assert get_feature_tier(FeatureKey.KEYWORD_SUGGESTIONS) is FeatureTier.LIGHT_AI
    assert get_feature_tier(FeatureKey.TIMELINE_AI_SUMMARY) is FeatureTier.LIGHT_AI
    assert get_feature_tier(FeatureKey.DOCUMENT_LLM_ANALYSIS) is FeatureTier.HEAVY_AI


def test_get_feature_tier_unknown_raises() -> None:
    with pytest.raises(KeyError):
        get_feature_tier("not_a_registered_feature")


def test_non_admin_free_features_allowed() -> None:
    u = _user(is_admin=False)
    assert can_access_feature(u, FeatureKey.DASHBOARDS) is True
    assert can_access_feature(u, FeatureKey.STANDARD_MONITOR) is True


def test_non_admin_light_and_heavy_denied() -> None:
    u = _user(is_admin=False)
    assert can_access_feature(u, FeatureKey.KEYWORD_SUGGESTIONS) is False
    assert can_access_feature(u, FeatureKey.TIMELINE_AI_SUMMARY) is False
    assert can_access_feature(u, FeatureKey.DOCUMENT_LLM_ANALYSIS) is False
    assert can_access_feature(u, FeatureKey.SCHEDULE_AI_ALERT) is False


def test_admin_all_tiers_allowed() -> None:
    u = _user(is_admin=True)
    assert can_access_feature(u, FeatureKey.DASHBOARDS) is True
    assert can_access_feature(u, FeatureKey.KEYWORD_SUGGESTIONS) is True
    assert can_access_feature(u, FeatureKey.DOCUMENT_LLM_ANALYSIS) is True


def test_schedule_type_feature_keys() -> None:
    assert feature_key_for_schedule_type("ai_alert") == FeatureKey.SCHEDULE_AI_ALERT
    assert feature_key_for_schedule_type("ai_report") == FeatureKey.SCHEDULE_AI_REPORT
    assert feature_key_for_schedule_type("general_alert") == FeatureKey.SCHEDULE_GENERAL_ALERT
    with pytest.raises(KeyError):
        feature_key_for_schedule_type("standard_monitor")


def test_ai_schedule_types_subset_of_schedule_types() -> None:
    for st in AI_SCHEDULE_TYPES:
        assert st in SCHEDULE_TYPES


def test_feature_tier_map_covers_all_feature_keys() -> None:
    for name in (
        FeatureKey.STANDARD_MONITOR,
        FeatureKey.DASHBOARDS,
        FeatureKey.CHARTS,
        FeatureKey.KEYWORD_GROUPS,
        FeatureKey.PORTFOLIOS,
        FeatureKey.ENTITIES,
        FeatureKey.MACRO_DATA,
        FeatureKey.ENTITY_DATA,
        FeatureKey.HEURISTIC_ANALYSIS,
        FeatureKey.REPORTS_NON_LLM,
        FeatureKey.COMMUNITY_FEED,
        FeatureKey.RSS_INGEST,
        FeatureKey.RESEARCH_WORKSPACE,
        FeatureKey.KEYWORD_SUGGESTIONS,
        FeatureKey.TIMELINE_AI_SUMMARY,
        FeatureKey.DOCUMENT_LLM_ANALYSIS,
        FeatureKey.SCHEDULE_AI_ALERT,
        FeatureKey.SCHEDULE_AI_REPORT,
        FeatureKey.SCHEDULE_GENERAL_ALERT,
    ):
        assert name in FEATURE_TIER_MAP


def test_ai_forbidden_detail_stable_for_http() -> None:
    assert AI_FEATURES_FORBIDDEN_DETAIL == "AI features are currently available to admin only."
