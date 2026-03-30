"""
Paid / token-costing AI feature identifiers and HTTP messaging.

Gating is implemented in ``app.core.feature_access`` (tiers, ``can_access_feature``).
This module keeps stable constants and a backward-compatible ``can_use_paid_ai`` helper
for **HEAVY_AI** workflows (document LLM + AI schedule bundle — same rule today for all).

**Inventory — features treated as AI / token-costing (gated):**
- ``POST /api/ai/keyword-suggestions`` — ``FeatureKey.KEYWORD_SUGGESTIONS`` (LIGHT_AI)
- ``POST /api/entities/{id}/price-timeline/ai-summary`` — ``FeatureKey.TIMELINE_AI_SUMMARY`` (LIGHT_AI)
- ``analyze_documents`` — ``FeatureKey.DOCUMENT_LLM_ANALYSIS`` (HEAVY_AI)
- Schedule types ``ai_alert``, ``ai_report``, ``general_alert`` — HEAVY_AI keys in ``feature_access``

**Not gated (non-LLM / heuristic):**
- ``analyze_documents_for_group`` — keyword/sentiment heuristics only
- Timeline placeholders without LLM in-window

For policy and migration notes see ``docs/admin_only_ai_gating.md`` and
``docs/feature_access_and_tiers.md``.
"""

from __future__ import annotations

from app.core.feature_access import (
    AI_SCHEDULE_TYPES,
    FeatureKey,
    can_access_feature,
)
from app.models.user import User

# Re-export for callers that imported from ai_access.
__all__ = (
    "AI_FEATURES_FORBIDDEN_DETAIL",
    "AI_BACKGROUND_SKIP_PREFIX",
    "AI_BACKGROUND_SKIP_DETAIL",
    "AI_RUN_SKIP_REASON_CODE",
    "AI_SCHEDULE_TYPES",
    "can_use_paid_ai",
    "FeatureKey",
    "can_access_feature",
)

# Single user-facing message for HTTP 403 from AI-gated routes (and same wording in logs/skip reasons).
AI_FEATURES_FORBIDDEN_DETAIL = "AI features are currently available to admin only."

# Celery / MonitoringRun.detail / pipeline return dicts — explicit operator-facing skip line (includes HTTP message).
AI_BACKGROUND_SKIP_PREFIX = "Skipped:"
AI_BACKGROUND_SKIP_DETAIL = f"{AI_BACKGROUND_SKIP_PREFIX} {AI_FEATURES_FORBIDDEN_DETAIL}"

# Stable machine-readable key for API responses and worker return payloads (not shown to end users).
AI_RUN_SKIP_REASON_CODE = "ai_requires_admin"


def can_use_paid_ai(user: User) -> bool:
    """
    True if the user may run HEAVY_AI document LLM analysis (aggregate check used by legacy call sites).

    Schedule and per-feature checks should prefer ``can_access_feature`` with the appropriate
    ``FeatureKey``; today all HEAVY_AI features share the same allow/deny rule as this helper.
    """

    return can_access_feature(user, FeatureKey.DOCUMENT_LLM_ANALYSIS)
