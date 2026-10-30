import logging
import sqlite3
import threading
from contextlib import closing
from pathlib import Path

from app import clock
from app.analyses import store
from app.analyses.results import ResultRow, build_result
from app.analyses.service import configured_model
from app.classify.base import AnswerToClassify, Classifier
from app.config import settings
from app.db import connect, transaction

POLL_SECONDS = 2

logger = logging.getLogger(__name__)


def run(database_path: Path, classifier: Classifier, stop: threading.Event) -> None:
    """Classify pending responses one at a time until told to stop."""
    with closing(connect(database_path)) as conn:
        while not stop.is_set():
            if process_pending(conn, classifier, limit=1) == 0:
                stop.wait(POLL_SECONDS)


def process_pending(conn: sqlite3.Connection, classifier: Classifier, limit: int) -> int:
    """Classify up to `limit` pending responses, saving each as it finishes."""
    execution_mode, model = configured_model()
    rows = store.next_pending(conn, execution_mode, model, limit)
    for pending in rows:
        try:
            process_one(conn, classifier, pending)
        except Exception as error:  # noqa: BLE001 - one broken response must not stop the rest
            logger.exception("worker failed on response %s", pending["response_id"])
            failure = ResultRow(
                status="failed",
                labels=None,
                score=None,
                evidence=[],
                error=f"worker error: {error}",
            )
            with transaction(conn):
                store.save_result(conn, pending, failure, settings.model_max_attempts, clock.now())
    return len(rows)


def process_one(conn: sqlite3.Connection, classifier: Classifier, pending: sqlite3.Row) -> None:
    # R8: the model reads the markdown view when it exists, else the plain text.
    text = pending["answer_markdown"] or pending["answer_text"]
    urls = store.citation_urls(conn, pending["dataset_id"], pending["response_id"])
    answer = AnswerToClassify(pending["response_id"], pending["question"], text)
    # Never call the model inside a transaction; it can take minutes.
    call = classifier.classify(answer)
    result = build_result(call, text, urls)
    with transaction(conn):
        store.insert_model_call(conn, pending, call, clock.now())
        is_saved = store.save_result(
            conn, pending, result, settings.model_max_attempts, clock.now()
        )
    if not is_saved:
        logger.warning("response %s was already saved; call logged only", pending["response_id"])
