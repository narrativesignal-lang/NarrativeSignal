"""OpenAI-compatible chat for entity chart explanations (stored context only; Massive is not used)."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.data_subscription import EntityDailyMetric, NormalizedNewsDocument, OhlcvSnapshot
from app.models.massive_ai_cache import MassiveAiExplanationCache
from app.models.portfolio import PortfolioEntity
from app.schemas.ai_structured import PriceMoveDriver, PriceMoveExplanationOut, RangeSummaryOut

logger = logging.getLogger(__name__)

FEATURE_PRICE_MOVE = "price_move_explanation"
FEATURE_RANGE_SUMMARY = "range_summary"
CACHE_TTL = timedelta(hours=1)
MAX_WINDOW_DAYS = 400
_MAX_NEWS = 36
_LLM_TIMEOUT = 75.0


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _fingerprint(
    *,
    entity_id: uuid.UUID,
    feature: str,
    window_start: datetime,
    window_end: datetime,
    chart_period: str,
    symbol: str,
    metric_touch: str | None,
    news_sig: str,
    ohlcv_sig: str | None,
) -> str:
    blob = json.dumps(
        {
            "e": str(entity_id),
            "f": feature,
            "ws": _ensure_aware(window_start).isoformat(),
            "we": _ensure_aware(window_end).isoformat(),
            "p": chart_period,
            "s": symbol,
            "m": metric_touch or "",
            "n": news_sig,
            "o": ohlcv_sig or "",
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:64]


def _strip_json_fence(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z0-9]*\s*", "", t)
        t = re.sub(r"\s*```$", "", t).strip()
    return t


def _get_entity_for_user(db: Session, entity_id: uuid.UUID, user_id: uuid.UUID) -> PortfolioEntity | None:
    return db.scalar(select(PortfolioEntity).where(PortfolioEntity.id == entity_id, PortfolioEntity.user_id == user_id))


def _load_ohlcv_bars(db: Session, symbol: str, chart_period: str) -> tuple[list[dict[str, Any]], str | None]:
    key = f"{symbol}:{chart_period}"
    snap = db.get(OhlcvSnapshot, key)
    if not snap or not snap.bars:
        return [], None
    bars = (snap.bars or {}).get("bars") or []
    if not isinstance(bars, list):
        return [], None
    sig = (snap.last_success_at or snap.last_attempt_at or _utcnow()).isoformat() if snap else None
    return bars, sig


def _bars_in_window(bars: list[dict[str, Any]], ws: datetime, we: datetime) -> list[dict[str, Any]]:
    ws_u = int(_ensure_aware(ws).timestamp())
    we_u = int(_ensure_aware(we).timestamp())
    out: list[dict[str, Any]] = []
    for b in bars:
        if not isinstance(b, dict):
            continue
        t = b.get("time")
        if t is None:
            continue
        try:
            tu = int(t)
        except (TypeError, ValueError):
            continue
        if ws_u <= tu <= we_u:
            out.append(b)
    out.sort(key=lambda x: int(x.get("time") or 0))
    return out


def _price_context(bars: list[dict[str, Any]]) -> dict[str, Any]:
    if not bars:
        return {"error": "no_bars_in_window"}
    closes = [float(b["close"]) for b in bars if b.get("close") is not None]
    if len(closes) < 2:
        return {"first_close": closes[0] if closes else None, "last_close": closes[-1] if closes else None, "bars": len(bars)}
    rets: list[float] = []
    for i in range(1, len(closes)):
        if closes[i - 1]:
            rets.append((closes[i] - closes[i - 1]) / closes[i - 1] * 100.0)
    max_idx = max(range(len(rets)), key=lambda i: abs(rets[i])) if rets else 0
    return {
        "bars_in_window": len(bars),
        "first_close": closes[0],
        "last_close": closes[-1],
        "total_return_pct": (closes[-1] - closes[0]) / closes[0] * 100.0 if closes[0] else None,
        "max_abs_1bar_move_pct": max((abs(r) for r in rets), default=0.0),
        "max_1bar_move_pct": rets[max_idx] if rets else None,
    }


def _metrics_slice(db: Session, entity_id: uuid.UUID, d0, d1) -> tuple[list[EntityDailyMetric], str | None]:
    q = (
        select(EntityDailyMetric)
        .where(
            EntityDailyMetric.entity_id == entity_id,
            EntityDailyMetric.metric_date >= d0,
            EntityDailyMetric.metric_date <= d1,
        )
        .order_by(EntityDailyMetric.metric_date.asc())
    )
    rows = list(db.scalars(q).all())
    touch: datetime | None = None
    for r in rows:
        for col in (r.updated_at, r.last_success_at, r.created_at):
            if col is not None:
                if touch is None or col > touch:
                    touch = col
    return rows, touch.isoformat() if touch else None


def _news_slice(db: Session, entity_id: uuid.UUID, ws: datetime, we: datetime) -> tuple[list[NormalizedNewsDocument], str]:
    pub = func.coalesce(NormalizedNewsDocument.published_at, NormalizedNewsDocument.created_at)
    q = (
        select(NormalizedNewsDocument)
        .where(
            NormalizedNewsDocument.entity_id == entity_id,
            pub >= _ensure_aware(ws),
            pub <= _ensure_aware(we),
        )
        .order_by(pub.desc())
        .limit(_MAX_NEWS)
    )
    rows = list(db.scalars(q).all())
    titles = [r.normalized_title[:200] for r in rows[:12]]
    sig = hashlib.sha256("|".join(titles).encode("utf-8", errors="ignore")).hexdigest()[:24]
    return rows, f"{len(rows)}:{sig}"


def _serialize_metrics(rows: list[EntityDailyMetric]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "date": r.metric_date.isoformat(),
                "target_search_volume": r.target_search_volume,
                "keywords_search_volume": r.keywords_search_volume,
                "coverage_volume": r.coverage_volume,
                "sentiment_score": r.sentiment_score,
            }
        )
    return out


def _read_cache(db: Session, entity_id: uuid.UUID, feature: str, fingerprint: str) -> dict[str, Any] | None:
    row = db.scalar(
        select(MassiveAiExplanationCache).where(
            MassiveAiExplanationCache.entity_id == entity_id,
            MassiveAiExplanationCache.feature_type == feature,
            MassiveAiExplanationCache.fingerprint == fingerprint,
        )
    )
    if not row or row.expires_at <= _utcnow():
        return None
    if isinstance(row.payload, dict):
        return row.payload
    return None


def _write_cache(
    db: Session,
    *,
    entity_id: uuid.UUID,
    feature: str,
    fingerprint: str,
    window_start: datetime,
    window_end: datetime,
    payload: dict[str, Any],
    model_label: str | None,
) -> None:
    now = _utcnow()
    row = db.scalar(
        select(MassiveAiExplanationCache).where(
            MassiveAiExplanationCache.entity_id == entity_id,
            MassiveAiExplanationCache.feature_type == feature,
            MassiveAiExplanationCache.fingerprint == fingerprint,
        )
    )
    if row is None:
        row = MassiveAiExplanationCache(
            entity_id=entity_id,
            feature_type=feature,
            fingerprint=fingerprint,
            window_start=_ensure_aware(window_start),
            window_end=_ensure_aware(window_end),
            payload=payload,
            expires_at=now + CACHE_TTL,
            model_label=model_label,
        )
        db.add(row)
    else:
        row.window_start = _ensure_aware(window_start)
        row.window_end = _ensure_aware(window_end)
        row.payload = payload
        row.expires_at = now + CACHE_TTL
        row.model_label = model_label
    db.commit()


def _call_chat_json(*, system: str, user: str) -> dict[str, Any]:
    url = (getattr(settings, "openai_chat_completions_url", None) or "").strip() or "https://api.openai.com/v1/chat/completions"
    key = (settings.openai_api_key or "").strip()
    if not key:
        raise RuntimeError("openai_api_key_not_configured")
    model = (settings.openai_model or "gpt-4.1-mini").strip()
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    body: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.25,
        "response_format": {"type": "json_object"},
    }
    with httpx.Client(timeout=_LLM_TIMEOUT) as client:
        r = client.post(url, headers=headers, json=body)
        r.raise_for_status()
        data = r.json()
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("llm_empty_choices")
    msg = (choices[0].get("message") or {}).get("content")
    if not isinstance(msg, str):
        raise RuntimeError("llm_no_content")
    raw = _strip_json_fence(msg)
    return json.loads(raw)


def _parse_price_move(obj: dict[str, Any], ws: datetime, we: datetime) -> PriceMoveExplanationOut:
    summary = str(obj.get("summary") or "").strip() or "No summary returned."
    drivers_raw = obj.get("drivers")
    drivers: list[PriceMoveDriver] = []
    if isinstance(drivers_raw, list):
        for item in drivers_raw[:10]:
            if not isinstance(item, dict):
                continue
            label = str(item.get("label") or "").strip()
            if not label:
                continue
            try:
                conf = float(item.get("confidence", 0.5))
            except (TypeError, ValueError):
                conf = 0.5
            conf = max(0.0, min(1.0, conf))
            et = str(item.get("evidence_type") or "price").strip().lower()
            if et not in ("news", "coverage", "search", "price"):
                et = "price"
            drivers.append(PriceMoveDriver(label=label[:400], confidence=conf, evidence_type=et))
    return PriceMoveExplanationOut(
        summary=summary[:4000],
        drivers=drivers,
        time_window_start=_ensure_aware(ws),
        time_window_end=_ensure_aware(we),
        cached=False,
    )


def _parse_range_summary(obj: dict[str, Any], ws: datetime, we: datetime) -> RangeSummaryOut:
    summary = str(obj.get("summary") or "").strip() or "No summary returned."
    narrative = str(obj.get("narrative") or "").strip() or summary
    hl_raw = obj.get("highlights")
    highlights: list[str] = []
    if isinstance(hl_raw, list):
        for x in hl_raw[:12]:
            if isinstance(x, str) and x.strip():
                highlights.append(x.strip()[:500])
    return RangeSummaryOut(
        summary=summary[:4000],
        narrative=narrative[:8000],
        highlights=highlights,
        time_window_start=_ensure_aware(ws),
        time_window_end=_ensure_aware(we),
        cached=False,
    )


def build_context_pack(
    db: Session,
    *,
    entity: PortfolioEntity,
    window_start: datetime,
    window_end: datetime,
    chart_period: str,
) -> dict[str, Any]:
    symbol = (entity.instrument.symbol if entity.instrument else "") or ""
    symbol = symbol.strip()
    ws = _ensure_aware(window_start)
    we = _ensure_aware(window_end)
    d0, d1 = ws.date(), we.date()
    bars_all, ohlcv_sig = _load_ohlcv_bars(db, symbol, chart_period) if symbol else ([], None)
    win_bars = _bars_in_window(bars_all, ws, we)
    metrics, m_touch = _metrics_slice(db, entity.id, d0, d1)
    news_rows, news_sig = _news_slice(db, entity.id, ws, we)
    news_titles = [{"title": r.normalized_title[:300], "source": r.source_channel} for r in news_rows[:20]]
    return {
        "entity_name": entity.name,
        "symbol": symbol,
        "chart_period": chart_period,
        "window": {"start": ws.isoformat(), "end": we.isoformat()},
        "price": _price_context(win_bars),
        "daily_metrics": _serialize_metrics(metrics),
        "news_headlines": news_titles,
        "_finger": {
            "metric_touch": m_touch,
            "news_sig": news_sig,
            "ohlcv_sig": ohlcv_sig,
        },
    }


def explain_price_move(
    db: Session,
    *,
    entity: PortfolioEntity,
    window_start: datetime,
    window_end: datetime,
    chart_period: str,
) -> PriceMoveExplanationOut:
    ws, we = _ensure_aware(window_start), _ensure_aware(window_end)
    if we <= ws:
        raise ValueError("window_end_must_be_after_start")
    if (we - ws).days > MAX_WINDOW_DAYS:
        raise ValueError("window_too_long")

    ctx = build_context_pack(db, entity=entity, window_start=ws, window_end=we, chart_period=chart_period)
    symbol = str(ctx.get("symbol") or "")
    fp_meta = ctx.pop("_finger", {}) or {}
    fp = _fingerprint(
        entity_id=entity.id,
        feature=FEATURE_PRICE_MOVE,
        window_start=ws,
        window_end=we,
        chart_period=chart_period,
        symbol=symbol,
        metric_touch=fp_meta.get("metric_touch"),
        news_sig=str(fp_meta.get("news_sig") or ""),
        ohlcv_sig=fp_meta.get("ohlcv_sig"),
    )

    cached = _read_cache(db, entity.id, FEATURE_PRICE_MOVE, fp)
    if cached:
        out = _parse_price_move(cached, ws, we)
        out.cached = True
        return out

    if ctx.get("price", {}).get("error") == "no_bars_in_window":
        raise ValueError("no_ohlcv_in_window")

    system = (
        "You explain price moves using ONLY the JSON context provided. "
        "Do not invent prices, volumes, or events. No buy/sell/hold or trading advice. "
        "Output STRICT JSON with keys: summary (string), drivers (array of {label, confidence 0-1, evidence_type}). "
        "evidence_type must be one of: news, coverage, search, price. "
        "Tie each driver to evidence_type; prefer news when headlines plausibly relate."
    )
    user = json.dumps(ctx, ensure_ascii=False)[:24000]
    raw = _call_chat_json(system=system, user=user)
    if not isinstance(raw, dict):
        raise RuntimeError("llm_bad_shape")
    out = _parse_price_move(raw, ws, we)
    _write_cache(
        db,
        entity_id=entity.id,
        feature=FEATURE_PRICE_MOVE,
        fingerprint=fp,
        window_start=ws,
        window_end=we,
        payload=out.model_dump(mode="json"),
        model_label=(settings.openai_model or "").strip() or None,
    )
    return out


def summarize_range(
    db: Session,
    *,
    entity: PortfolioEntity,
    window_start: datetime,
    window_end: datetime,
    chart_period: str,
) -> RangeSummaryOut:
    ws, we = _ensure_aware(window_start), _ensure_aware(window_end)
    if we <= ws:
        raise ValueError("window_end_must_be_after_start")
    if (we - ws).days > MAX_WINDOW_DAYS:
        raise ValueError("window_too_long")

    ctx = build_context_pack(db, entity=entity, window_start=ws, window_end=we, chart_period=chart_period)
    symbol = str(ctx.get("symbol") or "")
    fp_meta = ctx.pop("_finger", {}) or {}
    fp = _fingerprint(
        entity_id=entity.id,
        feature=FEATURE_RANGE_SUMMARY,
        window_start=ws,
        window_end=we,
        chart_period=chart_period,
        symbol=symbol,
        metric_touch=fp_meta.get("metric_touch"),
        news_sig=str(fp_meta.get("news_sig") or ""),
        ohlcv_sig=fp_meta.get("ohlcv_sig"),
    )

    cached = _read_cache(db, entity.id, FEATURE_RANGE_SUMMARY, fp)
    if cached:
        out = _parse_range_summary(cached, ws, we)
        out.cached = True
        return out

    # Range summary may use news + daily metrics even when OHLCV has no bars in-window.
    if ctx.get("price", {}).get("error") == "no_bars_in_window":
        ctx["price"] = {"note": "no_ohlcv_bars_in_window", "bars_in_window": 0}

    system = (
        "Summarize what happened in the time window using ONLY the JSON context. "
        "No trade recommendations. Do not fabricate data not present in context. "
        "Output STRICT JSON with keys: summary (string), narrative (string), highlights (string array, max 8 short items)."
    )
    user = json.dumps(ctx, ensure_ascii=False)[:24000]
    raw = _call_chat_json(system=system, user=user)
    if not isinstance(raw, dict):
        raise RuntimeError("llm_bad_shape")
    out = _parse_range_summary(raw, ws, we)
    _write_cache(
        db,
        entity_id=entity.id,
        feature=FEATURE_RANGE_SUMMARY,
        fingerprint=fp,
        window_start=ws,
        window_end=we,
        payload=out.model_dump(mode="json"),
        model_label=(settings.openai_model or "").strip() or None,
    )
    return out
