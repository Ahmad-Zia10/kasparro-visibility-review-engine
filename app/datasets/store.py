import json
import sqlite3
from datetime import datetime

from app.datasets.schemas import CitationRecord, PromptRecord, RejectedRecord, ResponseRecord


def dataset_exists(conn: sqlite3.Connection, dataset_id: str) -> bool:
    row = conn.execute("SELECT 1 FROM datasets WHERE dataset_id = ?", (dataset_id,)).fetchone()
    return row is not None


def insert_dataset(
    conn: sqlite3.Connection,
    dataset_id: str,
    content_hash: str,
    imported_at: datetime,
    rejected: list[RejectedRecord],
) -> None:
    conn.execute(
        "INSERT INTO datasets (dataset_id, content_hash, imported_at, rejected_json) "
        "VALUES (?, ?, ?, ?)",
        (
            dataset_id,
            content_hash,
            imported_at.isoformat(),
            json.dumps([record.model_dump() for record in rejected]),
        ),
    )


def insert_prompts(conn: sqlite3.Connection, dataset_id: str, prompts: list[PromptRecord]) -> None:
    conn.executemany(
        "INSERT INTO prompts (dataset_id, prompt_id, text, raw_json) VALUES (?, ?, ?, ?)",
        [(dataset_id, prompt.prompt_id, prompt.text, prompt.raw_json) for prompt in prompts],
    )


def insert_responses(
    conn: sqlite3.Connection, dataset_id: str, responses: list[ResponseRecord]
) -> None:
    conn.executemany(
        "INSERT INTO responses (dataset_id, response_id, prompt_id, engine, model_version, "
        "answer_text, answer_markdown, raw_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                dataset_id,
                response.response_id,
                response.prompt_id,
                response.engine,
                response.model_version,
                response.answer_text,
                response.answer_markdown,
                response.raw_json,
            )
            for response in responses
        ],
    )


def insert_citations(
    conn: sqlite3.Connection, dataset_id: str, citations: list[CitationRecord]
) -> None:
    conn.executemany(
        "INSERT INTO citations (dataset_id, citation_id, response_id, position, citation_type, "
        "url, raw_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            (
                dataset_id,
                citation.citation_id,
                citation.response_id,
                citation.order,
                citation.citation_type,
                citation.url,
                citation.raw_json,
            )
            for citation in citations
        ],
    )


def get_dataset(conn: sqlite3.Connection, dataset_id: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT dataset_id, content_hash, imported_at, rejected_json, "
        "(SELECT COUNT(*) FROM prompts WHERE dataset_id = d.dataset_id) AS prompt_count, "
        "(SELECT COUNT(*) FROM responses WHERE dataset_id = d.dataset_id) AS response_count, "
        "(SELECT COUNT(*) FROM citations WHERE dataset_id = d.dataset_id) AS citation_count "
        "FROM datasets AS d WHERE dataset_id = ?",
        (dataset_id,),
    ).fetchone()
