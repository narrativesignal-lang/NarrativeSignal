"""AI endpoints (e.g. keyword suggestions). Coexists with existing routes."""

from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import require_feature
from app.core.config import settings
from app.core.feature_access import FeatureKey
from app.models.user import User
from app.schemas.portfolios import KeywordSuggestionRequest, KeywordSuggestionResponse

router = APIRouter()
MAX_KW = 15


@router.post("/keyword-suggestions", response_model=KeywordSuggestionResponse)
def keyword_suggestions(
    payload: KeywordSuggestionRequest,
    current_user: User = Depends(require_feature(FeatureKey.KEYWORD_SUGGESTIONS)),
) -> KeywordSuggestionResponse:
    if not settings.gemini_api_key:
        raise HTTPException(status_code=503, detail="Gemini API key not configured")
    idea = (payload.idea or "").strip()
    if not idea:
        raise HTTPException(status_code=400, detail="idea is required")
    prompt = (
        "Generate keywords or key phrases for monitoring a narrative. "
        "Return ONLY a list of keywords, one per line. No numbering, no explanations. Max 15.\n\n"
        f"Narrative idea: {idea}\n"
    )
    if payload.instrument:
        prompt += f"Instrument: {payload.instrument}\n"
    if payload.asset_class:
        prompt += f"Asset class: {payload.asset_class}\n"
    if payload.portfolio:
        prompt += f"Portfolio: {payload.portfolio}\n"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{settings.gemini_model}:generateContent"
    with httpx.Client(timeout=30) as client:
        r = client.post(url, params={"key": settings.gemini_api_key}, json={"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0.3, "maxOutputTokens": 500}})
        r.raise_for_status()
        out = r.json()
    try:
        text = out["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError):
        raise HTTPException(status_code=502, detail="Invalid Gemini response")
    raw = [x.strip() for x in text.splitlines() if x.strip()]
    seen: set[str] = set()
    keywords: list[str] = []
    for line in raw:
        w = line.lstrip("0123456789.-) ").strip().lower()
        if w and w not in seen:
            seen.add(w)
            keywords.append(w)
        if len(keywords) >= MAX_KW:
            break
    return KeywordSuggestionResponse(keywords=keywords[:MAX_KW])
