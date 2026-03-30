from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.feature_access import FeatureKey, can_access_feature
from app.models.document import SourceDocument
from app.models.document_analysis import DocumentAnalysis
from app.models.user import User
from app.services.ai.providers import AnalysisResult, get_provider


def analyze_documents(
    *,
    db: Session,
    group_id: uuid.UUID,
    document_ids: list[uuid.UUID],
    acting_user_id: uuid.UUID | None = None,
) -> int:
    """
    Analyze documents and persist results if not already present for the chosen provider.
    Returns number of analyses created.

    ``acting_user_id``: owner of the monitoring run; non-admins never invoke LLM providers (returns 0).
    """
    if not document_ids:
        return 0
    if acting_user_id is None:
        return 0
    owner = db.get(User, acting_user_id)
    if not owner or not can_access_feature(owner, FeatureKey.DOCUMENT_LLM_ANALYSIS):
        return 0

    provider = get_provider()
    provider_name = getattr(provider, "provider", "unknown")
    model = getattr(provider, "model", "v1")

    docs = db.scalars(select(SourceDocument).where(SourceDocument.id.in_(document_ids))).all()
    docs_by_id = {d.id: d for d in docs}

    created = 0
    for did in document_ids:
        doc = docs_by_id.get(did)
        if not doc:
            continue

        existing = db.scalar(
            select(DocumentAnalysis.id).where(
                DocumentAnalysis.group_id == group_id,
                DocumentAnalysis.document_id == did,
                DocumentAnalysis.provider == provider_name,
            )
        )
        if existing:
            continue

        text = " ".join([doc.title or "", doc.content or ""])
        result: AnalysisResult = provider.analyze(text=text)

        row = DocumentAnalysis(
            group_id=group_id,
            document_id=did,
            provider=result.provider,
            model=result.model,
            sentiment_label=result.sentiment_label,
            sentiment_score=float(result.sentiment_score),
            narrative_summary=result.narrative_summary,
            detected_events=result.detected_events,
        )
        db.add(row)
        db.commit()
        created += 1

    return created

