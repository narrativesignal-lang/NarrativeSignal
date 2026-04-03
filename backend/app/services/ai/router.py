from __future__ import annotations

import logging
from typing import Literal

from app.core.config import settings
from app.services.ai.providers import AIProvider, GeminiProvider, HeuristicProvider, OpenAIProvider

logger = logging.getLogger(__name__)

AIProviderRole = Literal["verify", "summarize", "analysis"]


def get_provider_for_role(role: AIProviderRole) -> AIProvider:
    """
    Provider routing by role to keep behavior predictable:
    - verify: prefer Gemini (facts-first extraction)
    - summarize: prefer OpenAI (narrative/report writing)

    If the preferred provider key is missing, falls back to the other LLM if available,
    else heuristic provider.
    """
    r = (role or "summarize").strip().lower()
    if r not in ("verify", "summarize", "analysis"):
        r = "summarize"

    has_openai = bool((settings.openai_api_key or "").strip())
    has_gemini = bool((settings.gemini_api_key or "").strip())

    if r in ("verify", "analysis"):
        if has_gemini:
            return GeminiProvider()
        if has_openai:
            return OpenAIProvider()
        return HeuristicProvider()

    # summarize
    if has_openai:
        return OpenAIProvider()
    if has_gemini:
        return GeminiProvider()
    return HeuristicProvider()

