from typing import Annotated

from fastapi import APIRouter, Query, Response

from app.analyses import service
from app.analyses.schemas import AnalysisOut, AnalysisRequest, ResultOut, ResultsPage
from app.auth import Analyst, Caller
from app.db import Conn

router = APIRouter(prefix="/analyses", tags=["analyses"])


@router.post("", response_model=AnalysisOut, status_code=202)
def start_analysis(
    requested: AnalysisRequest, analyst: Analyst, conn: Conn, response: Response
) -> AnalysisOut:
    """Queue a dataset for labelling. The same configuration returns the existing run."""
    analysis, is_new = service.start_analysis(conn, requested.dataset_id)
    if not is_new:
        response.status_code = 200
    return analysis


@router.get("/{analysis_id}", response_model=AnalysisOut)
def read_analysis(analysis_id: str, caller: Caller, conn: Conn) -> AnalysisOut:
    """Show a run's configuration and how many responses are in each status."""
    return service.get_analysis(conn, analysis_id)


@router.get("/{analysis_id}/results", response_model=ResultsPage)
def list_results(
    analysis_id: str,
    caller: Caller,
    conn: Conn,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ResultsPage:
    """List results in response ID order, at most 100 per page."""
    return service.list_results(conn, analysis_id, limit, offset)


@router.get("/{analysis_id}/results/{response_id}", response_model=ResultOut)
def read_result(analysis_id: str, response_id: str, caller: Caller, conn: Conn) -> ResultOut:
    """Show one response's status, labels, score, evidence and any error or skip reason."""
    return service.get_result(conn, analysis_id, response_id)


@router.post("/{analysis_id}/retry", response_model=AnalysisOut)
def retry_failed(analysis_id: str, analyst: Analyst, conn: Conn) -> AnalysisOut:
    """Requeue failed responses that have attempts left."""
    return service.retry_failed(conn, analysis_id)
