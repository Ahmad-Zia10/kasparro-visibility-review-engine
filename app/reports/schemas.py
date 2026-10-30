from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

from app.classify.base import ExecutionMode

VersionStatus = Literal["draft", "submitted", "approved", "rejected", "expired", "superseded"]


class ReportRequest(BaseModel):
    analysis_id: str


class ContentEdit(BaseModel):
    content: dict


class DecisionRequest(BaseModel):
    version: int = Field(ge=1)
    decision: Literal["approve", "reject"]
    comment: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class VersionOut(BaseModel):
    report_id: str
    analysis_id: str
    version: int
    status: VersionStatus
    revision: int
    etag: str
    content: dict
    content_sha256: str
    created_by: str
    created_at: datetime
    submitted_at: datetime | None
    review_due_at: datetime | None
    approval_valid_until: datetime | None


class ExportOut(BaseModel):
    report_id: str
    version: int
    is_latest_version: bool
    approved_by: str
    approved_at: datetime
    valid_until: datetime
    execution_mode: ExecutionMode
    model: str
    scoring_version: str
    category_version: str
    content_sha256: str
    content: dict
