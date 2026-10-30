from http import HTTPStatus

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException


class AppError(Exception):
    status_code = 500
    code = "internal_error"

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class Unauthenticated(AppError):
    status_code = 401
    code = "unauthenticated"


class Forbidden(AppError):
    status_code = 403
    code = "forbidden"


class NotFound(AppError):
    status_code = 404
    code = "not_found"


class UnreadablePack(AppError):
    status_code = 422
    code = "unreadable_pack"


def handle_app_error(request: Request, app_error: AppError) -> JSONResponse:
    body = {"error": app_error.code, "detail": app_error.detail}
    return JSONResponse(body, status_code=app_error.status_code)


def handle_validation_error(request: Request, invalid: RequestValidationError) -> JSONResponse:
    problems = [
        f"{'.'.join(str(part) for part in issue['loc'])}: {issue['msg']}"
        for issue in invalid.errors()
    ]
    body = {"error": "invalid_request", "detail": "; ".join(problems)}
    return JSONResponse(body, status_code=422)


def handle_http_error(request: Request, http_error: HTTPException) -> JSONResponse:
    """Give framework errors, such as an unknown URL, the same body shape."""
    code = HTTPStatus(http_error.status_code).phrase.lower().replace(" ", "_")
    body = {"error": code, "detail": str(http_error.detail)}
    return JSONResponse(body, status_code=http_error.status_code)
