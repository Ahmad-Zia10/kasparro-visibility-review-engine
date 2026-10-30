import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from app import clock, findings
from app.analyses import service as analyses
from app.analyses.schemas import AnalysisOut
from app.auth import Identity
from app.config import settings
from app.db import transaction
from app.errors import Conflict, NotFound, StaleVersion, VersionRequired
from app.reports import store
from app.reports.schemas import DecisionRequest, ExportOut, VersionOut

CATEGORIES_PATH = Path(__file__).parents[1] / "categories_v1.json"
LABEL_NOTE = (
    "Labels come from a small local model and are not verified beyond the hand-labelled "
    "cases; see the evaluation report."
)


def create_report(
    conn: sqlite3.Connection, analysis_id: str, analyst: Identity
) -> tuple[VersionOut, bool]:
    """Open a report on a finished analysis with a draft built from its findings."""
    analysis = analyses.get_analysis(conn, analysis_id)
    if analysis.status != "complete":
        raise Conflict("analysis is still running")
    content = build_content(conn, analysis)
    with transaction(conn):
        report_id = store.find_report_id(conn, analysis_id)
        is_new = report_id is None
        if is_new:
            report_id = f"rp_{uuid.uuid4().hex[:12]}"
            store.insert_report(conn, report_id, analysis_id, clock.now())
            add_draft(conn, report_id, 1, content, analyst)
    return get_report(conn, report_id), is_new


def build_content(conn: sqlite3.Connection, analysis: AnalysisOut) -> dict:
    rows = [row_facts(row) for row in store.analysis_rows(conn, analysis.analysis_id)]
    categories = load_categories()
    aggregates = findings.aggregate(rows, categories)
    diagnostics = findings.build_diagnostics(aggregates, rows, categories)
    return {
        "notice": findings.SNAPSHOT_NOTE,
        "live_observations": "none: only the archived answers were analysed",
        "label_note": LABEL_NOTE,
        "analysis": analysis.model_dump(mode="json", exclude={"created_at", "status"}),
        "summary": "",
        "aggregates": aggregates,
        "diagnostics": diagnostics,
        "remedies": findings.build_remedies(diagnostics),
    }


def row_facts(row: sqlite3.Row) -> dict:
    return {
        "response_id": row["response_id"],
        "prompt_id": row["prompt_id"],
        "engine": row["engine"],
        "status": row["status"],
        "labels": json.loads(row["labels_json"]) if row["labels_json"] else None,
        "score": json.loads(row["score_json"]) if row["score_json"] else None,
        "evidence": json.loads(row["evidence_json"]) if row["evidence_json"] else [],
    }


def load_categories() -> dict[str, dict]:
    document = json.loads(CATEGORIES_PATH.read_text(encoding="utf-8"))
    return {entry["prompt_id"]: entry for entry in document["prompts"]}


def get_report(conn: sqlite3.Connection, report_id: str) -> VersionOut:
    return version_out(require_latest(conn, report_id))


def edit_report(
    conn: sqlite3.Connection,
    report_id: str,
    if_match: str | None,
    content: dict,
    analyst: Identity,
) -> VersionOut:
    """Change the draft, or start a new draft when the latest version is frozen."""
    if if_match is None:
        raise VersionRequired("send If-Match with the ETag from the last read")
    with transaction(conn):
        latest = require_latest(conn, report_id)
        if if_match != etag(latest):
            raise StaleVersion("the report changed since you read it")
        if latest["status"] == "draft":
            changed = store.update_draft(
                conn, latest["version_id"], latest["revision"], encode(content)
            )
            if not changed:
                raise StaleVersion("the report changed since you read it")
        else:
            if latest["status"] == "submitted":
                store.mark_superseded(conn, latest["version_id"])
            add_draft(conn, report_id, latest["version_no"] + 1, content, analyst)
    return get_report(conn, report_id)


def submit_report(conn: sqlite3.Connection, report_id: str) -> VersionOut:
    """Freeze the draft and start its review window."""
    now = clock.now()
    with transaction(conn):
        latest = require_latest(conn, report_id)
        due = now + timedelta(hours=settings.review_ttl_hours)
        if not store.mark_submitted(conn, latest["version_id"], now, due):
            raise Conflict(f"version {latest['version_no']} is {latest['status']}, not a draft")
    return get_report(conn, report_id)


def decide(
    conn: sqlite3.Connection, report_id: str, request: DecisionRequest, reviewer: Identity
) -> VersionOut:
    """Approve or reject one submitted version, once, before its deadline."""
    now = clock.now()
    is_expired = False
    with transaction(conn):
        version = require_version(conn, report_id, request.version)
        if version["status"] != "submitted":
            raise Conflict(f"version {request.version} is {version['status']}, not under review")
        if now > parse(version["review_due_at"]):
            is_expired = store.mark_expired(conn, version["version_id"])
        else:
            record_decision(conn, version, request, reviewer, now)
    # Raised after the commit so the expired status is kept.
    if is_expired:
        raise Conflict(f"review deadline passed; version {request.version} is now expired")
    return version_out(require_version(conn, report_id, request.version))


def record_decision(
    conn: sqlite3.Connection,
    version: sqlite3.Row,
    request: DecisionRequest,
    reviewer: Identity,
    now: datetime,
) -> None:
    approved = request.decision == "approve"
    until = now + timedelta(hours=settings.approval_ttl_hours) if approved else None
    status = "approved" if approved else "rejected"
    # Guarded update: zero rows means another reviewer already decided.
    if not store.mark_decided(conn, version["version_id"], status, until):
        raise Conflict("version is no longer under review")
    decision = store.NewDecision(
        decision_id=f"dc_{uuid.uuid4().hex[:12]}",
        version_id=version["version_id"],
        actor=reviewer.name,
        decision=request.decision,
        comment=request.comment,
        decided_at=now,
    )
    store.insert_decision(conn, decision)


def export_report(conn: sqlite3.Connection, report_id: str, version_no: int | None) -> ExportOut:
    """Return an approved, unexpired version with everything that identifies it."""
    latest = require_latest(conn, report_id)
    version = latest if version_no is None else require_version(conn, report_id, version_no)
    if version["status"] != "approved":
        which = "latest version" if version_no is None else "version"
        raise Conflict(f"{which} {version['version_no']} is {version['status']}, not approved")
    valid_until = parse(version["approval_valid_until"])
    if clock.now() > valid_until:
        raise Conflict(f"approval of version {version['version_no']} expired at {valid_until}")
    decision = store.get_decision(conn, version["version_id"])
    analysis = analyses.get_analysis(conn, version["analysis_id"])
    return ExportOut(
        report_id=report_id,
        version=version["version_no"],
        is_latest_version=version["version_no"] == latest["version_no"],
        approved_by=decision["actor"],
        approved_at=decision["decided_at"],
        valid_until=valid_until,
        execution_mode=analysis.execution_mode,
        model=analysis.model,
        scoring_version=analysis.scoring_version,
        category_version=analysis.category_version,
        content_sha256=version["content_sha256"],
        content=json.loads(version["content_json"]),
    )


def add_draft(
    conn: sqlite3.Connection, report_id: str, version_no: int, content: dict, author: Identity
) -> None:
    content_json, content_sha256 = encode(content)
    draft = store.NewDraft(
        version_id=f"rv_{uuid.uuid4().hex[:12]}",
        report_id=report_id,
        version_no=version_no,
        content_json=content_json,
        content_sha256=content_sha256,
        created_by=author.name,
        created_at=clock.now(),
    )
    store.insert_version(conn, draft)


def encode(content: dict) -> tuple[str, str]:
    """Canonical JSON and its SHA-256, so equal content always hashes the same."""
    content_json = json.dumps(content, sort_keys=True, ensure_ascii=False)
    return content_json, hashlib.sha256(content_json.encode()).hexdigest()


def require_latest(conn: sqlite3.Connection, report_id: str) -> sqlite3.Row:
    version = store.latest_version(conn, report_id)
    if version is None:
        raise NotFound(f"report {report_id} not found")
    return version


def require_version(conn: sqlite3.Connection, report_id: str, version_no: int) -> sqlite3.Row:
    version = store.get_version(conn, report_id, version_no)
    if version is None:
        raise NotFound(f"report {report_id} has no version {version_no}")
    return version


def etag(version: sqlite3.Row) -> str:
    # Version and revision together, so a new draft never matches an old version's tag.
    return f'"{version["version_no"]}.{version["revision"]}"'


def parse(timestamp: str) -> datetime:
    return datetime.fromisoformat(timestamp)


def version_out(version: sqlite3.Row) -> VersionOut:
    return VersionOut(
        report_id=version["report_id"],
        analysis_id=version["analysis_id"],
        version=version["version_no"],
        status=version["status"],
        revision=version["revision"],
        etag=etag(version),
        content=json.loads(version["content_json"]),
        content_sha256=version["content_sha256"],
        created_by=version["created_by"],
        created_at=version["created_at"],
        submitted_at=version["submitted_at"],
        review_due_at=version["review_due_at"],
        approval_valid_until=version["approval_valid_until"],
    )
