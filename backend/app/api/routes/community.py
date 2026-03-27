"""Community submissions and data requests."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.community import CommunityDataRequest, CommunitySubmission
from app.models.user import User
from app.schemas.community import (
    CommunitySubmissionCreate,
    CommunitySubmissionOut,
    DataRequestCreate,
    DataRequestOut,
)
from app.services.community_email import forward_data_request_email, forward_submission_email


router = APIRouter()


@router.post("/submissions", response_model=CommunitySubmissionOut)
def create_submission(
    payload: CommunitySubmissionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CommunitySubmissionOut:
    s = CommunitySubmission(
        user_id=current_user.id,
        category=payload.category,
        title=payload.title,
        description=payload.description,
        problem_solves=payload.problem_solves,
        platform_data_used=payload.platform_data_used,
        has_data_source=payload.has_data_source,
        data_source_access=payload.data_source_access,
        contact_info=payload.contact_info,
        notes=payload.notes,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    forward_submission_email(
        category=payload.category,
        title=payload.title,
        description=payload.description,
        contact_info=payload.contact_info,
    )
    return CommunitySubmissionOut(id=str(s.id), category=s.category, title=s.title, created_at=s.created_at.isoformat())


@router.post("/data-requests", response_model=DataRequestOut)
def create_data_request(
    payload: DataRequestCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DataRequestOut:
    r = CommunityDataRequest(
        user_id=current_user.id,
        requested_data_name=payload.requested_data_name,
        description=payload.description,
        use_case=payload.use_case,
        source_known=payload.source_known,
        how_to_obtain=payload.how_to_obtain,
        source_details=payload.source_details,
        contact_info=payload.contact_info,
        priority=payload.priority,
        notes=payload.notes,
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    forward_data_request_email(
        requested_data_name=payload.requested_data_name,
        description=payload.description,
        source_known=payload.source_known,
        contact_info=payload.contact_info,
    )
    return DataRequestOut(id=str(r.id), requested_data_name=r.requested_data_name, created_at=r.created_at.isoformat())
