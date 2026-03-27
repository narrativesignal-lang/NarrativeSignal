from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document import SourceDocument
from app.models.document_analysis import DocumentAnalysis
from app.models.keyword_group import KeywordGroup
from app.models.portfolio import PortfolioEntity


def build_group_snapshot_markdown(
    *,
    db: Session,
    group: KeywordGroup,
    window_start: datetime,
    window_end: datetime,
    docs: list[SourceDocument],
) -> str:
    doc_ids = [d.id for d in docs]
    analyses = []
    if doc_ids:
        analyses = db.scalars(
            select(DocumentAnalysis).where(DocumentAnalysis.group_id == group.id, DocumentAnalysis.document_id.in_(doc_ids))
        ).all()
    by_doc: dict[uuid.UUID, DocumentAnalysis] = {a.document_id: a for a in analyses}

    bull = bear = neu = 0
    for a in analyses:
        if a.sentiment_label == "bullish":
            bull += 1
        elif a.sentiment_label == "bearish":
            bear += 1
        else:
            neu += 1

    bullets = []
    for d in docs[:10]:
        a = by_doc.get(d.id)
        title = d.title or "(untitled)"
        url = d.url or ""
        sent = f" — **{a.sentiment_label}** ({a.sentiment_score:+.2f})" if a else ""
        if url:
            bullets.append(f"- [{title}]({url}){sent}")
        else:
            bullets.append(f"- {title}{sent}")

    events = []
    for d in docs[:8]:
        a = by_doc.get(d.id)
        if not a:
            continue
        for ev in (a.detected_events or [])[:3]:
            t = (ev or {}).get("title") or ""
            details = (ev or {}).get("details") or ""
            if t and details:
                events.append(f"- **{t}**: {details}")
            elif t:
                events.append(f"- **{t}**")

    lines = [
        f"## {group.name}",
        "",
        f"Window: **{window_start.isoformat()} -> {window_end.isoformat()}**",
        "",
        "### Sentiment distribution",
        f"- Bullish: **{bull}**",
        f"- Bearish: **{bear}**",
        f"- Neutral: **{neu}**",
        "",
        "### Key articles",
        *(bullets if bullets else ["- No matching articles linked for this window."]),
        "",
        "### Detected events (AI)",
        *(events if events else ["- No events extracted (or AI provider is running in heuristic mode)."]),
        "",
        "### Narrative summary (AI)",
        "- See each article's stored summary; a higher-level group summary is generated in daily reports.",
    ]
    return "\n".join(lines) + "\n"


def build_entity_snapshot_markdown(
    *,
    entity: PortfolioEntity,
    portfolio_name: str,
    window_start: datetime,
    window_end: datetime,
) -> str:
    """Build markdown for an entity-based report (no document analysis; entity context only)."""
    inst = entity.instrument
    instrument_line = "No instrument"
    asset_type = "—"
    if inst:
        instrument_line = f"{inst.symbol}" + (f" · {inst.display_name}" if inst.display_name else "")
        asset_type = inst.asset_class or "—"
    terms_str = ", ".join(t.term for t in entity.terms[:20]) if entity.terms else "—"
    lines = [
        f"## {entity.name}",
        "",
        f"**Portfolio:** {portfolio_name}",
        f"**Instrument:** {instrument_line}",
        f"**Asset type:** {asset_type}",
        "",
        f"Window: **{window_start.isoformat()} → {window_end.isoformat()}**",
        "",
        "### Terms",
        terms_str,
        "",
        "### Narrative / charts",
        "Add charts and narrative from the Entity workspace.",
    ]
    return "\n".join(lines) + "\n"


def build_daily_info_report_markdown(*, items: list[SourceDocument]) -> str:
    bullets = []
    for d in items[:30]:
        title = d.title or "(untitled)"
        url = d.url or ""
        if url:
            bullets.append(f"- [{title}]({url})")
        else:
            bullets.append(f"- {title}")
    return "\n".join(
        [
            "## 24 Hour Information Report",
            "",
            "### Top items (ingested)",
            *(bullets if bullets else ["- No items found."]),
            "",
        ]
    )

