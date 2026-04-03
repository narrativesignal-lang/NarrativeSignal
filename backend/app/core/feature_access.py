"""
Central feature tier model and access checks.

Product tiers (for documentation and future billing):
- FREE: core app surfaces without paid LLM.
- LIGHT_AI: lighter LLM usage (e.g. suggestions, short summaries).
- HEAVY_AI: document analysis, AI schedules, and other high-cost LLM workflows.

**Effective rule:** admins bypass all tier checks. Non-admins: FREE always;
LIGHT_AI / HEAVY_AI via ``plan_code`` + ``ai_access_level`` (see ``_non_admin_ai_entitled``).

See ``docs/feature_access_and_tiers.md`` for the feature map and billing hooks.
"""

from __future__ import annotations

from enum import Enum

from app.core.plan_entitlements import (
    AiAccessLevel,
    PlanCode,
    normalize_ai_access_level,
    normalize_plan_code,
)
from app.core.user_admin import user_is_admin
from app.models.user import User


class FeatureTier(str, Enum):
    FREE = "free"
    LIGHT_AI = "light_ai"
    HEAVY_AI = "heavy_ai"


class FeatureKey:
    """Stable string ids for ``FEATURE_TIER_MAP`` and ``can_access_feature``."""

    # --- FREE (core product; no paid LLM) ---
    STANDARD_MONITOR = "standard_monitor"
    DASHBOARDS = "dashboards"
    CHARTS = "charts"
    KEYWORD_GROUPS = "keyword_groups"
    PORTFOLIOS = "portfolios"
    ENTITIES = "entities"
    MACRO_DATA = "macro_data"
    ENTITY_DATA = "entity_data"
    HEURISTIC_ANALYSIS = "heuristic_analysis"
    REPORTS_NON_LLM = "reports_non_llm"
    COMMUNITY_FEED = "community_feed"
    RSS_INGEST = "rss_ingest"
    RESEARCH_WORKSPACE = "research_workspace"

    # --- LIGHT_AI ---
    KEYWORD_SUGGESTIONS = "keyword_suggestions"
    TIMELINE_AI_SUMMARY = "timeline_ai_summary"
    ENTITY_SENTIMENT_AI = "entity_sentiment_ai"
    PRICE_MOVE_EXPLANATION = "price_move_explanation"
    RANGE_SUMMARY = "range_summary"
    COMPARE_SUMMARY = "compare_summary"

    # --- HEAVY_AI ---
    DOCUMENT_LLM_ANALYSIS = "document_llm_analysis"
    SCHEDULE_AI_ALERT = "schedule_ai_alert"
    SCHEDULE_AI_REPORT = "schedule_ai_report"
    SCHEDULE_GENERAL_ALERT = "schedule_general_alert"


FEATURE_TIER_MAP: dict[str, FeatureTier] = {
    # FREE
    FeatureKey.STANDARD_MONITOR: FeatureTier.FREE,
    FeatureKey.DASHBOARDS: FeatureTier.FREE,
    FeatureKey.CHARTS: FeatureTier.FREE,
    FeatureKey.KEYWORD_GROUPS: FeatureTier.FREE,
    FeatureKey.PORTFOLIOS: FeatureTier.FREE,
    FeatureKey.ENTITIES: FeatureTier.FREE,
    FeatureKey.MACRO_DATA: FeatureTier.FREE,
    FeatureKey.ENTITY_DATA: FeatureTier.FREE,
    FeatureKey.HEURISTIC_ANALYSIS: FeatureTier.FREE,
    FeatureKey.REPORTS_NON_LLM: FeatureTier.FREE,
    FeatureKey.COMMUNITY_FEED: FeatureTier.FREE,
    FeatureKey.RSS_INGEST: FeatureTier.FREE,
    FeatureKey.RESEARCH_WORKSPACE: FeatureTier.FREE,
    # LIGHT_AI
    FeatureKey.KEYWORD_SUGGESTIONS: FeatureTier.LIGHT_AI,
    FeatureKey.TIMELINE_AI_SUMMARY: FeatureTier.LIGHT_AI,
    FeatureKey.ENTITY_SENTIMENT_AI: FeatureTier.LIGHT_AI,
    FeatureKey.PRICE_MOVE_EXPLANATION: FeatureTier.LIGHT_AI,
    FeatureKey.RANGE_SUMMARY: FeatureTier.LIGHT_AI,
    FeatureKey.COMPARE_SUMMARY: FeatureTier.LIGHT_AI,
    # HEAVY_AI
    FeatureKey.DOCUMENT_LLM_ANALYSIS: FeatureTier.HEAVY_AI,
    FeatureKey.SCHEDULE_AI_ALERT: FeatureTier.HEAVY_AI,
    FeatureKey.SCHEDULE_AI_REPORT: FeatureTier.HEAVY_AI,
    FeatureKey.SCHEDULE_GENERAL_ALERT: FeatureTier.HEAVY_AI,
}

SCHEDULE_TYPE_TO_FEATURE_KEY: dict[str, str] = {
    "ai_alert": FeatureKey.SCHEDULE_AI_ALERT,
    "ai_report": FeatureKey.SCHEDULE_AI_REPORT,
    "general_alert": FeatureKey.SCHEDULE_GENERAL_ALERT,
}

AI_SCHEDULE_TYPES: frozenset[str] = frozenset(SCHEDULE_TYPE_TO_FEATURE_KEY.keys())


def feature_key_for_schedule_type(schedule_type: str) -> str:
    """Resolve monitoring ``schedule_type`` string to a ``FeatureKey`` value."""
    key = SCHEDULE_TYPE_TO_FEATURE_KEY.get(schedule_type)
    if key is None:
        raise KeyError(f"Not an AI schedule type: {schedule_type!r}")
    return key


def get_feature_tier(feature_name: str) -> FeatureTier:
    """Return the tier for a registered feature. Unknown keys raise ``KeyError``."""
    return FEATURE_TIER_MAP[feature_name]


def _non_admin_ai_entitled(user: User, tier: FeatureTier) -> bool:
    """
    Non-admin: LIGHT_AI / HEAVY_AI from ``plan_code`` + ``ai_access_level``.

    - ``basic_ai`` + ``light`` → LIGHT_AI features only.
    - ``full_ai`` + ``light`` → LIGHT_AI features.
    - ``full_ai`` + ``heavy`` → LIGHT_AI and HEAVY_AI features.
    Other combinations → no AI (same as free).
    """
    plan = normalize_plan_code(getattr(user, "plan_code", None)) or PlanCode.FREE
    level = normalize_ai_access_level(getattr(user, "ai_access_level", None)) or AiAccessLevel.NONE

    if tier == FeatureTier.LIGHT_AI:
        if plan == PlanCode.BASIC_AI:
            return level == AiAccessLevel.LIGHT
        if plan == PlanCode.FULL_AI:
            return level in (AiAccessLevel.LIGHT, AiAccessLevel.HEAVY)
        return False

    if tier == FeatureTier.HEAVY_AI:
        return plan == PlanCode.FULL_AI and level == AiAccessLevel.HEAVY

    return False


def can_access_feature(user: User, feature_name: str) -> bool:
    """
    Central gate for a named feature. Admins always pass.

    Non-admins: FREE features allowed; LIGHT_AI and HEAVY_AI use
    ``_non_admin_ai_entitled`` (today: denied).
    """
    if user_is_admin(user):
        return True
    tier = get_feature_tier(feature_name)
    if tier == FeatureTier.FREE:
        return True
    return _non_admin_ai_entitled(user, tier)
