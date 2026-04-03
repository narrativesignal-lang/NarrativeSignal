"""AI endpoints (e.g. keyword suggestions). Coexists with existing routes."""

from __future__ import annotations

import json
import logging
import re

import httpx
from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import require_feature
from app.core.config import resolve_gemini_rest_model_id, settings
from app.core.feature_access import FeatureKey
from app.db.session import get_db
from app.models.portfolio import PortfolioEntity
from app.models.user import User
from app.schemas.portfolios import KeywordSuggestionRequest, KeywordSuggestionResponse
from app.schemas.ai_structured import (
    AiDisabledResponse,
    CompareSummaryOut,
    EntityChartWindowRequest,
    PriceMoveExplanationOut,
    RangeSummaryOut,
)
from app.services.massive_explanation_service import explain_price_move, summarize_range
from app.services.runtime_logs import append_runtime_log
from app.services.runtime_flags import RuntimeFlagKey, ai_feature_enabled
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

router = APIRouter()
logger = logging.getLogger(__name__)

MAX_KW = 8
_GEMINI_GENERATE_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


def _gemini_generate_url(model_id: str) -> str:
    mid = resolve_gemini_rest_model_id(model_id)
    return f"{_GEMINI_GENERATE_BASE}/{mid}:generateContent"


def _extract_text_from_gemini_body(data: dict) -> str | None:
    cands = data.get("candidates")
    if not cands:
        fb = data.get("promptFeedback")
        if fb:
            logger.warning("Gemini keyword-suggestions: empty candidates, promptFeedback=%s", fb)
        return None
    parts = (cands[0].get("content") or {}).get("parts") or []
    if not parts:
        return None
    t = parts[0].get("text")
    return t if isinstance(t, str) else None


def _strip_json_fence(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z0-9]*\s*", "", t)
        t = re.sub(r"\s*```$", "", t).strip()
    return t


def _parse_keywords_from_model_text(text: str) -> list[str] | None:
    raw = _strip_json_fence(text)
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if isinstance(obj, dict) and isinstance(obj.get("keywords"), list):
        kws = obj["keywords"]
    elif isinstance(obj, list):
        kws = obj
    else:
        return None
    out: list[str] = []
    for item in kws:
        if isinstance(item, str) and item.strip():
            out.append(item.strip())
        elif isinstance(item, (int, float)):
            out.append(str(item).strip())
    return out or None


def _parse_keywords_from_lines(text: str) -> list[str]:
    raw = [x.strip() for x in text.splitlines() if x.strip()]
    out: list[str] = []
    seen: set[str] = set()
    for line in raw:
        w = re.sub(r"^[\d]+[\).\s]+", "", line).strip()
        w = w.lstrip("-•* ").strip()
        if not w:
            continue
        low = w.lower()
        if low not in seen:
            seen.add(low)
            out.append(w)
    return out


def _context_terms_lower(payload: KeywordSuggestionRequest) -> set[str]:
    terms: set[str] = set()
    for attr in ("idea", "instrument", "asset_class", "portfolio"):
        v = getattr(payload, attr, None)
        if v is None:
            continue
        s = str(v).strip()
        if s:
            terms.add(s.lower())
    return terms


def _expand_forbidden_tokens(forbidden_phrases: set[str], idea: str) -> set[str]:
    """Exact phrase matches plus significant tokens from the idea (avoid echoing user wording)."""
    out = set(forbidden_phrases)
    for w in re.findall(r"[a-zA-Z0-9]+", idea.lower()):
        if len(w) >= 3:
            out.add(w)
    return out


_MAX_PHRASE_LEN = 48


def _flatten_keyword_strings(items: list[str]) -> list[str]:
    """Split comma/semicolon lumps from the model into separate short phrases."""
    flat: list[str] = []
    for item in items:
        if not isinstance(item, str):
            continue
        for chunk in re.split(r"[,;]", item):
            c = " ".join(chunk.split()).strip()
            if c:
                flat.append(c)
    return flat


def _cleanup_keyword_candidate(s: str) -> str | None:
    x = " ".join(s.split()).strip()
    x = x.strip(" \"'`")
    if re.match(r"^\d+[\.\)]\s+", x):
        return None
    x = re.sub(r"^[\-\*•\u2022]+\s*", "", x).strip()
    if not x or len(x) > _MAX_PHRASE_LEN:
        return None
    if any(ch in x for ch in "\n\r"):
        return None
    return x


def _finalize_keywords(
    raw: list[str],
    *,
    forbidden_lower: set[str],
    max_n: int,
) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for w in _flatten_keyword_strings(raw):
        cleaned = _cleanup_keyword_candidate(w)
        if not cleaned:
            continue
        low = cleaned.lower()
        if low in seen:
            continue
        if low in forbidden_lower:
            continue
        seen.add(low)
        out.append(low)
        if len(out) >= max_n:
            break
    return out


@router.post("/keyword-suggestions", response_model=KeywordSuggestionResponse)
def keyword_suggestions(
    payload: KeywordSuggestionRequest,
    _authorized: User = Depends(require_feature(FeatureKey.KEYWORD_SUGGESTIONS)),
    db: Session = Depends(get_db),
) -> KeywordSuggestionResponse:
    # NOTE: This route is AI-gated by entitlement (admin-only today) AND runtime flags.
    # Runtime flags must be able to disable without any provider call.
    if not ai_feature_enabled(db, RuntimeFlagKey.ENABLE_AI_KEYWORD_SUGGESTIONS):
        append_runtime_log(
            db,
            category="ai",
            job_name="api_keyword_suggestions",
            provider=None,
            status="skipped",
            message="disabled_by_runtime_flag",
            disabled_by_runtime_flag=True,
            no_provider_call=True,
            request_count=0,
        )
        return KeywordSuggestionResponse(
            keywords=[],
            ok=False,
            disabled=True,
            reason="disabled_by_runtime_flag",
        )

    if not settings.gemini_api_key:
        raise HTTPException(status_code=503, detail="Gemini API key not configured")
    idea = (payload.idea or "").strip()
    if not idea:
        raise HTTPException(status_code=400, detail="idea is required")

    forbidden = _expand_forbidden_tokens(_context_terms_lower(payload), idea)
    avoid_list = ", ".join(sorted(forbidden))[:500]

    prompt = (
        "You output monitoring keywords only. Reply with STRICT JSON and nothing else.\n"
        "Schema: {\"keywords\": [\"...\", \"...\"]}\n"
        f"Rules: at most {MAX_KW} items; each item one short phrase (under {_MAX_PHRASE_LEN} chars); "
        "lowercase; no duplicates; no sentences, numbering, markdown, labels, or explanations; "
        "no comma-separated lists inside one string—use one array entry per phrase.\n"
        "Do not repeat supplied narrative text or these tokens/phrases (case-insensitive): "
        f"{avoid_list if avoid_list else '(none)'}.\n"
        "Suggest distinct, useful monitoring phrases related to the topic but not verbatim repeats.\n"
    )
    if payload.instrument:
        prompt += f"Context instrument: {payload.instrument}\n"
    if payload.asset_class:
        prompt += f"Context asset class: {payload.asset_class}\n"
    if payload.portfolio:
        prompt += f"Context portfolio: {payload.portfolio}\n"
    prompt += f"Narrative idea: {idea}\n"

    url = _gemini_generate_url(settings.gemini_model)
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 400,
            "responseMimeType": "application/json",
        },
    }
    try:
        with httpx.Client(timeout=30.0) as client:
            r = client.post(url, params={"key": settings.gemini_api_key}, json=body)
            try:
                r.raise_for_status()
            except httpx.HTTPStatusError as e:
                snippet = (e.response.text or "")[:800]
                logger.warning(
                    "Gemini keyword-suggestions HTTP error status=%s url_model=%s body_prefix=%s",
                    e.response.status_code,
                    resolve_gemini_rest_model_id(settings.gemini_model),
                    snippet.replace("\n", " "),
                )
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Gemini request failed (HTTP {e.response.status_code})",
                ) from None
            out = r.json()
    except HTTPException:
        raise
    except httpx.RequestError as e:
        logger.warning("Gemini keyword-suggestions transport error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Gemini request failed (network error)",
        ) from None

    text = _extract_text_from_gemini_body(out)
    if not text:
        logger.warning(
            "Gemini keyword-suggestions: missing text in response keys=%s",
            list(out.keys()) if isinstance(out, dict) else type(out),
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Gemini returned no usable content",
        )

    parsed = _parse_keywords_from_model_text(text)
    if parsed is None:
        parsed = _parse_keywords_from_lines(text)
    keywords = _finalize_keywords(parsed, forbidden_lower=forbidden, max_n=MAX_KW)
    if not keywords:
        logger.warning(
            "Gemini keyword-suggestions: parsed empty keywords, text_prefix=%s",
            text[:400].replace("\n", " "),
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not parse keyword suggestions from model output",
        )

    return KeywordSuggestionResponse(keywords=keywords)


def _load_owned_entity(db: Session, user: User, entity_id) -> PortfolioEntity:
    eid = entity_id
    entity = db.scalar(
        select(PortfolioEntity)
        .where(PortfolioEntity.id == eid, PortfolioEntity.user_id == user.id)
        .options(selectinload(PortfolioEntity.instrument))
    )
    if not entity:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entity not found")
    return entity


@router.post("/price-move-explanation", response_model=PriceMoveExplanationOut | AiDisabledResponse)
def price_move_explanation(
    payload: EntityChartWindowRequest,
    _authorized: User = Depends(require_feature(FeatureKey.PRICE_MOVE_EXPLANATION)),
    db: Session = Depends(get_db),
) -> PriceMoveExplanationOut | AiDisabledResponse:
    """
    OpenAI chat (stored OHLCV + news + metrics only). Massive is not used.
    """
    if not ai_feature_enabled(db, RuntimeFlagKey.ENABLE_AI_PRICE_MOVE_EXPLANATION):
        logger.info(
            "job=ai_api feature=price_move_explanation disabled_by_runtime_flag=1 flag=%s no_provider_call=true",
            RuntimeFlagKey.ENABLE_AI_PRICE_MOVE_EXPLANATION,
        )
        append_runtime_log(
            db,
            category="ai",
            job_name="api_price_move_explanation",
            provider=None,
            status="skipped",
            message="disabled_by_runtime_flag",
            disabled_by_runtime_flag=True,
            no_provider_call=True,
            request_count=0,
        )
        return AiDisabledResponse()
    entity = _load_owned_entity(db, _authorized, payload.entity_id)
    try:
        return explain_price_move(
            db,
            entity=entity,
            window_start=payload.window_start,
            window_end=payload.window_end,
            chart_period=payload.chart_period,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from None
    except json.JSONDecodeError as e:
        logger.warning("price_move_explanation json decode: %s", e)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Model returned invalid JSON") from None
    except httpx.HTTPStatusError as e:
        logger.warning("price_move_explanation provider HTTP %s", e.response.status_code)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Model provider error (HTTP {e.response.status_code})",
        ) from None
    except httpx.RequestError as e:
        logger.warning("price_move_explanation transport: %s", e)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Model provider network error") from None
    except RuntimeError as e:
        msg = str(e)
        if "not_configured" in msg:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="OpenAI is not configured: set OPENAI_API_KEY (optional OPENAI_CHAT_COMPLETIONS_URL).",
            ) from None
        logger.warning("price_move_explanation runtime: %s", msg)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Model request failed") from None


@router.post("/range-summary", response_model=RangeSummaryOut | AiDisabledResponse)
def range_summary(
    payload: EntityChartWindowRequest,
    _authorized: User = Depends(require_feature(FeatureKey.RANGE_SUMMARY)),
    db: Session = Depends(get_db),
) -> RangeSummaryOut | AiDisabledResponse:
    """Concise period summary from stored context only (OpenAI chat; Massive is not used)."""
    if not ai_feature_enabled(db, RuntimeFlagKey.ENABLE_AI_RANGE_ANALYSIS):
        append_runtime_log(
            db,
            category="ai",
            job_name="api_range_summary",
            provider=None,
            status="skipped",
            message="disabled_by_runtime_flag",
            disabled_by_runtime_flag=True,
            no_provider_call=True,
            request_count=0,
        )
        return AiDisabledResponse()
    entity = _load_owned_entity(db, _authorized, payload.entity_id)
    try:
        return summarize_range(
            db,
            entity=entity,
            window_start=payload.window_start,
            window_end=payload.window_end,
            chart_period=payload.chart_period,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from None
    except json.JSONDecodeError as e:
        logger.warning("range_summary json decode: %s", e)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Model returned invalid JSON") from None
    except httpx.HTTPStatusError as e:
        logger.warning("range_summary provider HTTP %s", e.response.status_code)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Model provider error (HTTP {e.response.status_code})",
        ) from None
    except httpx.RequestError as e:
        logger.warning("range_summary transport: %s", e)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Model provider network error") from None
    except RuntimeError as e:
        msg = str(e)
        if "not_configured" in msg:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="OpenAI is not configured: set OPENAI_API_KEY (optional OPENAI_CHAT_COMPLETIONS_URL).",
            ) from None
        logger.warning("range_summary runtime: %s", msg)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Model request failed") from None


@router.post("/compare-summary", response_model=CompareSummaryOut | AiDisabledResponse)
def compare_summary(
    _authorized: User = Depends(require_feature(FeatureKey.COMPARE_SUMMARY)),
    db: Session = Depends(get_db),
) -> CompareSummaryOut | AiDisabledResponse:
    """
    Structured AI endpoint (schema-first). Default OFF via runtime flags.
    When disabled, returns a stable structured disabled payload and makes no provider calls.
    """
    if not ai_feature_enabled(db, RuntimeFlagKey.ENABLE_AI_COMPARE_SUMMARY):
        logger.info(
            "job=ai_api feature=compare_summary disabled_by_runtime_flag=1 flag=%s no_provider_call=true",
            RuntimeFlagKey.ENABLE_AI_COMPARE_SUMMARY,
        )
        append_runtime_log(
            db,
            category="ai",
            job_name="api_compare_summary",
            provider=None,
            status="skipped",
            message="disabled_by_runtime_flag",
            disabled_by_runtime_flag=True,
            no_provider_call=True,
            request_count=0,
        )
        return AiDisabledResponse()
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Not implemented")
