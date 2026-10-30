from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, closing

from fastapi import APIRouter, FastAPI
from fastapi.exceptions import RequestValidationError

from app.config import settings
from app.db import connect, init_db
from app.errors import AppError, handle_app_error, handle_validation_error

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    """Report that the service is running. Needs no token."""
    return {"status": "ok"}


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    with closing(connect(settings.database_path)) as conn:
        init_db(conn)
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="Kasparro AI visibility review", lifespan=lifespan)
    app.add_exception_handler(AppError, handle_app_error)
    app.add_exception_handler(RequestValidationError, handle_validation_error)
    app.include_router(router)
    return app


app = create_app()
