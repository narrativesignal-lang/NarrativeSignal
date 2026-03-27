from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings


@dataclass(frozen=True)
class AnalysisResult:
    sentiment_label: str  # bullish/bearish/neutral
    sentiment_score: float  # -1..+1
    narrative_summary: str
    detected_events: list[dict]
    provider: str
    model: str


class AIProvider(Protocol):
    def analyze(self, *, text: str) -> AnalysisResult: ...


class HeuristicProvider:
    provider = "heuristic"
    model = "v1"

    POS = {"bull", "bullish", "surge", "record", "beats", "growth", "support", "approve", "up", "positive"}
    NEG = {"bear", "bearish", "crash", "miss", "downgrade", "risk", "lawsuit", "down", "negative"}

    def analyze(self, *, text: str) -> AnalysisResult:
        t = (text or "").lower()
        pos = sum(1 for w in self.POS if w in t)
        neg = sum(1 for w in self.NEG if w in t)
        if pos > neg:
            label = "bullish"
        elif neg > pos:
            label = "bearish"
        else:
            label = "neutral"
        score = 0.0 if pos == neg else max(-1.0, min(1.0, (pos - neg) / max(3.0, pos + neg)))
        summary = "Heuristic summary (MVP): sentiment inferred from simple keyword cues."
        events = []
        return AnalysisResult(
            sentiment_label=label,
            sentiment_score=score,
            narrative_summary=summary,
            detected_events=events,
            provider=self.provider,
            model=self.model,
        )


class OpenAIProvider:
    provider = "openai"

    def __init__(self) -> None:
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY not set")
        self.model = settings.openai_model

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5, min=0.5, max=6))
    def analyze(self, *, text: str) -> AnalysisResult:
        # Uses OpenAI Chat Completions-compatible endpoint.
        # We keep this minimal; user can swap to Responses API later.
        url = "https://api.openai.com/v1/chat/completions"
        system = (
            "You are a market narrative analyst. Output STRICT JSON only (no markdown). "
            "Schema: {sentiment_label: 'bullish'|'bearish'|'neutral', sentiment_score: number (-1..1), "
            "narrative_summary: string (<=80 words), detected_events: [{title:string, details:string}]}."
        )
        payload = {
            "model": self.model,
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": text[:8000]},
            ],
        }
        headers = {"Authorization": f"Bearer {settings.openai_api_key}"}
        with httpx.Client(timeout=30) as client:
            r = client.post(url, json=payload, headers=headers)
            r.raise_for_status()
            content = r.json()["choices"][0]["message"]["content"]

        data = json.loads(content)
        return AnalysisResult(
            sentiment_label=data["sentiment_label"],
            sentiment_score=float(data["sentiment_score"]),
            narrative_summary=data["narrative_summary"],
            detected_events=list(data.get("detected_events") or []),
            provider=self.provider,
            model=self.model,
        )


class GeminiProvider:
    provider = "gemini"

    def __init__(self) -> None:
        if not settings.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY not set")
        self.model = settings.gemini_model

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5, min=0.5, max=6))
    def analyze(self, *, text: str) -> AnalysisResult:
        # Minimal Gemini REST call.
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        prompt = (
            "Return STRICT JSON only (no markdown). "
            "Schema: {sentiment_label: 'bullish'|'bearish'|'neutral', sentiment_score: number (-1..1), "
            "narrative_summary: string (<=80 words), detected_events: [{title:string, details:string}]}. "
            "Text:\n" + text[:8000]
        )
        payload = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0.2}}
        with httpx.Client(timeout=30) as client:
            r = client.post(url, params={"key": settings.gemini_api_key}, json=payload)
            r.raise_for_status()
            out_text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
        data = json.loads(out_text)
        return AnalysisResult(
            sentiment_label=data["sentiment_label"],
            sentiment_score=float(data["sentiment_score"]),
            narrative_summary=data["narrative_summary"],
            detected_events=list(data.get("detected_events") or []),
            provider=self.provider,
            model=self.model,
        )


def get_provider() -> AIProvider:
    # Prefer explicit keys; otherwise fall back to heuristic provider.
    if settings.openai_api_key:
        return OpenAIProvider()
    if settings.gemini_api_key:
        return GeminiProvider()
    return HeuristicProvider()

