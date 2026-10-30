from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


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
