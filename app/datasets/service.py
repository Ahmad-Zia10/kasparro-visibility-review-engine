import hashlib
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import TypeVar

from pydantic import ValidationError

from app import clock
from app.datasets import store
from app.datasets.schemas import (
    CitationRecord,
    DatasetOut,
    PackRecord,
    PromptRecord,
    RejectedRecord,
    ResponseRecord,
)
from app.db import transaction
from app.errors import NotFound, UnreadablePack

PACK_FILES = ("prompts.jsonl", "responses.jsonl", "citations.jsonl")

RecordT = TypeVar("RecordT", bound=PackRecord)


@dataclass
class ParsedPack:
    prompts: list[PromptRecord]
    responses: list[ResponseRecord]
    citations: list[CitationRecord]
    rejected: list[RejectedRecord]


def import_dataset(conn: sqlite3.Connection, pack_dir: Path) -> tuple[DatasetOut, bool]:
    """Store a validated pack once; return it and whether this call created it."""
    texts = {name: read_pack_file(pack_dir / "data" / name) for name in PACK_FILES}
    content_hash = hash_pack(texts)
    dataset_id = f"ds_{content_hash[:12]}"
    pack = parse_pack(texts)

    with transaction(conn):
        is_new = not store.dataset_exists(conn, dataset_id)
        if is_new:
            store.insert_dataset(conn, dataset_id, content_hash, clock.now(), pack.rejected)
            store.insert_prompts(conn, dataset_id, pack.prompts)
            store.insert_responses(conn, dataset_id, pack.responses)
            store.insert_citations(conn, dataset_id, pack.citations)
    return get_dataset(conn, dataset_id), is_new


def get_dataset(conn: sqlite3.Connection, dataset_id: str) -> DatasetOut:
    row = store.get_dataset(conn, dataset_id)
    if row is None:
        raise NotFound(f"dataset {dataset_id} not found")
    return DatasetOut(
        dataset_id=row["dataset_id"],
        content_hash=row["content_hash"],
        imported_at=row["imported_at"],
        prompt_count=row["prompt_count"],
        response_count=row["response_count"],
        citation_count=row["citation_count"],
        rejected=json.loads(row["rejected_json"]),
    )


def read_pack_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise UnreadablePack(f"cannot read {path.name}") from error


def hash_pack(texts: dict[str, str]) -> str:
    digest = hashlib.sha256()
    for name in PACK_FILES:
        digest.update(name.encode())
        digest.update(texts[name].encode())
    return digest.hexdigest()


def parse_pack(texts: dict[str, str]) -> ParsedPack:
    prompts, rejected_prompts = validate_lines("prompts.jsonl", texts, PromptRecord)
    responses, rejected_responses = validate_lines("responses.jsonl", texts, ResponseRecord)
    citations, rejected_citations = validate_lines("citations.jsonl", texts, CitationRecord)

    prompt_ids = {prompt.prompt_id for prompt in prompts}
    responses, unlinked_responses = keep_linked(
        "responses.jsonl", responses, "prompt_id", prompt_ids
    )
    response_ids = {response.response_id for response in responses}
    citations, unlinked_citations = keep_linked(
        "citations.jsonl", citations, "response_id", response_ids
    )

    rejected = (
        rejected_prompts
        + rejected_responses
        + unlinked_responses
        + rejected_citations
        + unlinked_citations
    )
    return ParsedPack(prompts, responses, citations, rejected)


def validate_lines(
    file_name: str, texts: dict[str, str], model: type[RecordT]
) -> tuple[list[RecordT], list[RejectedRecord]]:
    """Validate each line on its own so one bad record never blocks the rest."""
    accepted: list[RecordT] = []
    rejected: list[RejectedRecord] = []
    seen_ids: set[str] = set()
    for line_no, line in enumerate(texts[file_name].splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = model.model_validate_json(line)
        except ValidationError as error:
            record_id = id_from_raw(line, model.id_field)
            rejected.append(
                RejectedRecord(
                    file=file_name, line=line_no, record_id=record_id, reason=first_problem(error)
                )
            )
            continue
        if record.record_id in seen_ids:
            reason = f"duplicate {model.id_field}"
            rejected.append(
                RejectedRecord(
                    file=file_name, line=line_no, record_id=record.record_id, reason=reason
                )
            )
            continue
        seen_ids.add(record.record_id)
        accepted.append(record.model_copy(update={"line": line_no, "raw_json": line}))
    return accepted, rejected


def keep_linked(
    file_name: str, records: list[RecordT], parent_field: str, parent_ids: set[str]
) -> tuple[list[RecordT], list[RejectedRecord]]:
    """Drop records whose parent was missing or rejected."""
    kept = [record for record in records if getattr(record, parent_field) in parent_ids]
    rejected = [
        RejectedRecord(
            file=file_name,
            line=record.line,
            record_id=record.record_id,
            reason=f"unknown {parent_field} {getattr(record, parent_field)}",
        )
        for record in records
        if getattr(record, parent_field) not in parent_ids
    ]
    return kept, rejected


def first_problem(error: ValidationError) -> str:
    issue = error.errors()[0]
    location = ".".join(str(part) for part in issue["loc"])
    return f"{location}: {issue['msg']}" if location else issue["msg"]


def id_from_raw(line: str, id_field: str) -> str | None:
    try:
        return json.loads(line).get(id_field)
    except (json.JSONDecodeError, AttributeError):
        return None
