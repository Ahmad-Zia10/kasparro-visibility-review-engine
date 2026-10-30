from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.classify.base import ExecutionMode


class AnalysisRequest(BaseModel):
    dataset_id: str


class AnalysisConfig(BaseModel):
    """Everything that decides whether a stored run can be reused."""

    dataset_id: str
    execution_mode: ExecutionMode
    prompt_version: str
    model: str
    scoring_version: str
    category_version: str


class StatusCounts(BaseModel):
    pending: int
    done: int
    failed: int
    skipped: int
    total: int


class AnalysisOut(AnalysisConfig):
    analysis_id: str
    created_at: datetime
    status: Literal["running", "complete"]
    counts: StatusCounts


class ResultOut(BaseModel):
    analysis_id: str
    response_id: str
    status: Literal["pending", "done", "failed", "skipped"]
    attempts: int
    execution_mode: ExecutionMode
    labels: dict | None
    score: dict | None
    evidence: list[dict]
    error: str | None
    reason: str | None
    updated_at: datetime


class ResultsPage(BaseModel):
    total: int
    limit: int
    offset: int
    results: list[ResultOut]
