"""Community submission schemas."""

from __future__ import annotations

from pydantic import BaseModel


class CommunitySubmissionCreate(BaseModel):
    category: str
    title: str
    description: str = ""
    problem_solves: str = ""
    platform_data_used: str = ""
    has_data_source: bool = False
    data_source_access: str = ""
    contact_info: str = ""
    notes: str = ""


class CommunitySubmissionOut(BaseModel):
    id: str
    category: str
    title: str
    created_at: str


class DataRequestCreate(BaseModel):
    requested_data_name: str
    description: str = ""
    use_case: str = ""
    source_known: bool = False
    how_to_obtain: str = ""
    source_details: str = ""
    contact_info: str = ""
    priority: str = "medium"
    notes: str = ""


class DataRequestOut(BaseModel):
    id: str
    requested_data_name: str
    created_at: str
