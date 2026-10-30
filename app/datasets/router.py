from fastapi import APIRouter, Response

from app.auth import Analyst, Caller
from app.config import settings
from app.datasets import service
from app.datasets.schemas import DatasetOut
from app.db import Conn

router = APIRouter(prefix="/datasets", tags=["datasets"])


@router.post("", response_model=DatasetOut, status_code=201)
def import_dataset(analyst: Analyst, conn: Conn, response: Response) -> DatasetOut:
    """Import the pack from PACK_DIR. Importing the same files again returns the same dataset."""
    dataset, is_new = service.import_dataset(conn, settings.pack_dir)
    if not is_new:
        response.status_code = 200
    return dataset


@router.get("/{dataset_id}", response_model=DatasetOut)
def read_dataset(dataset_id: str, caller: Caller, conn: Conn) -> DatasetOut:
    """Show a dataset's counts and every rejected record with its reason."""
    return service.get_dataset(conn, dataset_id)
