from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Literal

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import resolve_gemini_rest_model_id, settings
from app.models.data_subscription import EntityDailyMetric, NormalizedNewsDocument
from app.models.entity_sentiment_baseline import EntitySentimentBaseline
from app.services.ai.router import get_provider_for_role
from app.services.cache_fallback import utcnow

logger = logging.getLogger(__name__)


PeriodKey = Literal["1M", "3M", "6M", "1Y", "MAX"]


def _period_days(period: str) -> int:
    p = (period or "3M").strip().upper()
    if p in {"1M", "30D"}:
        return 30
    if p in {"6M"}:
        return 180
    if p in {"1Y", "MAX"}:
        return 365
    return 90  # 3M default


def _bucket_step_days(window_days: int) -> int:
    # Keep AI calls bounded. For long ranges, compute weekly buckets.
    return 1 if window_days <= 120 else 7


def _day0_utc(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)


def _list_titles(db: Session, *, entity_id: uuid.UUID, start: datetime, end: datetime, limit: int) -> list[str]:
    rows = db.execute(
        select(NormalizedNewsDocument.normalized_title)
        .where(
            NormalizedNewsDocument.entity_id == entity_id,
            NormalizedNewsDocument.published_at.isnot(None),
            NormalizedNewsDocument.published_at >= start,
            NormalizedNewsDocument.published_at < end,
        )
        .order_by(NormalizedNewsDocument.published_at.desc())
        .limit(int(limit))
    ).all()
    out: list[str] = []
    for (t,) in rows:
        s = (t or "").strip()
        if s and s not in out:
            out.append(s)
    return out


@dataclass(frozen=True)
class SentimentPoint:
    t: str  # YYYY-MM-DD bucket end date
    sentiment_score: float  # -1..+1 (delta vs baseline)
    sentiment_label: Literal["bullish", "bearish", "neutral"]
    confidence: float | None


def _clamp_label(score: float) -> Literal["bullish", "bearish", "neutral"]:
    if score >= 0.15:
        return "bullish"
    if score <= -0.15:
        return "bearish"
    return "neutral"


def _llm_kind() -> Literal["gemini", "openai", "none"]:
    # Mirror router preference for "analysis" role (Gemini preferred).
    if (settings.gemini_api_key or "").strip():
        return "gemini"
    if (settings.openai_api_key or "").strip():
        return "openai"
    return "none"


def _call_llm_json(prompt: str) -> dict[str, Any]:
    kind = _llm_kind()
    if kind == "none":
        raise RuntimeError("no_ai_provider_configured")
    if kind == "openai":
        url = "https://api.openai.com/v1/chat/completions"
        payload = {
            "model": settings.openai_model,
            "temperature": 0.2,
            "messages": [
                {
                    "role": "system",
                    "content": "You output STRICT JSON only (no markdown, no prose).",
                },
                {"role": "user", "content": prompt[:12000]},
            ],
        }
        headers = {"Authorization": f"Bearer {settings.openai_api_key}"}
        with httpx.Client(timeout=45) as client:
            r = client.post(url, json=payload, headers=headers)
            r.raise_for_status()
            content = r.json()["choices"][0]["message"]["content"]
        return json.loads(content)

    # gemini
    model = resolve_gemini_rest_model_id(settings.gemini_model)
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    payload = {"contents": [{"parts": [{"text": prompt[:12000]}]}], "generationConfig": {"temperature": 0.2}}
    with httpx.Client(timeout=45) as client:
        r = client.post(url, params={"key": settings.gemini_api_key}, json=payload)
        r.raise_for_status()
        out_text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
    return json.loads(out_text)


def _baseline_cached_or_compute(
    db: Session,
    *,
    entity_id: uuid.UUID,
    baseline_start_day: date,
    baseline_end_day: date,
    bucket_step_days: int,
    titles_limit: int,
    max_age_hours: int = 24,
) -> tuple[float, str, float | None, str | None]:
    now = utcnow()
    row = db.scalar(
        select(EntitySentimentBaseline).where(
            EntitySentimentBaseline.entity_id == entity_id,
            EntitySentimentBaseline.window_start == baseline_start_day,
            EntitySentimentBaseline.window_end == baseline_end_day,
            EntitySentimentBaseline.bucket_step_days == bucket_step_days,
        )
    )
    if row and row.computed_at and (now - row.computed_at) <= timedelta(hours=max_age_hours):
        return float(row.baseline_score), str(row.baseline_label), float(row.confidence) if row.confidence is not None else None, "cache_hit"

    baseline_titles = _list_titles(
        db,
        entity_id=entity_id,
        start=_day0_utc(baseline_start_day),
        end=_day0_utc(baseline_end_day),
        limit=titles_limit,
    )
    if len(baseline_titles) < 6:
        raise ValueError("insufficient_baseline_news")

    prompt = (
        "Compute ABSOLUTE narrative tone for the BASELINE window.\n"
        "Output STRICT JSON only.\n"
        "Schema: {baseline_score: number (-1..1), confidence: number (0..100)}\n"
        "Guidance: baseline_score reflects overall tone/intensity/stance of the language.\n\n"
        "BASELINE HEADLINES:\n" + "\n".join(f"- {t}" for t in baseline_titles[:titles_limit])
    )
    data = _call_llm_json(prompt)
    bs = max(-1.0, min(1.0, float(data.get("baseline_score"))))
    conf = data.get("confidence")
    conf_f = None
    if conf is not None:
        try:
            conf_f = max(0.0, min(100.0, float(conf)))
        except Exception:
            conf_f = None
    label = _clamp_label(bs)

    provider = get_provider_for_role("analysis")
    provider_name = getattr(provider, "provider", "unknown")
    model = getattr(provider, "model", "v1")
    if row is None:
        row = EntitySentimentBaseline(
            entity_id=entity_id,
            window_start=baseline_start_day,
            window_end=baseline_end_day,
            bucket_step_days=bucket_step_days,
            baseline_score=bs,
            baseline_label=label,
            confidence=conf_f,
            provider=str(provider_name),
            model=str(model),
            computed_at=now,
        )
        db.add(row)
    else:
        row.baseline_score = bs
        row.baseline_label = label
        row.confidence = conf_f
        row.provider = str(provider_name)
        row.model = str(model)
        row.computed_at = now

    return bs, label, conf_f, "computed"


def _bucket_dates(start_day: date, end_day: date, step_days: int) -> list[date]:
    out: list[date] = []
    cursor = start_day
    while cursor < end_day:
        out.append(cursor + timedelta(days=step_days - 1))
        cursor = cursor + timedelta(days=step_days)
    return out


def _read_cached_bucket_points(
    db: Session,
    *,
    entity_id: uuid.UUID,
    bucket_days: list[date],
    bucket_step_days: int,
    max_age_hours: int = 24,
) -> dict[str, SentimentPoint]:
    if not bucket_days:
        return {}
    now = utcnow()
    rows = db.scalars(
        select(EntityDailyMetric).where(
            EntityDailyMetric.entity_id == entity_id,
            EntityDailyMetric.metric_date.in_(bucket_days),
            EntityDailyMetric.sentiment_score.isnot(None),
        )
    ).all()
    out: dict[str, SentimentPoint] = {}
    for r in rows:
        ex = r.extra or {}
        if int(ex.get("bucket_step_days") or 0) != int(bucket_step_days):
            continue
        computed_at_s = ex.get("computed_at")
        if computed_at_s:
            try:
                dt = datetime.fromisoformat(str(computed_at_s).replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                if (now - dt.astimezone(timezone.utc)) > timedelta(hours=max_age_hours):
                    continue
            except Exception:
                continue
        label = str(ex.get("sentiment_label") or "").strip().lower()
        if label not in {"bullish", "bearish", "neutral"}:
            continue
        conf = ex.get("confidence")
        conf_f = None
        if conf is not None:
            try:
                conf_f = max(0.0, min(100.0, float(conf)))
            except Exception:
                conf_f = None
        k = r.metric_date.isoformat()
        out[k] = SentimentPoint(
            t=k,
            sentiment_score=float(r.sentiment_score),
            sentiment_label=label,  # type: ignore[assignment]
            confidence=conf_f,
        )
    return out


def compute_sentiment_series_delta(
    db: Session,
    *,
    entity_id: uuid.UUID,
    period: str,
    min_bucket_docs: int = 2,
    baseline_titles_limit: int = 120,
    bucket_titles_limit: int = 40,
    max_inline_llm_calls: int = 10,
    buckets_per_call: int = 8,
) -> tuple[list[SentimentPoint], str | None, dict[str, Any]]:
    """
    AI-backed sentiment series:
    - For each bucket within selected window, compare bucket language vs prior equal-length baseline window.
    - Uses normalized_news_documents titles as corpus (stable, deduped).
    - Returns per-bucket delta sentiment in [-1, +1].
    """
    window_days = min(365, _period_days(period))  # hard clamp to 1Y
    step_days = _bucket_step_days(window_days)

    now = utcnow()
    end_day = now.date()
    start_day = end_day - timedelta(days=window_days)
    baseline_start_day = start_day - timedelta(days=window_days)
    baseline_end_day = start_day

    baseline_start = _day0_utc(baseline_start_day)
    baseline_end = _day0_utc(baseline_end_day)

    provider = get_provider_for_role("analysis")
    provider_name = str(getattr(provider, "provider", "unknown"))
    model = str(getattr(provider, "model", "v1"))
    if provider_name.strip().lower() == "heuristic":
        return [], "no_ai_provider_configured", {"computed": 0, "reused": 0, "llm_calls": 0}

    # Baseline cache (absolute tone)
    try:
        baseline_abs, _blabel, _bconf, baseline_mode = _baseline_cached_or_compute(
            db,
            entity_id=entity_id,
            baseline_start_day=baseline_start_day,
            baseline_end_day=baseline_end_day,
            bucket_step_days=step_days,
            titles_limit=baseline_titles_limit,
        )
    except ValueError:
        return [], "insufficient_baseline_news", {"computed": 0, "reused": 0, "llm_calls": 0}
    except RuntimeError:
        return [], "no_ai_provider_configured", {"computed": 0, "reused": 0, "llm_calls": 0}

    bucket_days = _bucket_dates(start_day, end_day, step_days)
    cached = _read_cached_bucket_points(db, entity_id=entity_id, bucket_days=bucket_days, bucket_step_days=step_days)

    missing_days = [d for d in bucket_days if d.isoformat() not in cached]
    llm_calls = 0
    computed = 0

    # Build missing buckets' headline payloads once.
    missing_payload: list[dict[str, Any]] = []
    for d in missing_days:
        bucket_end_day = d
        bucket_start_day = bucket_end_day - timedelta(days=step_days - 1)
        titles = _list_titles(
            db,
            entity_id=entity_id,
            start=_day0_utc(bucket_start_day),
            end=_day0_utc(bucket_end_day + timedelta(days=1)),
            limit=bucket_titles_limit,
        )
        if len(titles) < min_bucket_docs:
            continue
        missing_payload.append(
            {
                "t": bucket_end_day.isoformat(),
                "bucket_start": bucket_start_day.isoformat(),
                "bucket_end": (bucket_end_day + timedelta(days=1)).isoformat(),
                "headlines": titles[:bucket_titles_limit],
            }
        )

    # Batch buckets per call; cap total calls per request.
    batched: list[list[dict[str, Any]]] = []
    for i in range(0, len(missing_payload), int(buckets_per_call)):
        batched.append(missing_payload[i : i + int(buckets_per_call)])

    max_batches = max(0, int(max_inline_llm_calls) - (0 if baseline_mode == "cache_hit" else 1))
    batched = batched[:max_batches]

    now = utcnow()
    for batch in batched:
        prompt = (
            "Compute ABSOLUTE narrative tone for each bucket.\n"
            "Output STRICT JSON only.\n"
            "Schema: {buckets: [{t:'YYYY-MM-DD', abs_score:number(-1..1), confidence:number(0..100)}]}.\n"
            "Do not include any other keys.\n\n"
            "BUCKETS:\n"
            + "\n".join(
                [
                    f"t={b['t']}\n" + "\n".join(f"- {h}" for h in (b.get("headlines") or []))
                    for b in batch
                ]
            )
        )
        try:
            data = _call_llm_json(prompt)
        except Exception:
            return [], "ai_provider_failed", {"computed": computed, "reused": len(cached), "llm_calls": llm_calls}
        llm_calls += 1
        out_list = data.get("buckets")
        if not isinstance(out_list, list):
            return [], "ai_provider_failed", {"computed": computed, "reused": len(cached), "llm_calls": llm_calls}

        by_t: dict[str, dict[str, Any]] = {}
        for item in out_list:
            if isinstance(item, dict) and isinstance(item.get("t"), str):
                by_t[item["t"]] = item

        for b in batch:
            t = str(b["t"])
            it = by_t.get(t)
            if not it:
                continue
            try:
                abs_score = max(-1.0, min(1.0, float(it.get("abs_score"))))
            except Exception:
                continue
            delta = max(-1.0, min(1.0, abs_score - float(baseline_abs)))
            label = _clamp_label(delta)
            conf_f = None
            if it.get("confidence") is not None:
                try:
                    conf_f = max(0.0, min(100.0, float(it.get("confidence"))))
                except Exception:
                    conf_f = None

            metric_day = date.fromisoformat(t)
            row = db.scalar(
                select(EntityDailyMetric).where(
                    EntityDailyMetric.entity_id == entity_id,
                    EntityDailyMetric.metric_date == metric_day,
                )
            )
            extra = {
                "sentiment_label": label,
                "confidence": conf_f,
                "bucket_step_days": step_days,
                "bucket_start": b["bucket_start"],
                "bucket_end": b["bucket_end"],
                "baseline_start": baseline_start_day.isoformat(),
                "baseline_end": baseline_end_day.isoformat(),
                "baseline_score_abs": float(baseline_abs),
                "abs_score": abs_score,
                "provider": provider_name,
                "model": model,
                "computed_at": now.isoformat(),
            }
            if row is None:
                db.add(
                    EntityDailyMetric(
                        entity_id=entity_id,
                        metric_date=metric_day,
                        search_trend=None,
                        coverage_volume=None,
                        sentiment_score=float(delta),
                        coverage_volume_source=None,
                        search_trend_source=None,
                        last_success_at=now,
                        last_error=None,
                        is_stale=False,
                        extra=extra,
                    )
                )
            else:
                row.sentiment_score = float(delta)
                row.last_success_at = now
                row.last_error = None
                row.is_stale = False
                row.extra = {**(row.extra or {}), **extra}

            cached[t] = SentimentPoint(
                t=t,
                sentiment_score=float(delta),
                sentiment_label=label,
                confidence=conf_f,
            )
            computed += 1

    # Return ordered series for requested window.
    points = [cached[d.isoformat()] for d in bucket_days if d.isoformat() in cached]
    if not points:
        return [], "insufficient_bucket_news", {"computed": computed, "reused": len(cached) - computed, "llm_calls": llm_calls}
    return points, None, {"computed": computed, "reused": len(points) - computed, "llm_calls": llm_calls, "bucket_step_days": step_days}


def read_cached_sentiment_series(
    db: Session,
    *,
    entity_id: uuid.UUID,
    period: str,
    max_age_hours: int = 24,
) -> tuple[list[SentimentPoint], int, bool, int]:
    """
    Read cached per-bucket sentiment for the requested range without performing any AI calls.
    Returns (points, missing_count, baseline_cached, bucket_step_days).
    """
    window_days = min(365, _period_days(period))
    step_days = _bucket_step_days(window_days)
    now = utcnow().date()
    end_day = now
    start_day = end_day - timedelta(days=window_days)
    baseline_start_day = start_day - timedelta(days=window_days)
    baseline_end_day = start_day

    baseline_row = db.scalar(
        select(EntitySentimentBaseline.id).where(
            EntitySentimentBaseline.entity_id == entity_id,
            EntitySentimentBaseline.window_start == baseline_start_day,
            EntitySentimentBaseline.window_end == baseline_end_day,
            EntitySentimentBaseline.bucket_step_days == step_days,
        )
    )
    baseline_cached = bool(baseline_row)

    bucket_days = _bucket_dates(start_day, end_day, step_days)
    cached = _read_cached_bucket_points(db, entity_id=entity_id, bucket_days=bucket_days, bucket_step_days=step_days, max_age_hours=max_age_hours)
    points = [cached[d.isoformat()] for d in bucket_days if d.isoformat() in cached]
    missing = len([d for d in bucket_days if d.isoformat() not in cached])
    return points, missing, baseline_cached, step_days

