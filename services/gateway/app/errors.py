from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class AppError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class Unauthenticated(AppError):
    def __init__(self, message: str = "Missing or invalid Authorization header") -> None:
        super().__init__("UNAUTHENTICATED", message, 401)


class Forbidden(AppError):
    def __init__(self, message: str = "Token kind not allowed for this endpoint") -> None:
        super().__init__("FORBIDDEN", message, 403)


class NotFound(AppError):
    def __init__(self, message: str = "Resource not found") -> None:
        super().__init__("NOT_FOUND", message, 404)


class Conflict(AppError):
    def __init__(self, message: str = "Conflict", code: str = "CONFLICT") -> None:
        super().__init__(code, message, 409)


class ValidationFailed(AppError):
    def __init__(self, message: str, code: str = "VALIDATION_ERROR") -> None:
        super().__init__(code, message, 422)


def error_body(code: str, message: str, request_id: str) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "request_id": request_id}}


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", None) or request.headers.get("X-Request-Id") or "unknown"


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=error_body(exc.code, exc.message, _request_id(request)),
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = "ERROR"
    if exc.status_code == 401:
        code = "UNAUTHENTICATED"
    elif exc.status_code == 403:
        code = "FORBIDDEN"
    elif exc.status_code == 404:
        code = "NOT_FOUND"
    elif exc.status_code == 409:
        code = "CONFLICT"
    elif exc.status_code == 422:
        code = "VALIDATION_ERROR"
    detail = exc.detail
    if isinstance(detail, dict) and "code" in detail:
        code = detail["code"]
        message = detail.get("message", str(detail))
    else:
        message = str(detail)
    return JSONResponse(
        status_code=exc.status_code,
        content=error_body(code, message, _request_id(request)),
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    errs = exc.errors()
    msg = errs[0]["msg"] if errs else "Validation error"
    loc = errs[0].get("loc") if errs else None
    if loc:
        msg = f"{'.'.join(str(x) for x in loc)}: {msg}"
    return JSONResponse(
        status_code=422,
        content=error_body("VALIDATION_ERROR", msg, _request_id(request)),
    )
