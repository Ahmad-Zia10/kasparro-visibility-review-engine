from typing import Annotated

from fastapi import APIRouter, Header, Query, Response

from app.auth import Analyst, Caller, Reviewer
from app.db import Conn
from app.reports import service
from app.reports.schemas import ContentEdit, DecisionRequest, ExportOut, ReportRequest, VersionOut

router = APIRouter(prefix="/reports", tags=["reports"])


@router.post("", response_model=VersionOut, status_code=201)
def create_report(
    requested: ReportRequest, analyst: Analyst, conn: Conn, response: Response
) -> VersionOut:
    """Open a report on a finished analysis. A second call returns the same report."""
    version, is_new = service.create_report(conn, requested.analysis_id, analyst)
    response.status_code = 201 if is_new else 200
    response.headers["ETag"] = version.etag
    return version


@router.get("/{report_id}", response_model=VersionOut)
def read_report(report_id: str, caller: Caller, conn: Conn, response: Response) -> VersionOut:
    """Show the latest version. Its ETag is needed to edit it."""
    version = service.get_report(conn, report_id)
    response.headers["ETag"] = version.etag
    return version


@router.patch("/{report_id}", response_model=VersionOut)
def edit_report(
    report_id: str,
    edit: ContentEdit,
    analyst: Analyst,
    conn: Conn,
    if_match: Annotated[str | None, Header()] = None,
) -> VersionOut:
    """Replace the content; the new ETag is in the body. A frozen version gets a new draft."""
    return service.edit_report(conn, report_id, if_match, edit.content, analyst)


@router.post("/{report_id}/submit", response_model=VersionOut)
def submit_report(report_id: str, analyst: Analyst, conn: Conn) -> VersionOut:
    """Freeze the current draft and start its review window."""
    return service.submit_report(conn, report_id)


@router.post("/{report_id}/decision", response_model=VersionOut)
def decide(report_id: str, request: DecisionRequest, reviewer: Reviewer, conn: Conn) -> VersionOut:
    """Approve or reject a submitted version, with a comment."""
    return service.decide(conn, report_id, request, reviewer)


@router.get("/{report_id}/export", response_model=ExportOut)
def export_report(
    report_id: str,
    caller: Caller,
    conn: Conn,
    version: Annotated[int | None, Query(ge=1)] = None,
) -> ExportOut:
    """Export the latest version, or ?version=n, only if approved and unexpired."""
    return service.export_report(conn, report_id, version)
