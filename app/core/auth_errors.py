from http import HTTPStatus
from typing import Any

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


COMMON_PROBLEM_STATUS_CODES = (400, 401, 403, 404, 409, 422, 429, 503, 504)


class AuthProblem(HTTPException):
    def __init__(self, status_code: int, detail: str):
        super().__init__(
            status_code,
            detail,
            headers={"WWW-Authenticate": "Bearer"} if status_code == 401 else None,
        )


PROBLEM_SCHEMA = {
    "type": "object",
    "required": ["type", "title", "status", "detail", "instance"],
    "properties": {
        "type": {"type": "string"},
        "title": {"type": "string"},
        "status": {"type": "integer"},
        "detail": {"type": "string"},
        "instance": {"type": "string"},
        "errors": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["loc", "msg", "type"],
                "properties": {
                    "loc": {
                        "type": "array",
                        "items": {"anyOf": [{"type": "string"}, {"type": "integer"}]},
                    },
                    "msg": {"type": "string"},
                    "type": {"type": "string"},
                },
            },
        },
        "code": {"type": "string"},
        "action": {"type": "string"},
    },
}


def problem_response(description: str):
    return {
        "description": description,
        "content": {
            "application/problem+json": {
                "schema": PROBLEM_SCHEMA,
            }
        },
    }


PROBLEM_RESPONSES = {
    code: problem_response(HTTPStatus(code).phrase)
    for code in COMMON_PROBLEM_STATUS_CODES
}

# Backwards-compatible name used by existing routers.
AUTH_RESPONSES = {
    code: PROBLEM_RESPONSES[code]
    for code in (400, 401, 403, 503)
}


def _title(status_code: int) -> str:
    try:
        return HTTPStatus(status_code).phrase
    except ValueError:
        return "HTTP Error"


def _safe_http_detail(status_code: int, detail: Any) -> tuple[str, dict[str, str]]:
    if isinstance(detail, str):
        return detail, {}

    if isinstance(detail, dict):
        message = detail.get("message")
        safe_detail = message if isinstance(message, str) and message else _title(status_code)
        extensions = {
            key: value
            for key in ("code", "action")
            if isinstance((value := detail.get(key)), str)
        }
        return safe_detail, extensions

    return _title(status_code), {}


def _problem_content(
    request: Request,
    status_code: int,
    detail: str,
    **extensions: Any,
) -> dict[str, Any]:
    return {
        "type": "about:blank",
        "title": _title(status_code),
        "status": status_code,
        "detail": detail,
        "instance": request.url.path,
        **extensions,
    }


async def http_problem_handler(
    request: Request,
    exc: StarletteHTTPException,
):
    detail, extensions = _safe_http_detail(exc.status_code, exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content=_problem_content(
            request,
            exc.status_code,
            detail,
            **extensions,
        ),
        headers=exc.headers,
        media_type="application/problem+json",
    )


async def auth_problem_handler(request: Request, exc: AuthProblem):
    return await http_problem_handler(request, exc)


async def validation_problem_handler(
    request: Request,
    exc: RequestValidationError,
):
    errors = [
        {
            "loc": list(error.get("loc", ())),
            "msg": str(error.get("msg", "Invalid value")),
            "type": str(error.get("type", "value_error")),
        }
        for error in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content=_problem_content(
            request,
            422,
            "Request validation failed",
            errors=errors,
        ),
        media_type="application/problem+json",
    )
