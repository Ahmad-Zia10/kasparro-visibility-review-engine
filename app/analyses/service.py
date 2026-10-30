import json
import sqlite3
import uuid

from app import clock
from app.analyses import store
from app.analyses.schemas import (
    AnalysisConfig,
    AnalysisOut,
    ResultOut,
    ResultsPage,
    StatusCounts,
)
from app.classify.base import PROMPT_VERSION, ExecutionMode
from app.config import settings
from app.datasets.schemas import RejectedRecord
from app.datasets.service import get_dataset
from app.db import transaction
from app.errors import NotFound
from app.scoring import SCORING_VERSION

CATEGORY_VERSION = "categories_v1"
EXECUTION_MODES: dict[str, ExecutionMode] = {
    "local": "local-model",
    "replay": "replay",
    "stub": "stub",
}


def configured_model() -> tuple[ExecutionMode, str]:
    """Execution mode and model name that the current settings select."""
    execution_mode = EXECUTION_MODES[settings.model_mode]
    # UNIQUE treats NULLs as distinct, so the stub needs a model name.
    model = "stub" if execution_mode == "stub" else settings.model_name
    return execution_mode, model


def start_analysis(conn: sqlite3.Connection, dataset_id: str) -> tuple[AnalysisOut, bool]:
    """Queue every response of the dataset once per config; return the run and whether it is new."""
    dataset = get_dataset(conn, dataset_id)
    execution_mode, model = configured_model()
    config = AnalysisConfig(
        dataset_id=dataset_id,
        execution_mode=execution_mode,
        prompt_version=PROMPT_VERSION,
        model=model,
        scoring_version=SCORING_VERSION,
        category_version=CATEGORY_VERSION,
    )
    with transaction(conn):
        analysis_id = store.find_analysis_id(conn, config)
        is_new = analysis_id is None
        if is_new:
            analysis_id = f"an_{uuid.uuid4().hex[:12]}"
            now = clock.now()
            store.insert_analysis(conn, analysis_id, config, now)
            store.insert_pending(conn, analysis_id, dataset_id, now)
            store.insert_skipped(conn, analysis_id, skip_reasons(dataset.rejected), now)
    return get_analysis(conn, analysis_id), is_new


def skip_reasons(rejected: list[RejectedRecord]) -> dict[str, str]:
    """R23: each rejected response with a readable ID gets a skipped row and its reason."""
    return {
        record.record_id: record.reason
        for record in rejected
        if record.file == "responses.jsonl" and record.record_id is not None
    }


def get_analysis(conn: sqlite3.Connection, analysis_id: str) -> AnalysisOut:
    row = store.get_analysis(conn, analysis_id)
    if row is None:
        raise NotFound(f"analysis {analysis_id} not found")
    counts = StatusCounts(
        pending=row["pending"],
        done=row["done"],
        failed=row["failed"],
        skipped=row["skipped"],
        total=row["total"],
    )
    status = "running" if counts.pending else "complete"
    return AnalysisOut.model_validate(dict(row) | {"status": status, "counts": counts})


def list_results(
    conn: sqlite3.Connection, analysis_id: str, limit: int, offset: int
) -> ResultsPage:
    analysis = get_analysis(conn, analysis_id)
    rows = store.list_results(conn, analysis_id, limit, offset)
    return ResultsPage(
        total=analysis.counts.total,
        limit=limit,
        offset=offset,
        results=[result_out(row) for row in rows],
    )


def get_result(conn: sqlite3.Connection, analysis_id: str, response_id: str) -> ResultOut:
    row = store.get_result(conn, analysis_id, response_id)
    if row is None:
        raise NotFound(f"response {response_id} not found in analysis {analysis_id}")
    return result_out(row)


def retry_failed(conn: sqlite3.Connection, analysis_id: str) -> AnalysisOut:
    """Put failed responses back in the queue unless they have used every attempt."""
    get_analysis(conn, analysis_id)
    with transaction(conn):
        store.requeue_failed(conn, analysis_id, settings.model_max_attempts, clock.now())
    return get_analysis(conn, analysis_id)


def result_out(row: sqlite3.Row) -> ResultOut:
    return ResultOut(
        analysis_id=row["analysis_id"],
        response_id=row["response_id"],
        status=row["status"],
        attempts=row["attempts"],
        execution_mode=row["execution_mode"],
        labels=json.loads(row["labels_json"]) if row["labels_json"] else None,
        score=json.loads(row["score_json"]) if row["score_json"] else None,
        evidence=json.loads(row["evidence_json"]) if row["evidence_json"] else [],
        error=row["error"],
        reason=row["reason"],
        updated_at=row["updated_at"],
    )
