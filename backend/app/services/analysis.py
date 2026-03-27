from __future__ import annotations

import re
from datetime import datetime, timezone

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.models.document import SourceDocument
from app.models.index_point import IndexPoint
from app.models.keyword_group import KeywordGroup


POS_WORDS = {"bull", "bullish", "surge", "record", "beats", "growth", "support", "approve", "up", "positive"}
NEG_WORDS = {"bear", "bearish", "crash", "miss", "downgrade", "risk", "lawsuit", "down", "negative"}


def floor_time_bucket(dt: datetime, *, bucket_minutes: int) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    minute = (dt.minute // bucket_minutes) * bucket_minutes
    return dt.replace(minute=minute, second=0, microsecond=0)


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").lower()).strip()


def _matches_group(doc_text: str, group: KeywordGroup) -> bool:
    text = _norm(doc_text)
    if not group.terms:
        return False
    required = [t.term for t in group.terms if t.is_required]
    optional = [t.term for t in group.terms if not t.is_required]

    def has(term: str) -> bool:
        t = _norm(term)
        if not t:
            return False
        return t in text

    if required and not all(has(t) for t in required):
        return False
    if optional and not any(has(t) for t in optional):
        return False
    if required and not optional:
        return True
    return True


def _sentiment_bucket(text: str) -> str:
    t = _norm(text)
    words = set(re.findall(r"[a-z']+", t))
    pos = len(words & POS_WORDS)
    neg = len(words & NEG_WORDS)
    if pos > neg:
        return "pos"
    if neg > pos:
        return "neg"
    return "neu"


def analyze_documents_for_group(
    *,
    db: Session,
    user_id,
    group: KeywordGroup,
    window_start: datetime,
    window_end: datetime,
) -> tuple[dict, list[SourceDocument]]:
    docs = db.scalars(
        select(SourceDocument)
        .where(
            and_(
                SourceDocument.user_id == user_id,
                SourceDocument.published_at.is_not(None),
                SourceDocument.published_at >= window_start,
                SourceDocument.published_at < window_end,
            )
        )
        .order_by(SourceDocument.published_at.desc())
        .limit(300)
    ).all()

    matched: list[SourceDocument] = []
    pos = neg = neu = 0

    for d in docs:
        text = " ".join([d.title or "", d.content or ""])
        if not _matches_group(text, group):
            continue
        matched.append(d)
        s = _sentiment_bucket(text)
        if s == "pos":
            pos += 1
        elif s == "neg":
            neg += 1
        else:
            neu += 1

    metrics = {"mention_volume": len(matched), "pos": pos, "neg": neg, "neu": neu}
    return metrics, matched[:10]


def compute_derivatives(*, current: IndexPoint, previous: IndexPoint | None) -> tuple[float, float, float]:
    if not previous:
        momentum = float(current.mention_volume)
        d1 = momentum
        d2 = d1
        return momentum, d1, d2

    momentum = float(current.mention_volume - previous.mention_volume)
    d1 = float(momentum - previous.momentum)
    d2 = float(d1 - previous.d1)
    return momentum, d1, d2


def generate_group_report_markdown(
    *,
    group: KeywordGroup,
    window_start: datetime,
    window_end: datetime,
    docs: list[SourceDocument],
) -> str:
    bullets = []
    for d in docs[:8]:
        title = d.title or "(untitled)"
        url = d.url or ""
        if url:
            bullets.append(f"- [{title}]({url})")
        else:
            bullets.append(f"- {title}")

    lines = [
        f"## {group.name}",
        "",
        f"Window: **{window_start.isoformat()} → {window_end.isoformat()}**",
        "",
        "### What moved",
        "- Narrative snapshot generated from matched documents in the window.",
        "",
        "### Top information",
        *(bullets if bullets else ["- No matching documents found in this window."]),
        "",
        "### Interpretation (MVP)",
        "- Treat this as a *starter* narrative summary; plug in GPT/Gemini for richer event extraction and stance analysis.",
    ]
    return "\n".join(lines) + "\n"

