import json
import sqlite3
import uuid
from datetime import datetime

from app.analyses.results import ResultRow
from app.analyses.schemas import AnalysisConfig
from app.classify.base import ModelCall


def find_analysis_id(conn: sqlite3.Connection, config: AnalysisConfig) -> str | None:
    row = conn.execute(
        "SELECT analysis_id FROM analyses WHERE dataset_id = :dataset_id "
        "AND execution_mode = :execution_mode AND prompt_version = :prompt_version "
        "AND model = :model AND scoring_version = :scoring_version "
        "AND category_version = :category_version",
        config.model_dump(),
    ).fetchone()
    return row["analysis_id"] if row else None


def insert_analysis(
    conn: sqlite3.Connection, analysis_id: str, config: AnalysisConfig, created_at: datetime
) -> None:
    conn.execute(
        "INSERT INTO analyses (analysis_id, dataset_id, execution_mode, prompt_version, model, "
        "scoring_version, category_version, created_at) VALUES (:analysis_id, :dataset_id, "
        ":execution_mode, :prompt_version, :model, :scoring_version, :category_version, "
        ":created_at)",
        config.model_dump() | {"analysis_id": analysis_id, "created_at": created_at.isoformat()},
    )


def insert_pending(
    conn: sqlite3.Connection, analysis_id: str, dataset_id: str, created_at: datetime
) -> None:
    conn.execute(
        "INSERT INTO response_results (analysis_id, response_id, status, updated_at) "
        "SELECT ?, response_id, 'pending', ? FROM responses WHERE dataset_id = ?",
        (analysis_id, created_at.isoformat(), dataset_id),
    )


def insert_skipped(
    conn: sqlite3.Connection, analysis_id: str, reasons: dict[str, str], created_at: datetime
) -> None:
    # A rejected duplicate shares its ID with the stored response, which keeps the row.
    conn.executemany(
        "INSERT OR IGNORE INTO response_results "
        "(analysis_id, response_id, status, reason, updated_at) "
        "VALUES (?, ?, 'skipped', ?, ?)",
        [
            (analysis_id, response_id, reason, created_at.isoformat())
            for response_id, reason in reasons.items()
        ],
    )


def get_analysis(conn: sqlite3.Connection, analysis_id: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT a.*, "
        "COUNT(*) FILTER (WHERE rr.status = 'pending') AS pending, "
        "COUNT(*) FILTER (WHERE rr.status = 'done') AS done, "
        "COUNT(*) FILTER (WHERE rr.status = 'failed') AS failed, "
        "COUNT(*) FILTER (WHERE rr.status = 'skipped') AS skipped, "
        "COUNT(rr.response_id) AS total "
        "FROM analyses AS a LEFT JOIN response_results AS rr ON rr.analysis_id = a.analysis_id "
        "WHERE a.analysis_id = ? GROUP BY a.analysis_id",
        (analysis_id,),
    ).fetchone()


def list_results(
    conn: sqlite3.Connection, analysis_id: str, limit: int, offset: int
) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT rr.*, a.execution_mode FROM response_results AS rr "
        "JOIN analyses AS a ON a.analysis_id = rr.analysis_id "
        "WHERE rr.analysis_id = ? ORDER BY rr.response_id LIMIT ? OFFSET ?",
        (analysis_id, limit, offset),
    ).fetchall()


def get_result(conn: sqlite3.Connection, analysis_id: str, response_id: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT rr.*, a.execution_mode FROM response_results AS rr "
        "JOIN analyses AS a ON a.analysis_id = rr.analysis_id "
        "WHERE rr.analysis_id = ? AND rr.response_id = ?",
        (analysis_id, response_id),
    ).fetchone()


def requeue_failed(
    conn: sqlite3.Connection, analysis_id: str, max_attempts: int, updated_at: datetime
) -> None:
    conn.execute(
        "UPDATE response_results SET status = 'pending', error = NULL, updated_at = ? "
        "WHERE analysis_id = ? AND status = 'failed' AND attempts < ?",
        (updated_at.isoformat(), analysis_id, max_attempts),
    )


def next_pending(
    conn: sqlite3.Connection, execution_mode: str, model: str, limit: int
) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT rr.analysis_id, rr.response_id, a.dataset_id, p.text AS question, "
        "r.answer_text, r.answer_markdown "
        "FROM response_results AS rr "
        "JOIN analyses AS a ON a.analysis_id = rr.analysis_id "
        "JOIN responses AS r ON r.dataset_id = a.dataset_id AND r.response_id = rr.response_id "
        "JOIN prompts AS p ON p.dataset_id = r.dataset_id AND p.prompt_id = r.prompt_id "
        "WHERE rr.status = 'pending' AND a.execution_mode = ? AND a.model = ? "
        "ORDER BY a.created_at, rr.response_id LIMIT ?",
        (execution_mode, model, limit),
    ).fetchall()


def citation_urls(conn: sqlite3.Connection, dataset_id: str, response_id: str) -> list[str]:
    rows = conn.execute(
        "SELECT url FROM citations WHERE dataset_id = ? AND response_id = ? ORDER BY position",
        (dataset_id, response_id),
    ).fetchall()
    return [row["url"] for row in rows]


def save_result(
    conn: sqlite3.Connection,
    pending: sqlite3.Row,
    result: ResultRow,
    max_attempts: int,
    updated_at: datetime,
) -> bool:
    cursor = conn.execute(
        "UPDATE response_results SET status = ?, attempts = attempts + 1, labels_json = ?, "
        "score_json = ?, evidence_json = ?, error = ?, updated_at = ? "
        "WHERE analysis_id = ? AND response_id = ? AND status = 'pending' AND attempts < ?",
        (
            result.status,
            json.dumps(result.labels) if result.labels is not None else None,
            json.dumps(result.score) if result.score is not None else None,
            json.dumps(result.evidence),
            result.error,
            updated_at.isoformat(),
            pending["analysis_id"],
            pending["response_id"],
            max_attempts,
        ),
    )
    return cursor.rowcount == 1


def insert_model_call(
    conn: sqlite3.Connection, pending: sqlite3.Row, call: ModelCall, created_at: datetime
) -> None:
    conn.execute(
        "INSERT INTO model_calls (call_id, analysis_id, response_id, execution_mode, model, "
        "latency_ms, input_tokens, output_tokens, cost_usd, outcome, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            f"call_{uuid.uuid4().hex}",
            pending["analysis_id"],
            pending["response_id"],
            call.execution_mode,
            call.model,
            call.latency_ms,
            call.input_tokens,
            call.output_tokens,
            call.cost_usd,
            call.outcome,
            created_at.isoformat(),
        ),
    )
