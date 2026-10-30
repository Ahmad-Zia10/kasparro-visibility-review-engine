from datetime import datetime
from typing import ClassVar, Literal

from pydantic import BaseModel, Field

Engine = Literal["aimode", "chatgpt", "gemini"]


class PackRecord(BaseModel):
    """One validated line from a pack file, with its original text kept."""

    id_field: ClassVar[str]
    line: int = 0
    raw_json: str = ""

    @property
    def record_id(self) -> str:
        return getattr(self, self.id_field)


class PromptRecord(PackRecord):
    id_field: ClassVar[str] = "prompt_id"
    prompt_id: str
    run_id: str
    text: str = Field(min_length=1)


class ResponseRecord(PackRecord):
    id_field: ClassVar[str] = "response_id"
    response_id: str
    run_id: str
    prompt_id: str
    engine: Engine
    answer_text: str = Field(min_length=1)
    answer_markdown: str | None = None
    model_version: str | None = None
    capture_status: Literal["captured"]


class CitationRecord(PackRecord):
    id_field: ClassVar[str] = "citation_id"
    citation_id: str
    response_id: str
    prompt_id: str
    engine: Engine
    order: int = Field(ge=1)
    citation_type: Literal["inline_hyperlink", "sources_panel"]
    url: str


class RejectedRecord(BaseModel):
    file: str
    line: int
    record_id: str | None
    reason: str


class DatasetOut(BaseModel):
    dataset_id: str
    content_hash: str
    imported_at: datetime
    prompt_count: int
    response_count: int
    citation_count: int
    rejected: list[RejectedRecord]
