"""
Simplified AI Alert pipeline (MVP).
- Step 1–2: Heuristic impact scoring (keyword relevance, asset mention, sentiment)
- Step 3: Placeholder for GPT deep analysis
- Step 4: Placeholder for historical comparison
- Step 5: Trigger alert if above threshold
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.monitoring import TriggeredAlert
from app.models.report import Report


def run_ai_alert_pipeline(
    db: Session,
    user_id: uuid.UUID,
    schedule_id: uuid.UUID | None,
    schedule_type: str,
    group_ids: list[uuid.UUID],
    entity_ids: list[uuid.UUID],
    linked_assets: list[str],
    threshold: int | None,
    label: str | None,
) -> dict:
    """
    Simplified AI Alert: heuristic scoring, placeholder for LLM steps.
    Returns {alerts_triggered, report_created}.
    """
    now = datetime.now(timezone.utc)
    window_end = now
    window_start = now - timedelta(hours=24)

    # Placeholder: mock impact score (in real impl: fetch content, cluster, filter, score)
    impact_score = 65
    key_signals: list[str] = ["Mock signal 1: keyword relevance high", "Mock signal 2: asset mention detected"]
    summary = "Placeholder AI analysis. Connect content sources and LLM for full pipeline."

    triggered = 0
    if threshold is None:
        threshold = 60
    if impact_score >= threshold:
        alert = TriggeredAlert(
            user_id=user_id,
            schedule_id=schedule_id,
            schedule_type=schedule_type,
            title=f"{label or 'AI Alert'}: High impact detected",
            body_markdown=summary,
            impact_score=impact_score,
            payload={"key_signals": key_signals, "placeholder": True},
        )
        db.add(alert)
        db.commit()
        triggered = 1

    return {"alerts_triggered": triggered, "impact_score": impact_score}


def run_ai_report_pipeline(
    db: Session,
    user_id: uuid.UUID,
    schedule_id: uuid.UUID | None,
    schedule_type: str,
    group_ids: list[uuid.UUID],
    entity_ids: list[uuid.UUID],
    linked_assets: list[str],
    label: str | None,
) -> dict:
    """
    AI Report: always generate a report (no threshold). Same heuristic placeholder.
    """
    now = datetime.now(timezone.utc)
    window_end = now
    window_start = now - timedelta(hours=24)

    # Placeholder content
    impact_score = 55
    summary = "## AI Report (Placeholder)\n\n"
    summary += "- **Summary:** Connect content sources and LLM for full analysis.\n"
    summary += "- **Key signals:** Placeholder; real pipeline will extract from ingested docs.\n"
    summary += "- **Potential impact:** Heuristic score = %d\n" % impact_score
    summary += "- **Related assets:** %s\n" % (", ".join(linked_assets) if linked_assets else "None configured")
    summary += "\n---\n*Email/SMS delivery: coming soon.*"

    report = Report(
        user_id=user_id,
        kind="ai_report",
        title=f"{label or 'AI Report'}: Narrative analysis",
        label=label,
        schedule_type=schedule_type,
        body_markdown=summary,
        payload={
            "schedule_id": str(schedule_id) if schedule_id else None,
            "schedule_type": schedule_type,
            "label": label,
            "impact_score": impact_score,
            "key_signals": ["Placeholder signal"],
            "related_assets": linked_assets,
        },
        window_start=window_start,
        window_end=window_end,
    )
    db.add(report)
    db.commit()

    return {"report_created": 1}
