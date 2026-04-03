from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.system_runtime_flag import SystemRuntimeFlag

logger = logging.getLogger(__name__)


class RuntimeFlagKey:
    ENABLE_EXTERNAL_PROVIDERS = "ENABLE_EXTERNAL_PROVIDERS"
    ENABLE_TWELVE_QUOTES = "ENABLE_TWELVE_QUOTES"
    ENABLE_TWELVE_OHLCV = "ENABLE_TWELVE_OHLCV"
    ENABLE_YAHOO_QUOTES = "ENABLE_YAHOO_QUOTES"
    ENABLE_YAHOO_OHLCV = "ENABLE_YAHOO_OHLCV"
    ENABLE_STOOQ_FALLBACK = "ENABLE_STOOQ_FALLBACK"
    ENABLE_MASSIVE_BACKFILL = "ENABLE_MASSIVE_BACKFILL"
    ENABLE_MASSIVE_ANALYSIS = "ENABLE_MASSIVE_ANALYSIS"
    ENABLE_PYTRENDS = "ENABLE_PYTRENDS"
    ENABLE_FETCH_MACRO_NEWS = "ENABLE_FETCH_MACRO_NEWS"
    ENABLE_STARTUP_WARMUPS = "ENABLE_STARTUP_WARMUPS"

    # AI (default: OFF)
    ENABLE_AI_FEATURES = "ENABLE_AI_FEATURES"
    ENABLE_AI_KEYWORD_SUGGESTIONS = "ENABLE_AI_KEYWORD_SUGGESTIONS"
    ENABLE_AI_TIMELINE_SUMMARY = "ENABLE_AI_TIMELINE_SUMMARY"
    ENABLE_AI_RANGE_ANALYSIS = "ENABLE_AI_RANGE_ANALYSIS"
    ENABLE_AI_ENTITY_SUMMARY = "ENABLE_AI_ENTITY_SUMMARY"
    ENABLE_AI_REPORT_GENERATION = "ENABLE_AI_REPORT_GENERATION"
    ENABLE_AI_ALERTS = "ENABLE_AI_ALERTS"
    ENABLE_AI_DOCUMENT_ANALYSIS = "ENABLE_AI_DOCUMENT_ANALYSIS"
    ENABLE_AI_NEWS_SUMMARY = "ENABLE_AI_NEWS_SUMMARY"
    ENABLE_AI_SIMILAR_EVENT_ANALYSIS = "ENABLE_AI_SIMILAR_EVENT_ANALYSIS"
    ENABLE_AI_NARRATIVE_ANALYSIS = "ENABLE_AI_NARRATIVE_ANALYSIS"
    ENABLE_AI_PRICE_MOVE_EXPLANATION = "ENABLE_AI_PRICE_MOVE_EXPLANATION"
    ENABLE_AI_COMPARE_SUMMARY = "ENABLE_AI_COMPARE_SUMMARY"


DEFAULTS: dict[str, bool] = {
    RuntimeFlagKey.ENABLE_EXTERNAL_PROVIDERS: True,
    RuntimeFlagKey.ENABLE_TWELVE_QUOTES: True,
    RuntimeFlagKey.ENABLE_TWELVE_OHLCV: True,
    RuntimeFlagKey.ENABLE_YAHOO_QUOTES: True,
    RuntimeFlagKey.ENABLE_YAHOO_OHLCV: True,
    RuntimeFlagKey.ENABLE_STOOQ_FALLBACK: True,
    RuntimeFlagKey.ENABLE_MASSIVE_BACKFILL: True,
    RuntimeFlagKey.ENABLE_MASSIVE_ANALYSIS: True,
    RuntimeFlagKey.ENABLE_PYTRENDS: True,
    RuntimeFlagKey.ENABLE_FETCH_MACRO_NEWS: True,
    # env/config default for startup warmups already exists; runtime flag can override it.
    RuntimeFlagKey.ENABLE_STARTUP_WARMUPS: bool(getattr(settings, "enable_startup_warmups", False)),

    # AI defaults: all OFF
    RuntimeFlagKey.ENABLE_AI_FEATURES: False,
    RuntimeFlagKey.ENABLE_AI_KEYWORD_SUGGESTIONS: False,
    RuntimeFlagKey.ENABLE_AI_TIMELINE_SUMMARY: False,
    RuntimeFlagKey.ENABLE_AI_RANGE_ANALYSIS: False,
    RuntimeFlagKey.ENABLE_AI_ENTITY_SUMMARY: False,
    RuntimeFlagKey.ENABLE_AI_REPORT_GENERATION: False,
    RuntimeFlagKey.ENABLE_AI_ALERTS: False,
    RuntimeFlagKey.ENABLE_AI_DOCUMENT_ANALYSIS: False,
    RuntimeFlagKey.ENABLE_AI_NEWS_SUMMARY: False,
    RuntimeFlagKey.ENABLE_AI_SIMILAR_EVENT_ANALYSIS: False,
    RuntimeFlagKey.ENABLE_AI_NARRATIVE_ANALYSIS: False,
    RuntimeFlagKey.ENABLE_AI_PRICE_MOVE_EXPLANATION: False,
    RuntimeFlagKey.ENABLE_AI_COMPARE_SUMMARY: False,
}


@dataclass(frozen=True)
class RuntimeFlagsSnapshot:
    values: dict[str, bool]
    loaded_at: datetime


_CACHE: RuntimeFlagsSnapshot | None = None
_CACHE_TTL = timedelta(seconds=10)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def load_all_flags(db: Session, *, use_cache: bool = True) -> dict[str, bool]:
    global _CACHE
    now = _utcnow()
    if use_cache and _CACHE and (now - _CACHE.loaded_at) <= _CACHE_TTL:
        return dict(_CACHE.values)

    rows = db.execute(select(SystemRuntimeFlag)).scalars().all()
    vals: dict[str, bool] = dict(DEFAULTS)
    for r in rows:
        if not r.key:
            continue
        vals[str(r.key).strip().upper()] = bool(r.value_bool)
    _CACHE = RuntimeFlagsSnapshot(values=dict(vals), loaded_at=now)
    return vals


def get_flag(db: Session, key: str, *, default: bool | None = None) -> bool:
    k = (key or "").strip().upper()
    vals = load_all_flags(db)
    if k in vals:
        return bool(vals[k])
    if default is not None:
        return bool(default)
    return bool(DEFAULTS.get(k, False))


def external_providers_enabled(db: Session) -> bool:
    return get_flag(db, RuntimeFlagKey.ENABLE_EXTERNAL_PROVIDERS, default=True)


def provider_enabled(db: Session, key: str) -> bool:
    # total gate first
    if not external_providers_enabled(db):
        return False
    return get_flag(db, key, default=True)


def pytrends_enabled(db: Session) -> bool:
    """
    Google Trends (pytrends) is not a market-data provider; do not gate it behind
    ENABLE_EXTERNAL_PROVIDERS so narrative search metrics still sync when market APIs are off.
    """
    return get_flag(db, RuntimeFlagKey.ENABLE_PYTRENDS, default=True)


def ai_features_enabled(db: Session) -> bool:
    return get_flag(db, RuntimeFlagKey.ENABLE_AI_FEATURES, default=False)


def ai_feature_enabled(db: Session, key: str) -> bool:
    # total AI gate first
    if not ai_features_enabled(db):
        return False
    return get_flag(db, key, default=False)

