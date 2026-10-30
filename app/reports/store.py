import sqlite3
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class NewDraft:
    version_id: str
    report_id: str
    version_no: int
    content_json: str
    content_sha256: str
    created_by: str
    created_at: datetime


@dataclass(frozen=True)
class NewDecision:
    decision_id: str
    version_id: str
    actor: str
    decision: str
    comment: str
    decided_at: datetime


VERSION_COLUMNS = "v.*, r.analysis_id FROM report_versions AS v JOIN reports AS r USING (report_id)"


def find_report_id(conn: sqlite3.Connection, analysis_id: str) -> str | None:
    row = conn.execute(
        "SELECT report_id FROM reports WHERE analysis_id = ?", (analysis_id,)
    ).fetchone()
    return row["report_id"] if row else None


def insert_report(
    conn: sqlite3.Connection, report_id: str, analysis_id: str, created_at: datetime
) -> None:
    conn.execute(
        "INSERT INTO reports (report_id, analysis_id, created_at) VALUES (?, ?, ?)",
        (report_id, analysis_id, created_at.isoformat()),
    )


def insert_version(conn: sqlite3.Connection, draft: NewDraft) -> None:
    conn.execute(
        "INSERT INTO report_versions (version_id, report_id, version_no, status, content_json, "
        "content_sha256, created_by, created_at) VALUES (?, ?, ?, 'draft', ?, ?, ?, ?)",
        (
            draft.version_id,
            draft.report_id,
            draft.version_no,
            draft.content_json,
            draft.content_sha256,
            draft.created_by,
            draft.created_at.isoformat(),
        ),
    )


def latest_version(conn: sqlite3.Connection, report_id: str) -> sqlite3.Row | None:
    return conn.execute(
        f"SELECT {VERSION_COLUMNS} WHERE v.report_id = ? ORDER BY v.version_no DESC LIMIT 1",
        (report_id,),
    ).fetchone()


def get_version(conn: sqlite3.Connection, report_id: str, version_no: int) -> sqlite3.Row | None:
    return conn.execute(
        f"SELECT {VERSION_COLUMNS} WHERE v.report_id = ? AND v.version_no = ?",
        (report_id, version_no),
    ).fetchone()


def update_draft(
    conn: sqlite3.Connection, version_id: str, revision: int, encoded: tuple[str, str]
) -> bool:
    cursor = conn.execute(
        "UPDATE report_versions SET content_json = ?, content_sha256 = ?, revision = revision + 1 "
        "WHERE version_id = ? AND revision = ? AND status = 'draft'",
        (*encoded, version_id, revision),
    )
    return cursor.rowcount == 1


def mark_superseded(conn: sqlite3.Connection, version_id: str) -> bool:
    cursor = conn.execute(
        "UPDATE report_versions SET status = 'superseded' "
        "WHERE version_id = ? AND status = 'submitted'",
        (version_id,),
    )
    return cursor.rowcount == 1


def mark_submitted(
    conn: sqlite3.Connection, version_id: str, submitted_at: datetime, review_due_at: datetime
) -> bool:
    cursor = conn.execute(
        "UPDATE report_versions SET status = 'submitted', submitted_at = ?, review_due_at = ? "
        "WHERE version_id = ? AND status = 'draft'",
        (submitted_at.isoformat(), review_due_at.isoformat(), version_id),
    )
    return cursor.rowcount == 1


def mark_decided(
    conn: sqlite3.Connection, version_id: str, status: str, valid_until: datetime | None
) -> bool:
    cursor = conn.execute(
        "UPDATE report_versions SET status = ?, approval_valid_until = ? "
        "WHERE version_id = ? AND status = 'submitted'",
        (status, valid_until.isoformat() if valid_until else None, version_id),
    )
    return cursor.rowcount == 1


def mark_expired(conn: sqlite3.Connection, version_id: str) -> bool:
    cursor = conn.execute(
        "UPDATE report_versions SET status = 'expired' "
        "WHERE version_id = ? AND status = 'submitted'",
        (version_id,),
    )
    return cursor.rowcount == 1


def insert_decision(conn: sqlite3.Connection, decision: NewDecision) -> None:
    conn.execute(
        "INSERT INTO review_decisions "
        "(decision_id, version_id, actor, decision, comment, decided_at) VALUES (?, ?, ?, ?, ?, ?)",
        (
            decision.decision_id,
            decision.version_id,
            decision.actor,
            decision.decision,
            decision.comment,
            decision.decided_at.isoformat(),
        ),
    )


def get_decision(conn: sqlite3.Connection, version_id: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM review_decisions WHERE version_id = ?", (version_id,)
    ).fetchone()


def analysis_rows(conn: sqlite3.Connection, analysis_id: str) -> list[sqlite3.Row]:
    # Skipped rows may name rejected responses that were never stored, hence the LEFT JOIN.
    return conn.execute(
        "SELECT rr.response_id, rr.status, rr.labels_json, rr.score_json, rr.evidence_json, "
        "COALESCE(r.prompt_id, '') AS prompt_id, COALESCE(r.engine, 'unknown') AS engine "
        "FROM response_results AS rr JOIN analyses AS a ON a.analysis_id = rr.analysis_id "
        "LEFT JOIN responses AS r "
        "ON r.dataset_id = a.dataset_id AND r.response_id = rr.response_id "
        "WHERE rr.analysis_id = ? ORDER BY rr.response_id",
        (analysis_id,),
    ).fetchall()
